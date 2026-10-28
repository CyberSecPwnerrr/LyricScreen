import os
import re
import socket
import ctypes
from ctypes import wintypes

from lyricshud.paths import PROFILE_DIR


class _BB(ctypes.Structure):
    _fields_ = [
        ("flags", wintypes.DWORD),
        ("enable", wintypes.BOOL),
        ("rgn", ctypes.c_void_p),
        ("trans", wintypes.BOOL),
    ]


def set_blur(widget, on, rect=None, radius=0.0):
    try:
        dpr = widget.devicePixelRatioF()
        gdi = ctypes.windll.gdi32
        gdi.CreateRoundRectRgn.restype = ctypes.c_void_p
        gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi.DeleteObject.argtypes = [ctypes.c_void_p]
        dwm = ctypes.windll.dwmapi
        dwm.DwmEnableBlurBehindWindow.argtypes = [wintypes.HWND, ctypes.POINTER(_BB)]
        bb = _BB()
        bb.enable = 1 if on else 0
        bb.flags = 1
        rgn = None
        if on and rect is not None:
            d = int(radius * 2 * dpr)
            rgn = gdi.CreateRoundRectRgn(
                int(rect.left() * dpr),
                int(rect.top() * dpr),
                int(rect.right() * dpr) + 1,
                int(rect.bottom() * dpr) + 1,
                d,
                d,
            )
            bb.flags = 3
            bb.rgn = rgn
        dwm.DwmEnableBlurBehindWindow(int(widget.winId()), ctypes.byref(bb))
        if rgn:
            gdi.DeleteObject(rgn)
    except Exception:
        pass


def desktop_names():
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    display = ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        size = wintypes.ULONG(256)
        if ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size)):
            display = buf.value
    except Exception:
        pass
    return display or user or "there", os.environ.get("COMPUTERNAME") or socket.gethostname()


def list_profiles():
    try:
        return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    except Exception:
        return []


def profile_path(name):
    safe = re.sub(r"[^\w\- ]+", "", name or "").strip()
    return PROFILE_DIR / (safe + ".json") if safe else None
