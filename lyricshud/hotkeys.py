import re
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QPushButton


HOTKEY_ACTIONS = (
    ("later", "Lyrics later (-100 ms)", "hk_later"),
    ("earlier", "Lyrics earlier (+100 ms)", "hk_earlier"),
    ("reset", "Reset sync offset", "hk_reset"),
    ("snap", "Next line starts now", "hk_snap"),
    ("toggle", "Show / hide", "hk_toggle"),
    ("orbital", "Orbital menu", "hk_orbital"),
)

HOTKEY_SPECIAL = {
    "Space": 0x20,
    "Tab": 0x09,
    "Return": 0x0D,
    "Enter": 0x0D,
    "Backspace": 0x08,
    "Del": 0x2E,
    "Ins": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PgUp": 0x21,
    "PgDown": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
}

HOTKEY_QT = {
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Return: "Return",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Delete: "Del",
    Qt.Key.Key_Insert: "Ins",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PgUp",
    Qt.Key.Key_PageDown: "PgDown",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Down: "Down",
}


def parse_hotkey(text):
    mods = 0
    vk = 0
    for part in str(text).split("+"):
        part = part.strip()
        if part == "Alt":
            mods |= 0x1
        elif part == "Ctrl":
            mods |= 0x2
        elif part == "Shift":
            mods |= 0x4
        elif part == "Meta":
            mods |= 0x8
        elif len(part) == 1 and (part.isascii() and part.isalnum()):
            vk = ord(part.upper())
        elif part in HOTKEY_SPECIAL:
            vk = HOTKEY_SPECIAL[part]
        elif re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", part):
            vk = 0x6F + int(part[1:])
        else:
            return None
    if not mods or not vk:
        return None
    return mods | 0x4000, vk


def hotkey_text(e):
    k = e.key()
    m = e.modifiers()
    if k in HOTKEY_QT:
        tok = HOTKEY_QT[k]
    elif Qt.Key.Key_A <= k <= Qt.Key.Key_Z or Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
        tok = chr(int(k))
    elif Qt.Key.Key_F1 <= k <= Qt.Key.Key_F24:
        tok = "F%d" % (int(k) - int(Qt.Key.Key_F1) + 1)
    else:
        return None
    parts = []
    if m & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if m & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if m & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if m & Qt.KeyboardModifier.MetaModifier:
        parts.append("Meta")
    if not parts:
        return None
    return "+".join(parts + [tok])


class KeyCapture(QPushButton):
    changed = pyqtSignal(str)

    def __init__(self, text, taken):
        super().__init__(text)
        self.taken = taken
        self.capturing = False
        self.prev = text
        self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self.begin)

    def begin(self):
        self.capturing = True
        self.prev = self.text()
        self.setText("Press the new keys...")
        self.setFocus()
        self.grabKeyboard()

    def finish(self, text):
        self.capturing = False
        self.releaseKeyboard()
        self.setText(text)

    def focusOutEvent(self, e):
        if self.capturing:
            self.finish(self.prev)
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self.capturing:
            super().keyPressEvent(e)
            return
        if e.key() == Qt.Key.Key_Escape:
            self.finish(self.prev)
            return
        text = hotkey_text(e)
        if text is None or parse_hotkey(text) is None:
            return
        if text != self.prev and self.taken(text):
            self.setText("Already used, try another")
            return
        self.finish(text)
        if text != self.prev:
            self.changed.emit(text)


class HotkeyWorker(QThread):
    fired = pyqtSignal(str)

    def __init__(self, items):
        super().__init__()
        self.items = items
        self.tid = 0

    def run(self):
        u = ctypes.windll.user32
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        ids = {}
        for n, (name, mods, vk) in enumerate(self.items, 1):
            if u.RegisterHotKey(None, n, mods, vk):
                ids[n] = name
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                name = ids.get(int(msg.wParam))
                if name:
                    self.fired.emit(name)
        for n in ids:
            u.UnregisterHotKey(None, n)

    def stop(self):
        if self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)
