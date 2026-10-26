import sys

if sys.platform != "win32":
    print("Lyrics HUD needs Windows (media session API).")
    sys.exit(1)

import os
import json
import re
import time
import math
import random
import hashlib
import asyncio
import threading
import subprocess
import importlib
import queue
import warnings
import ctypes
from ctypes import wintypes
from bisect import bisect_right
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib import request as urlrequest
from urllib import parse as urlparse
from urllib.error import URLError, HTTPError

warnings.filterwarnings("ignore", category=FutureWarning)

REQUIRED = [
    ("PyQt6", "PyQt6"),
    ("winrt.runtime", "winrt-runtime"),
    ("winrt.windows.foundation", "winrt-Windows.Foundation"),
    ("winrt.windows.foundation.collections", "winrt-Windows.Foundation.Collections"),
    ("winrt.windows.media", "winrt-Windows.Media"),
    ("winrt.windows.media.control", "winrt-Windows.Media.Control"),
    ("winrt.windows.storage.streams", "winrt-Windows.Storage.Streams"),
]

OPTIONAL = [("comtypes", "comtypes"), ("pycaw", "pycaw")]


def ensure_packages():
    missing = []
    for mod, pkg in REQUIRED:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        print("Installing:", ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing]
        )
    for mod, pkg in OPTIONAL:
        try:
            importlib.import_module(mod)
        except Exception:
            print("Installing optional:", pkg)
            subprocess.call(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    importlib.invalidate_caches()


# ---------------------------------------------------------------------------
# Self-install (PyInstaller build only)
# First run of a downloaded LyricsScreen.exe copies itself to
# "C:\Program Files\Lyrics Screen", adds a Desktop shortcut and launches the
# installed copy. Runs of the installed copy start the app normally.
# Flags: --no-install (run from where it is), --selftest (build check)
# ---------------------------------------------------------------------------
APP_NAME = "Lyrics Screen"
EXE_NAME = "LyricsScreen.exe"
FROZEN = bool(getattr(sys, "frozen", False))


class _SEI(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _msgbox(text):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    except Exception:
        pass


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _install_dir():
    base = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(base) / APP_NAME


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _clean_env():
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_MEIPASS2", None)
    return env


def _do_copy(src, dst_dir):
    import shutil

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        tmp = dst_dir / (EXE_NAME + ".new")
        shutil.copy2(str(src), str(tmp))
        os.replace(str(tmp), str(dst_dir / EXE_NAME))
        return 0
    except Exception:
        return 1


def _run_elevated(exe, params):
    """Run exe elevated and wait. Returns the exit code, or None if UAC was declined."""
    k = ctypes.windll.kernel32
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.windll.shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SEI)]
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    os.environ.pop("_MEIPASS2", None)
    sei = _SEI()
    sei.cbSize = ctypes.sizeof(_SEI)
    sei.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = 0  # SW_HIDE
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None
    k.WaitForSingleObject(sei.hProcess, 180000)
    code = wintypes.DWORD(1)
    k.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    k.CloseHandle(sei.hProcess)
    return int(code.value)


def _make_desktop_shortcut(target):
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d ($env:LH_NAME+'.lnk')));"
        "$s.TargetPath=$env:LH_EXE;"
        "$s.WorkingDirectory=Split-Path $env:LH_EXE;"
        "$s.IconLocation=$env:LH_EXE;"
        "$s.Description=$env:LH_NAME;"
        "$s.Save()"
    )
    env = dict(os.environ, LH_NAME=APP_NAME, LH_EXE=str(target))
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            creationflags=0x08000000,
            timeout=60,
            check=False,
        )
    except Exception:
        pass


def _make_font_dir(d):
    try:
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["icacls", str(d), "/grant", "*S-1-5-32-545:(OI)(CI)M"],
            creationflags=0x08000000,
            timeout=30,
            check=False,
        )
        return 0
    except Exception:
        return 1


def self_install():
    if not FROZEN or "--no-install" in sys.argv:
        return
    if "--install-copy" in sys.argv:  # elevated helper: copy and exit
        i = sys.argv.index("--install-copy")
        sys.exit(_do_copy(Path(sys.argv[i + 1]), Path(sys.argv[i + 2])))
    if "--make-font-dir" in sys.argv:
        i = sys.argv.index("--make-font-dir")
        sys.exit(_make_font_dir(Path(sys.argv[i + 1])))
    exe = Path(sys.executable)
    target_dir = _install_dir()
    target = target_dir / EXE_NAME
    if _same_path(exe.parent, target_dir):
        return  # already the installed copy -> just run the app
    import filecmp

    try:
        up_to_date = target.exists() and filecmp.cmp(str(exe), str(target), shallow=False)
    except Exception:
        up_to_date = False
    if not up_to_date:
        if _is_admin():
            code = _do_copy(exe, target_dir)
        else:
            code = _run_elevated(str(exe), subprocess.list2cmdline(["--install-copy", str(exe), str(target_dir)]))
        if code is None:
            return  # UAC declined -> run portable from the current location
        if code != 0 or not target.exists():
            _msgbox(
                "Could not install to:\n" + str(target_dir) + "\n\n"
                "If Lyrics Screen is already running, quit it from the tray icon and open this file again."
            )
            sys.exit(1)
    _make_desktop_shortcut(target)
    try:
        subprocess.Popen(
            [str(target)],
            cwd=str(target_dir),
            env=_clean_env(),
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
    except Exception as e:
        _msgbox("Installed, but could not start the app:\n" + str(e))
        sys.exit(1)
    sys.exit(0)


self_install()
if not FROZEN:
    ensure_packages()

from PyQt6.QtCore import Qt, QThread, QObject, QTimer, QRectF, QPointF, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QFontDatabase,
    QPixmap,
    QImage,
    QLinearGradient,
    QRadialGradient,
    QConicalGradient,
    QTransform,
    QIcon,
    QAction,
    QActionGroup,
    QGuiApplication,
    QCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QButtonGroup,
    QLabel,
    QSlider,
    QSpinBox,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QFileDialog,
    QColorDialog,
    QListWidget,
    QStackedWidget,
    QScrollArea,
)

from winrt.windows.media import MediaPlaybackAutoRepeatMode
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winrt.windows.storage.streams import Buffer, InputStreamOptions, DataReader

APP_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "LyricsHUD"
CACHE_DIR = APP_DIR / "cache"
CFG_PATH = APP_DIR / "config.json"
OFFS_PATH = APP_DIR / "track_offsets.json"
APP_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_font_dir():
    base = Path(sys.executable).parent if FROZEN else Path(os.path.abspath(__file__)).parent
    if (
        FROZEN
        and "--no-install" not in sys.argv
        and not (base / "Font").exists()
        and not _is_admin()
        and _same_path(base, _install_dir())
    ):
        _run_elevated(sys.executable, subprocess.list2cmdline(["--make-font-dir", str(base / "Font")]))
    for d in (base / "Font", APP_DIR / "Font"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("x")
            probe.unlink()
            return d
        except Exception:
            continue
    return APP_DIR


FONT_DIR = _resolve_font_dir()
FONT_EXTS = (".ttf", ".otf", ".ttc")
GF_META = "https://fonts.google.com/metadata/fonts"
GF_CSS = "https://fonts.googleapis.com/css"

DEFAULT_FAMILY = "Segoe UI"
API = "https://lrclib.net/api"
UA = "LyricsHUD/2.0 (desktop lyrics widget)"

POS_KEYS = ["tl", "tr", "m", "ml", "mr", "bl", "br"]
POS = {
    "tl": (0.07, 0.17, "l"),
    "tr": (0.93, 0.17, "r"),
    "m": (0.50, 0.50, "c"),
    "ml": (0.07, 0.50, "l"),
    "mr": (0.93, 0.50, "r"),
    "bl": (0.07, 0.80, "l"),
    "br": (0.93, 0.80, "r"),
}
POS_LABELS = {
    "tl": "Top left",
    "tr": "Top right",
    "m": "Middle",
    "ml": "Middle left",
    "mr": "Middle right",
    "bl": "Bottom left",
    "br": "Bottom right",
}

DEFAULTS = {
    "mode": "both",
    "visible": True,
    "adaptive": True,
    "accent": "#ff2a6d",
    "secondary": "#05d9e8",
    "text": "#f4eeff",
    "font_path": "",
    "font_size": 26,
    "glow": 70,
    "opacity": 96,
    "lyric_opacity": 100,
    "offset_ms": 0,
    "hold": 100,
    "fade_ms": 450,
    "karaoke": True,
    "placement": "random",
    "positions": list(POS_KEYS),
    "fps": 30,
    "show_cover": True,
    "show_volume": True,
    "click_through": False,
    "particles": True,
    "scanlines": True,
    "glitch": True,
    "tilt": True,
    "holo_scale": 100,
    "holo_screen": 0,
    "auto_sync": True,
    "lyric_weight": 600,
    "lyric_spacing": 1,
    "lyric_case": "none",
    "lyric_fill": "soft",
    "lyric_outline": 0,
    "lyric_shadow": 40,
    "lyric_gap": 100,
    "glow_color": "accent",
    "dim_level": 42,
    "motion": 100,
    "holo_width": 36,
    "card_gap": 24,
    "particle_count": 42,
    "show_toast": True,
    "card_radius": 20,
    "backdrop": 34,
    "show_album": True,
    "show_status": True,
    "layer": "top",
    "wall_dim": 25,
    "wall_blend": "normal",
    "enter_style": "classic",
    "particle_speed": 100,
    "particle_size": 100,
    "ghost": 100,
    "toast_secs": 5,
    "card_glow": 60,
    "show_eq": True,
    "ui_anim": True,
    "anticipation": 120,
    "show_sync": True,
    "hotkeys": True,
    "hud_x": None,
    "hud_y": None,
    "hud_w": 520,
    "hud_h": 540,
}

AA = (
    QPainter.RenderHint.Antialiasing
    | QPainter.RenderHint.TextAntialiasing
    | QPainter.RenderHint.SmoothPixmapTransform
)

BLEND = {
    "normal": QPainter.CompositionMode.CompositionMode_SourceOver,
    "screen": QPainter.CompositionMode.CompositionMode_Screen,
    "overlay": QPainter.CompositionMode.CompositionMode_Overlay,
    "soft": QPainter.CompositionMode.CompositionMode_SoftLight,
    "add": QPainter.CompositionMode.CompositionMode_Plus,
}

QSS_TEMPLATE = """
QDialog{background:@BG@;}
QWidget#side{background:@BG2@;border-right:1px solid @LINE@;}
QWidget#main{background:@BG@;}
QLabel{color:@TX@;background:transparent;}
QLabel#brand{color:@ACC@;font-size:15px;font-weight:700;letter-spacing:5px;padding:20px 20px 8px 20px;}
QLabel#title{font-size:24px;font-weight:700;color:@TX@;padding:22px 28px 4px 28px;}
QLabel#section{color:@ACC@;font-size:11px;font-weight:700;letter-spacing:3px;padding:18px 0 6px 0;}
QLabel#rowlabel{color:@TX@;font-size:13px;}
QLabel#hint{color:@DIM@;font-size:11px;}
QLabel#nptitle{color:@TX@;font-size:12px;font-weight:700;}
QLabel#npartist{color:@DIM@;font-size:11px;}
QWidget#npcard{background:@SF@;border:1px solid @LINE@;border-radius:12px;}
QListWidget#nav{background:transparent;border:none;outline:none;padding:6px;}
QListWidget#nav::item{color:@DIM@;padding:12px 16px;border-radius:10px;margin:2px 6px;font-size:13px;}
QListWidget#nav::item:hover{background:@SF@;color:@TX@;}
QListWidget#nav::item:selected{background:@ACCA@;color:@TX@;border-left:3px solid @ACC@;}
QScrollArea{border:none;background:transparent;}
QScrollArea>QWidget>QWidget{background:transparent;}
QScrollBar:vertical{background:transparent;width:10px;margin:2px;}
QScrollBar::handle:vertical{background:@LINE@;border-radius:4px;min-height:30px;}
QScrollBar::handle:vertical:hover{background:@ACC@;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QPushButton{background:@SF@;border:1px solid @LINE@;border-radius:9px;padding:8px 16px;color:@TX@;font-size:12px;}
QPushButton:hover{border-color:@ACC@;}
QPushButton:disabled{color:@DIM@;border-color:@LINE@;}
QPushButton#primary{background:@ACC@;color:@BG@;border:none;font-weight:700;}
QPushButton#primary:hover{background:@SEC@;}
QPushButton#seg{border-radius:9px;padding:9px 18px;}
QPushButton#seg:checked{background:@ACC@;color:@BG@;border-color:@ACC@;font-weight:700;}
QPushButton#pos{background:@SF@;border:1px solid @LINE@;border-radius:7px;color:@DIM@;font-size:10px;font-weight:700;padding:0;}
QPushButton#pos:checked{background:@ACCA2@;border-color:@ACC@;color:@TX@;}
QSlider::groove:horizontal{height:5px;background:@LINE@;border-radius:2px;}
QSlider::sub-page:horizontal{background:@ACC@;border-radius:2px;}
QSlider::handle:horizontal{background:@TX@;width:14px;height:14px;margin:-5px 0;border-radius:7px;border:2px solid @ACC@;}
QComboBox,QSpinBox,QLineEdit{background:@SF@;border:1px solid @LINE@;border-radius:9px;padding:7px 10px;color:@TX@;font-size:12px;selection-background-color:@ACC@;selection-color:@BG@;}
QComboBox:hover,QSpinBox:hover,QLineEdit:hover{border-color:@ACC@;}
QComboBox::drop-down{border:none;width:24px;}
QComboBox QAbstractItemView{background:@BG2@;color:@TX@;border:1px solid @LINE@;selection-background-color:@ACCA@;outline:none;}
QSpinBox::up-button,QSpinBox::down-button{width:0;border:none;}
QToolTip{background:@BG2@;color:@TX@;border:1px solid @ACC@;padding:4px;}
QMenu{background:@BG2@;color:@TX@;border:1px solid @LINE@;border-radius:10px;padding:6px;}
QMenu::item{padding:8px 26px 8px 18px;border-radius:7px;}
QMenu::item:selected{background:@ACCA@;}
QMenu::separator{height:1px;background:@LINE@;margin:5px 8px;}
QMenu::indicator{width:14px;height:14px;}
"""


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def fmt_time(t):
    t = int(max(0, t))
    return f"{t // 60}:{t % 60:02d}"


def mix(a, b, k):
    return QColor.fromRgbF(
        clamp(a.redF() + (b.redF() - a.redF()) * k, 0.0, 1.0),
        clamp(a.greenF() + (b.greenF() - a.greenF()) * k, 0.0, 1.0),
        clamp(a.blueF() + (b.blueF() - a.blueF()) * k, 0.0, 1.0),
    )


def with_alpha(c, a):
    q = QColor(c)
    q.setAlpha(int(clamp(a, 0, 255)))
    return q


def fresh_defaults():
    return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}


WEIGHTS = {
    500: QFont.Weight.Medium,
    600: QFont.Weight.DemiBold,
    700: QFont.Weight.Bold,
    900: QFont.Weight.Black,
}


def lyric_style(cfg):
    return (
        int(cfg["lyric_weight"]),
        int(cfg["lyric_spacing"]),
        str(cfg["lyric_case"]),
        str(cfg["lyric_fill"]),
        int(cfg["lyric_outline"]),
        int(cfg["lyric_shadow"]),
        int(cfg["lyric_gap"]),
    )


def lyric_colors(cfg, pal):
    fill = QColor(pal.text)
    fill2 = None
    mode = cfg["lyric_fill"]
    if mode == "soft":
        fill2 = mix(pal.text, pal.secondary, 0.55)
    elif mode == "duo":
        white = QColor(255, 255, 255)
        fill = mix(pal.accent, white, 0.3)
        fill2 = mix(pal.secondary, white, 0.3)
    gc = {"secondary": pal.secondary, "text": pal.text}.get(cfg["glow_color"], pal.accent)
    return fill, fill2, QColor(gc)


class Config:
    def __init__(self):
        self.data = fresh_defaults()
        try:
            loaded = json.loads(CFG_PATH.read_text("utf-8"))
            for k, v in loaded.items():
                if k in DEFAULTS and (not isinstance(DEFAULTS[k], list) or isinstance(v, list)):
                    self.data[k] = v
        except Exception:
            pass

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def save(self):
        try:
            CFG_PATH.write_text(json.dumps(self.data, indent=2), "utf-8")
        except Exception:
            pass

    def reset(self):
        keep = {k: self.data[k] for k in ("hud_x", "hud_y", "hud_w", "hud_h")}
        self.data = fresh_defaults()
        self.data.update(keep)


class Theme:
    def __init__(self, cfg):
        self.cfg = cfg
        self.version = 0
        self.family = DEFAULT_FAMILY
        self.font_ok = True
        self.loaded_path = None
        self.loaded_family = None
        self.reload()

    def reload(self):
        path = self.cfg["font_path"]
        self.font_ok = True
        if path and os.path.isfile(path):
            if path != self.loaded_path:
                fid = QFontDatabase.addApplicationFont(path)
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                self.loaded_path = path
                self.loaded_family = fams[0] if fams else None
            if self.loaded_family:
                self.family = self.loaded_family
            else:
                self.family = DEFAULT_FAMILY
                self.font_ok = False
        else:
            self.family = DEFAULT_FAMILY
            if path:
                self.font_ok = False
        self.version += 1

    def font(self, px, weight=QFont.Weight.Medium, spacing=0.0):
        f = QFont(self.family)
        f.setPixelSize(max(6, int(px)))
        f.setWeight(weight)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        if spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return f


class Palette:
    __slots__ = ("accent", "secondary", "bg", "surface", "text", "dim")

    def __init__(self, accent, secondary, text=None):
        self.accent = QColor(accent)
        self.secondary = QColor(secondary)
        h = self.accent.hsvHueF()
        if h < 0:
            h = 0.0
        self.bg = QColor.fromHsvF(h % 1.0, 0.55, 0.075)
        self.surface = QColor.fromHsvF(h % 1.0, 0.45, 0.15)
        self.text = QColor(text) if text is not None else QColor.fromHsvF(h % 1.0, 0.07, 0.97)
        self.dim = mix(self.text, self.bg, 0.5)

    @staticmethod
    def blend(a, b, k):
        p = Palette.__new__(Palette)
        for n in Palette.__slots__:
            setattr(p, n, mix(getattr(a, n), getattr(b, n), k))
        return p

    def close_to(self, o):
        d = 0.0
        for n in ("accent", "secondary", "bg", "text"):
            a = getattr(self, n)
            b = getattr(o, n)
            d += abs(a.redF() - b.redF()) + abs(a.greenF() - b.greenF()) + abs(a.blueF() - b.blueF())
        return d < 0.012


def palette_from_image(img):
    small = img.scaled(
        40, 40, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    bins = [[0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(12)]
    for yy in range(40):
        for xx in range(40):
            h, s, v, _ = small.pixelColor(xx, yy).getHsvF()
            if h < 0 or s < 0.2 or v < 0.22:
                continue
            w = s * s * (0.3 + v)
            e = bins[int(h * 12) % 12]
            e[0] += w
            e[1] += math.cos(h * 6.2831853) * w
            e[2] += math.sin(h * 6.2831853) * w
            e[3] += s * w
            e[4] += v * w
    order = sorted(range(12), key=lambda i: bins[i][0], reverse=True)
    top = bins[order[0]]
    if top[0] < 1.5:
        return None

    def hsv_of(e):
        return (math.atan2(e[2], e[1]) / 6.2831853) % 1.0, e[3] / e[0], e[4] / e[0]

    h1, s1, v1 = hsv_of(top)
    acc = QColor.fromHsvF(h1, clamp(s1 * 1.1, 0.6, 1.0), clamp(v1 * 1.1 + 0.1, 0.85, 1.0))
    sec = None
    for i in order[1:]:
        e = bins[i]
        if e[0] < top[0] * 0.22:
            break
        h2, s2, v2 = hsv_of(e)
        dh = abs(h2 - h1)
        dh = min(dh, 1.0 - dh)
        if dh >= 0.09:
            sec = QColor.fromHsvF(h2, clamp(s2 * 1.1, 0.6, 1.0), clamp(v2 * 1.1 + 0.1, 0.85, 1.0))
            break
    if sec is None:
        sec = QColor.fromHsvF((h1 + 0.45) % 1.0, 0.8, 1.0)
    return Palette(acc, sec)


def build_qss(pal):
    def rgba(c, a):
        return f"rgba({c.red()},{c.green()},{c.blue()},{a})"

    bg2 = mix(pal.bg, pal.surface, 0.45)
    line = mix(pal.surface, pal.accent, 0.22)
    rep = {
        "@BG@": pal.bg.name(),
        "@BG2@": bg2.name(),
        "@SF@": pal.surface.name(),
        "@LINE@": line.name(),
        "@ACC@": pal.accent.name(),
        "@SEC@": pal.secondary.name(),
        "@TX@": pal.text.name(),
        "@DIM@": mix(pal.text, pal.bg, 0.42).name(),
        "@ACCA@": rgba(pal.accent, 60),
        "@ACCA2@": rgba(pal.accent, 90),
    }
    out = QSS_TEMPLATE
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


class Lyrics:
    def __init__(self, pairs):
        self.times = [t for t, _ in pairs]
        self.texts = [x for _, x in pairs]
        self.est = [0.5 + len(x) * 0.07 if x else 0.0 for x in self.texts]
        self.caps = []
        for x in self.texts:
            if x:
                units = max(len(x.split()), len(x) / 5.5)
                self.caps.append(clamp(1.3 + 0.4 * units, 2.2, 9.0))
            else:
                self.caps.append(0.0)

    def sing(self, i):
        est = self.est[i]
        if i + 1 < len(self.times):
            gap = self.times[i + 1] - self.times[i]
            return max(0.45, min(gap * 0.92, max(est * 2.2, 3.0)))
        return max(0.45, est * 1.5)

    def index_at(self, t):
        return bisect_right(self.times, t) - 1

    def span(self, i, hold):
        s = self.times[i]
        nxt = self.times[i + 1] if i + 1 < len(self.times) else s + 9.0
        return s, min(nxt, s + self.caps[i] * hold)


TS_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
WORD_RE = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>")
OFFSET_RE = re.compile(r"^\[offset:\s*([+-]?\d+)\]", re.I)


def parse_lrc(text):
    pairs = []
    offset = 0.0
    for raw in text.splitlines():
        raw = raw.strip()
        mo = OFFSET_RE.match(raw)
        if mo:
            offset = int(mo.group(1)) / 1000.0
            continue
        pos = 0
        stamps = []
        while True:
            m = TS_RE.match(raw, pos)
            if not m:
                break
            frac = m.group(3)
            sec = int(m.group(1)) * 60 + int(m.group(2))
            if frac:
                sec += int(frac) / (10 ** len(frac))
            stamps.append(sec)
            pos = m.end()
        if not stamps:
            continue
        body = WORD_RE.sub("", raw[pos:]).strip()
        if not body.strip("♪♫ -–—…"):
            body = ""
        for s in stamps:
            pairs.append((s - offset, body))
    if len(pairs) < 2 or not any(b for _, b in pairs):
        return None
    pairs.sort(key=lambda x: x[0])
    return Lyrics(pairs)


class NetError(Exception):
    pass


def http_json(path, params):
    url = f"{API}/{path}?{urlparse.urlencode(params)}"
    req = urlrequest.Request(url, headers={"User-Agent": UA})
    try:
        with urlrequest.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return None
        raise NetError(str(e))
    except (URLError, TimeoutError, ValueError, OSError) as e:
        raise NetError(str(e))


def clean_title(t):
    t = re.sub(
        r"\s*[\(\[][^\)\]]*(feat|ft\.|remaster|live|version|edit|mix|deluxe|bonus|mono|stereo|acoustic|radio|explicit|official|video|audio|lyrics)[^\)\]]*[\)\]]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+-\s+.*(remaster|version|edit|mix|live|mono|stereo|deluxe|single).*$", "", t, flags=re.I)
    return t.strip() or t


def clean_artist(a):
    a = re.sub(r"\s*-\s*topic$", "", a, flags=re.I)
    a = re.split(r"\s*(?:,|&|;|\sfeat\.?\s|\sft\.?\s|\sx\s)\s*", a, flags=re.I)[0]
    return a.strip()


def pick_best(items, dur, album=""):
    cands = [i for i in items if isinstance(i, dict) and i.get("syncedLyrics")]
    if not cands:
        return None
    al = (album or "").strip().lower()

    def gap(i):
        d = i.get("duration") or 0
        return abs(d - dur) if d else 6.0

    def score(i):
        s = gap(i) if dur > 0 else 0.0
        if al and str(i.get("albumName") or "").strip().lower() != al:
            s += 0.8
        return s

    cands.sort(key=score)
    if dur > 0 and gap(cands[0]) > 12:
        return None
    return cands[0]


def cache_file(title, artist, dur):
    h = hashlib.sha1(f"{artist.lower()}|{title.lower()}|{int(round(dur))}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.json"


def fetch_lyrics(title, artist, album, dur):
    cf = cache_file(title, artist, dur)
    try:
        cached = json.loads(cf.read_text("utf-8"))
        if cached.get("synced"):
            return parse_lrc(cached["synced"])
        if time.time() - cached.get("ts", 0) < 86400:
            return None
    except Exception:
        pass

    ct = clean_title(title)
    ca = clean_artist(artist)
    failed = False
    found = None
    cands = []
    dval = int(round(dur)) if dur > 0 else None

    def get_params(t, a, al):
        p = {"track_name": t, "artist_name": a}
        if al:
            p["album_name"] = al
        if dval:
            p["duration"] = dval
        return p

    attempts = [
        ("get", get_params(title, artist, album)),
        ("get", get_params(ct, ca, album)),
        ("get", get_params(ct, ca, "")),
        ("search", {"track_name": ct, "artist_name": ca}),
        ("search", {"q": f"{ca} {ct}"}),
    ]
    seen = set()
    for path, params in attempts:
        key = (path, tuple(sorted(params.items())))
        if key in seen:
            continue
        seen.add(key)
        try:
            data = http_json(path, params)
        except NetError:
            failed = True
            continue
        if not data:
            continue
        if path == "get":
            if isinstance(data, dict) and data.get("syncedLyrics"):
                cands.append(data)
        elif isinstance(data, list):
            cands.extend(i for i in data if isinstance(i, dict) and i.get("syncedLyrics"))
        best = pick_best(cands, dur, album)
        if best is not None and (dur <= 0 or abs((best.get("duration") or 0) - dur) <= 1.5):
            break

    found = pick_best(cands, dur, album)
    if found:
        try:
            cf.write_text(json.dumps({"synced": found["syncedLyrics"], "ts": time.time()}), "utf-8")
        except Exception:
            pass
        return parse_lrc(found["syncedLyrics"])
    if not failed:
        try:
            cf.write_text(json.dumps({"synced": None, "ts": time.time()}), "utf-8")
        except Exception:
            pass
    return None


async def read_thumb(ref):
    try:
        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0:
            return None
        buf = Buffer(size)
        await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
        try:
            data = bytes(memoryview(buf))
        except Exception:
            reader = DataReader.from_buffer(buf)
            arr = bytearray(buf.length)
            reader.read_bytes(arr)
            data = bytes(arr)
        try:
            stream.close()
        except Exception:
            pass
        return data if data else None
    except Exception:
        return None


class MediaWorker(QThread):
    media = pyqtSignal(dict)

    def __init__(self, cmds):
        super().__init__()
        self._run = True
        self.cmds = cmds
        self.session = None
        self.next_poll = 0.0
        self.last_key = None
        self.cover_sent = False
        self.tries = 0
        self.fb_pos = 0.0
        self.fb_t = time.monotonic()

    def stop(self):
        self._run = False

    def run(self):
        try:
            asyncio.run(self.loop())
        except Exception as e:
            print("Media worker stopped:", e)

    @staticmethod
    def pick(mgr):
        cur = mgr.get_current_session()
        try:
            if cur is not None and cur.get_playback_info().playback_status == PlaybackStatus.PLAYING:
                return cur
            for s in mgr.get_sessions():
                if s.get_playback_info().playback_status == PlaybackStatus.PLAYING:
                    return s
        except Exception:
            pass
        return cur

    @staticmethod
    def read_timeline(tl, playing, rate=1.0):
        start = tl.start_time.total_seconds()
        end = tl.end_time.total_seconds()
        pos = tl.position.total_seconds() - start
        dur = max(0.0, end - start)
        if playing:
            lu = tl.last_updated_time
            if lu is not None:
                try:
                    now = datetime.now(lu.tzinfo) if lu.tzinfo else datetime.now()
                    delta = (now - lu).total_seconds()
                    if delta > 0:
                        pos += delta * rate
                except Exception:
                    pass
        if dur > 0:
            pos = min(pos, dur)
        return max(0.0, pos), dur

    async def drain(self):
        while True:
            try:
                cmd, arg = self.cmds.get_nowait()
            except queue.Empty:
                return
            s = self.session
            if s is None:
                continue
            try:
                if cmd == "toggle":
                    await s.try_toggle_play_pause_async()
                elif cmd == "next":
                    await s.try_skip_next_async()
                elif cmd == "prev":
                    await s.try_skip_previous_async()
                elif cmd == "seek":
                    await s.try_change_playback_position_async(int(arg * 10000000))
                elif cmd == "shuffle":
                    await s.try_change_shuffle_active_async(bool(arg))
                elif cmd == "repeat":
                    await s.try_change_auto_repeat_mode_async(MediaPlaybackAutoRepeatMode(int(arg)))
            except Exception:
                pass
            self.next_poll = min(self.next_poll, time.monotonic() + 0.15)

    async def poll(self, mgr):
        session = self.pick(mgr)
        self.session = session
        active = False
        info = None
        status = None
        if session is not None:
            info = await session.try_get_media_properties_async()
            title = info.title or ""
            artist = info.artist or ""
            album = info.album_title or ""
            pb = session.get_playback_info()
            status = pb.playback_status
            if title and status not in (PlaybackStatus.STOPPED, PlaybackStatus.CLOSED):
                active = True
        if not active:
            self.last_key = None
            self.media.emit({"active": False})
            return
        playing = status == PlaybackStatus.PLAYING
        rate = 1.0
        try:
            rr = pb.playback_rate
            if rr:
                rate = clamp(float(rr), 0.25, 4.0)
        except Exception:
            pass
        pos, dur = self.read_timeline(session.get_timeline_properties(), playing, rate)
        key = f"{title}|{artist}|{album}"
        now = time.monotonic()
        if key != self.last_key:
            self.last_key = key
            self.cover_sent = False
            self.tries = 0
            self.fb_pos = 0.0
        if playing:
            self.fb_pos += now - self.fb_t
        self.fb_t = now
        if dur <= 0 and pos <= 0:
            pos = self.fb_pos
        can = {}
        try:
            c = pb.controls
            can = {
                "prev": bool(c.is_previous_enabled),
                "next": bool(c.is_next_enabled),
                "play": bool(c.is_play_enabled or c.is_pause_enabled or c.is_play_pause_toggle_enabled),
                "seek": bool(c.is_playback_position_enabled),
                "shuffle": bool(c.is_shuffle_enabled),
                "repeat": bool(c.is_repeat_enabled),
            }
        except Exception:
            can = {}
        shuffle = False
        repeat = 0
        try:
            sh = pb.is_shuffle_active
            shuffle = bool(sh) if sh is not None else False
            rm = pb.auto_repeat_mode
            repeat = int(rm) if rm is not None else 0
        except Exception:
            pass
        payload = {
            "active": True,
            "key": key,
            "title": title,
            "artist": artist,
            "album": album,
            "playing": playing,
            "pos": pos,
            "dur": dur,
            "cover": None,
            "can": can,
            "shuffle": shuffle,
            "repeat": repeat,
            "rate": rate,
        }
        if not self.cover_sent and self.tries < 8:
            self.tries += 1
            if info.thumbnail is not None:
                data = await read_thumb(info.thumbnail)
                if data:
                    self.cover_sent = True
                    payload["cover"] = data
        self.media.emit(payload)

    async def loop(self):
        mgr = await SessionManager.request_async()
        while self._run:
            try:
                await self.drain()
                now = time.monotonic()
                if now >= self.next_poll:
                    self.next_poll = now + 0.25
                    await self.poll(mgr)
            except Exception:
                pass
            await asyncio.sleep(0.07)


class VolumeControl:
    def __init__(self):
        self.iface = None
        self.available = False
        self.connect()

    def connect(self):
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER

            dev = AudioUtilities.GetSpeakers()
            iface = getattr(dev, "EndpointVolume", None)
            if iface is None:
                raw = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                iface = cast(raw, POINTER(IAudioEndpointVolume))
            self.iface = iface
            iface.GetMasterVolumeLevelScalar()
            self.available = True
        except Exception:
            self.iface = None
            self.available = False

    def get(self):
        if not self.available:
            return None
        for _ in range(2):
            try:
                return float(self.iface.GetMasterVolumeLevelScalar()), bool(self.iface.GetMute())
            except Exception:
                self.connect()
                if not self.available:
                    return None
        return None

    def set(self, v):
        if not self.available:
            return
        try:
            self.iface.SetMasterVolumeLevelScalar(float(clamp(v, 0.0, 1.0)), None)
            if v > 0:
                self.iface.SetMute(0, None)
        except Exception:
            self.connect()

    def set_mute(self, m):
        if not self.available:
            return
        try:
            self.iface.SetMute(1 if m else 0, None)
        except Exception:
            self.connect()


class State(QObject):
    track_changed = pyqtSignal()
    lyrics_changed = pyqtSignal()
    palette_changed = pyqtSignal()
    lyrics_ready = pyqtSignal(int, object)
    offset_changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.cmds = queue.Queue()
        self.active = False
        self.key = None
        self.title = ""
        self.artist = ""
        self.album = ""
        self.playing = False
        self.dur = 0.0
        self.cover = None
        self.cover_id = 0
        self.cover_pal = None
        self.lyrics = None
        self.status = "idle"
        self.can = {}
        self.shuffle = False
        self.repeat = 0
        self.anchor_pos = 0.0
        self.anchor_t = time.monotonic()
        self.hold_play = 0.0
        self.hold_ctrl = 0.0
        self.track_started = time.monotonic()
        self.fetch_id = 0
        self.rate = 1.0
        self.track_offsets = {}
        self.load_track_offsets()
        self.pal_target = self.compute_palette()
        self.pal_cur = Palette.blend(self.pal_target, self.pal_target, 0.0)
        self.pal_t = time.monotonic()
        self.lyrics_ready.connect(self.on_lyrics_ready)

    @property
    def palette(self):
        return self.pal_cur

    def compute_palette(self):
        if self.cfg["adaptive"] and self.cover_pal is not None:
            return self.cover_pal
        return Palette(self.cfg["accent"], self.cfg["secondary"], self.cfg["text"])

    def recompute_palette(self):
        self.pal_target = self.compute_palette()
        self.palette_changed.emit()

    def step_palette(self):
        now = time.monotonic()
        dt = min(0.1, now - self.pal_t)
        self.pal_t = now
        if self.pal_cur.close_to(self.pal_target):
            if self.pal_cur is not self.pal_target:
                self.pal_cur = Palette.blend(self.pal_target, self.pal_target, 0.0)
            return False
        self.pal_cur = Palette.blend(self.pal_cur, self.pal_target, 1.0 - math.exp(-dt * 5.0))
        return True

    def position(self):
        p = self.anchor_pos
        if self.playing:
            p += (time.monotonic() - self.anchor_t) * self.rate
        if self.dur > 0:
            p = min(p, self.dur)
        return max(0.0, p)

    def lyric_time(self):
        return self.position() + (self.cfg["offset_ms"] + self.track_ms() + self.cfg["anticipation"]) / 1000.0

    def active_lines(self):
        ly = self.lyrics
        if ly is None:
            return []
        t = self.lyric_time()
        hold = self.cfg["hold"] / 100.0
        fo = self.cfg["fade_ms"] / 1000.0
        fi = fo * 0.65
        idx = ly.index_at(t)
        out = []
        for i in range(max(0, idx - 2), idx + 1):
            if i >= len(ly.texts) or not ly.texts[i]:
                continue
            s, e = ly.span(i, hold)
            if t < s:
                continue
            eo = clamp((t - e) / fo, 0.0, 1.0)
            if eo >= 1.0:
                continue
            a = ease((t - s) / fi) * (1.0 - ease(eo))
            prog = clamp((t - s) / ly.sing(i), 0.0, 1.0)
            out.append((i, a, prog, t - s, eo))
        return out

    def set_cover(self, data):
        img = QImage.fromData(data)
        if img.isNull():
            return False
        self.cover = img
        self.cover_id += 1
        self.cover_pal = palette_from_image(img)
        self.recompute_palette()
        return True

    def on_media(self, d):
        if not d.get("active"):
            if self.active:
                self.active = False
                self.playing = False
                self.key = None
                self.lyrics = None
                self.status = "idle"
                self.cover = None
                self.cover_pal = None
                self.fetch_id += 1
                self.recompute_palette()
                self.track_changed.emit()
            return
        self.rate = float(d.get("rate", 1.0) or 1.0)
        changed = d["key"] != self.key
        notify = changed
        now = time.monotonic()
        if changed:
            self.key = d["key"]
            self.title = d["title"]
            self.artist = d["artist"]
            self.album = d["album"]
            self.dur = d["dur"]
            self.cover = None
            self.lyrics = None
            self.status = "loading"
            self.anchor_pos = d["pos"]
            self.anchor_t = now
            self.playing = d["playing"]
            self.active = True
            self.track_started = now
            self.request_lyrics()
        else:
            if d["dur"] > 0:
                self.dur = d["dur"]
            est = self.position()
            if now >= self.hold_play:
                if d["playing"] != self.playing or abs(d["pos"] - est) > 0.6:
                    self.anchor_pos = d["pos"]
                    self.anchor_t = now
                else:
                    self.anchor_pos += (d["pos"] - est) * 0.25
                self.playing = d["playing"]
        self.can = d.get("can", {})
        if now >= self.hold_ctrl:
            self.shuffle = d.get("shuffle", False)
            self.repeat = d.get("repeat", 0)
        if d.get("cover") and self.set_cover(d["cover"]):
            notify = True
        if notify:
            self.track_changed.emit()

    def request_lyrics(self):
        self.fetch_id += 1
        threading.Thread(
            target=self.fetch_worker,
            args=(self.fetch_id, self.title, self.artist, self.album, self.dur),
            daemon=True,
        ).start()

    def fetch_worker(self, fid, title, artist, album, dur):
        try:
            res = fetch_lyrics(title, artist, album, dur)
        except Exception:
            res = None
        self.lyrics_ready.emit(fid, res)

    def on_lyrics_ready(self, fid, res):
        if fid != self.fetch_id:
            return
        self.lyrics = res
        self.status = "found" if res else "none"
        self.lyrics_changed.emit()

    def toggle_play(self):
        now = time.monotonic()
        self.anchor_pos = self.position()
        self.anchor_t = now
        self.playing = not self.playing
        self.hold_play = now + 0.8
        self.cmds.put(("toggle", None))

    def skip_next(self):
        self.cmds.put(("next", None))

    def skip_prev(self):
        self.cmds.put(("prev", None))

    def seek(self, sec):
        now = time.monotonic()
        self.anchor_pos = clamp(sec, 0.0, self.dur if self.dur > 0 else sec)
        self.anchor_t = now
        self.hold_play = now + 0.8
        self.cmds.put(("seek", self.anchor_pos))

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.hold_ctrl = time.monotonic() + 1.2
        self.cmds.put(("shuffle", self.shuffle))

    def cycle_repeat(self):
        self.repeat = {0: 2, 2: 1, 1: 0}.get(self.repeat, 0)
        self.hold_ctrl = time.monotonic() + 1.2
        self.cmds.put(("repeat", self.repeat))

    def track_key(self):
        if not self.active:
            return None
        return f"{self.artist}|{self.title}|{int(round(self.dur))}".lower()

    def track_ms(self):
        if not self.cfg["auto_sync"]:
            return 0
        k = self.track_key()
        return int(self.track_offsets.get(k, 0)) if k else 0

    def sync_ms(self):
        if self.cfg["auto_sync"] and self.active:
            return self.track_ms()
        return int(self.cfg["offset_ms"])

    def snap(self, which):
        ly = self.lyrics
        if ly is None or not self.active:
            return False
        pos = self.position()
        idx = ly.index_at(self.lyric_time() - self.cfg["anticipation"] / 1000.0)
        target = idx + which
        if target < 0:
            return False
        while target < len(ly.texts) and not ly.texts[target]:
            target += 1
        if target >= len(ly.texts):
            return False
        total = int(round((ly.times[target] - pos) * 1000.0))
        if self.cfg["auto_sync"]:
            self.set_track_ms(total - int(self.cfg["offset_ms"]))
        else:
            self.cfg["offset_ms"] = int(clamp(total, -5000, 5000))
            self.offset_changed.emit()
        return True

    def load_track_offsets(self):
        try:
            data = json.loads(OFFS_PATH.read_text("utf-8"))
            if isinstance(data, dict):
                self.track_offsets = {str(k): int(v) for k, v in data.items()}
        except Exception:
            self.track_offsets = {}

    def set_track_ms(self, v):
        k = self.track_key()
        if not k:
            return
        v = int(clamp(v, -5000, 5000))
        if v:
            self.track_offsets[k] = v
        else:
            self.track_offsets.pop(k, None)
        try:
            OFFS_PATH.write_text(json.dumps(self.track_offsets, indent=2, ensure_ascii=False), "utf-8")
        except Exception:
            pass
        self.offset_changed.emit()


class LineCache:
    def __init__(self, cap=96):
        self.d = OrderedDict()
        self.cap = cap

    def get(self, key, factory):
        v = self.d.get(key)
        if v is not None:
            self.d.move_to_end(key)
            return v
        v = factory()
        self.d[key] = v
        if len(self.d) > self.cap:
            self.d.popitem(last=False)
        return v

    def clear(self):
        self.d.clear()


def wrap_text(text, fm, maxw):
    spaced = " " in text
    tokens = text.split(" ") if spaced else list(text)
    sep = " " if spaced else ""

    def greedy(limit):
        out = []
        cur = ""
        for tk in tokens:
            cand = cur + sep + tk if cur else tk
            if fm.horizontalAdvance(cand) <= limit or not cur:
                cur = cand
            else:
                out.append(cur)
                cur = tk
        if cur:
            out.append(cur)
        return out

    rows = greedy(maxw)
    if len(rows) > 1:
        hi = int(maxw)
        lo = min(int(max(fm.horizontalAdvance(t) for t in tokens)), hi)
        n = len(rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if len(greedy(mid)) <= n:
                hi = mid
            else:
                lo = mid + 1
        rows = greedy(hi)
    return rows or [text]


def render_line(text, font, fill, glowc, glow, maxw, dpr, scan, align, sty=None, fill2=None):
    gap = sty[6] / 100.0 if sty else 1.0
    outline = float(sty[4]) if sty else 0.0
    shadow = sty[5] / 100.0 if sty else 0.0
    fm = QFontMetrics(font)
    rows = wrap_text(text, fm, maxw)
    lh = max(1, int(fm.height() * gap))
    r = font.pixelSize() * 0.5 * glow
    pad = int(r) + 6 + int(outline) + (int(font.pixelSize() * 0.35) if shadow > 0.01 else 0)
    tw = max(fm.horizontalAdvance(x) for x in rows)
    w = tw + pad * 2
    h = lh * len(rows) + pad * 2
    pm = QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(AA)
    path = QPainterPath()
    meta = []
    y = pad + fm.ascent()
    top = float(pad)
    for row in rows:
        rw = fm.horizontalAdvance(row)
        if align == "l":
            rx = float(pad)
        elif align == "r":
            rx = float(w - pad - rw)
        else:
            rx = (w - rw) / 2.0
        path.addText(rx, y, font, row)
        meta.append((rx, top, float(rw), float(lh)))
        y += lh
        top += lh
    if shadow > 0.01:
        sp = font.pixelSize()
        p.save()
        p.translate(0.0, max(1.0, sp * 0.07))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for wm, a in ((0.34, 0.07), (0.2, 0.12), (0.1, 0.18)):
            c = QColor(0, 0, 0)
            c.setAlphaF(min(1.0, a * shadow * 2.0))
            pen = QPen(c, max(1.0, sp * wm))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        c = QColor(0, 0, 0)
        c.setAlphaF(min(1.0, 0.5 * shadow))
        p.setBrush(c)
        p.drawPath(path)
        p.restore()
    if glow > 0.01:
        p.setBrush(Qt.BrushStyle.NoBrush)
        for mul, a in ((2.0, 0.05), (1.3, 0.09), (0.8, 0.15), (0.4, 0.26)):
            c = QColor(glowc)
            c.setAlphaF(min(1.0, a * (0.6 + glow)))
            pen = QPen(c, max(1.0, r * mul))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(path)
    if outline > 0.01:
        pen = QPen(QColor(0, 0, 0, 185), outline * 2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    if fill2 is not None:
        g = QLinearGradient(float(pad), 0.0, float(max(pad + 1, w - pad)), 0.0)
        g.setColorAt(0.0, fill)
        g.setColorAt(1.0, fill2)
        p.setBrush(QBrush(g))
    else:
        p.setBrush(fill)
    p.drawPath(path)
    if scan:
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        c = QColor(0, 0, 0, 90)
        yy = 0
        while yy < h:
            p.fillRect(QRectF(0, yy, w, 1), c)
            yy += 3
    p.end()
    return pm, float(w), float(h), meta, float(pad)


def cached_line(cache, theme, text, px, fill, glowc, glow, maxw, dpr, scan, align, sty=None, fill2=None):
    if sty:
        weight = WEIGHTS.get(sty[0], QFont.Weight.DemiBold)
        spacing = float(sty[1])
        if sty[2] == "upper":
            text = text.upper()
        elif sty[2] == "lower":
            text = text.lower()
    else:
        weight = QFont.Weight.DemiBold
        spacing = 0.0
    key = (
        theme.version,
        text,
        int(px),
        fill.rgba(),
        glowc.rgba(),
        int(glow * 100),
        int(maxw),
        int(dpr * 100),
        scan,
        align,
        sty,
        fill2.rgba() if fill2 is not None else 0,
    )
    return cache.get(
        key,
        lambda: render_line(text, theme.font(px, weight, spacing), fill, glowc, glow, maxw, dpr, scan, align, sty, fill2),
    )


def draw_karaoke(p, dim, bright, prog, alpha, karaoke, flick=1.0, dim_a=0.42):
    ox = -bright[1] / 2.0
    oy = -bright[2] / 2.0
    if karaoke and dim is not None:
        p.setOpacity(clamp(alpha * dim_a, 0.0, 1.0))
        p.drawPixmap(QPointF(-dim[1] / 2.0, -dim[2] / 2.0), dim[0])
        pad = bright[4]
        rows = bright[3]
        total = sum(r[2] for r in rows) or 1.0
        used = prog * total
        path = QPainterPath()
        last = len(rows) - 1
        for k, (rx, ry, rw, rh) in enumerate(rows):
            take = clamp(used, 0.0, rw)
            used -= rw
            if take <= 0:
                continue
            width = take + pad + (pad if take >= rw - 0.5 else 0.0)
            y0 = 0.0 if k == 0 else ry
            y1 = bright[2] if k == last else ry + rh
            path.addRect(QRectF(ox + rx - pad, oy + y0, width, y1 - y0))
        if not path.isEmpty():
            p.setClipPath(path)
            p.setOpacity(clamp(alpha * flick, 0.0, 1.0))
            p.drawPixmap(QPointF(ox, oy), bright[0])
            p.setClipping(False)
    else:
        p.setOpacity(clamp(alpha * flick, 0.0, 1.0))
        p.drawPixmap(QPointF(ox, oy), bright[0])


def icon_pen(col, w=1.7):
    pen = QPen(col, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def icon_play(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    path = QPainterPath()
    path.moveTo(-4, -7)
    path.lineTo(7, 0)
    path.lineTo(-4, 7)
    path.closeSubpath()
    p.setPen(icon_pen(col, 1.6))
    p.setBrush(col)
    p.drawPath(path)
    p.restore()


def icon_pause(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(QRectF(-6, -7, 4.2, 14), 1.4, 1.4)
    p.drawRoundedRect(QRectF(1.8, -7, 4.2, 14), 1.4, 1.4)
    p.restore()


def icon_skip(p, cx, cy, s, col, flip=False, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(-k if flip else k, k)
    path = QPainterPath()
    path.moveTo(7, -6.5)
    path.lineTo(-3.5, 0)
    path.lineTo(7, 6.5)
    path.closeSubpath()
    p.setPen(icon_pen(col, 1.4))
    p.setBrush(col)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(-8, -6.5, 2.6, 13), 1.1, 1.1)
    p.restore()


def icon_prev(p, cx, cy, s, col, **kw):
    icon_skip(p, cx, cy, s, col, False)


def icon_next(p, cx, cy, s, col, **kw):
    icon_skip(p, cx, cy, s, col, True)


def icon_shuffle(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    a = QPainterPath()
    a.moveTo(-8, -4)
    a.lineTo(-4, -4)
    a.cubicTo(0, -4, 0, 4, 4, 4)
    a.lineTo(5.5, 4)
    b = QPainterPath()
    b.moveTo(-8, 4)
    b.lineTo(-4, 4)
    b.cubicTo(0, 4, 0, -4, 4, -4)
    b.lineTo(5.5, -4)
    p.setPen(icon_pen(col, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(a)
    p.drawPath(b)
    p.setBrush(col)
    for yy in (-4, 4):
        tri = QPainterPath()
        tri.moveTo(5, yy - 3)
        tri.lineTo(9, yy)
        tri.lineTo(5, yy + 3)
        tri.closeSubpath()
        p.drawPath(tri)
    p.restore()


def icon_repeat(p, cx, cy, s, col, mode=0, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    p.setPen(icon_pen(col, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-7, -4.5, 14, 9), 3.2, 3.2)
    p.setBrush(col)
    t1 = QPainterPath()
    t1.moveTo(1, -7.8)
    t1.lineTo(5.2, -4.5)
    t1.lineTo(1, -1.2)
    t1.closeSubpath()
    t2 = QPainterPath()
    t2.moveTo(-1, 1.2)
    t2.lineTo(-5.2, 4.5)
    t2.lineTo(-1, 7.8)
    t2.closeSubpath()
    p.drawPath(t1)
    p.drawPath(t2)
    if mode == 1:
        f = QFont("Segoe UI", 1)
        f.setPixelSize(8)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(-4, -4, 8, 8), Qt.AlignmentFlag.AlignCenter, "1")
    p.restore()


def icon_speaker(p, cx, cy, s, col, level=1.0, muted=False, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    body = QPainterPath()
    body.moveTo(-8, -2.8)
    body.lineTo(-4, -2.8)
    body.lineTo(0.5, -6.5)
    body.lineTo(0.5, 6.5)
    body.lineTo(-4, 2.8)
    body.lineTo(-8, 2.8)
    body.closeSubpath()
    p.setPen(icon_pen(col, 1.2))
    p.setBrush(col)
    p.drawPath(body)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(icon_pen(col, 1.6))
    if muted or level <= 0.01:
        p.drawLine(QPointF(3.5, -3), QPointF(8.5, 3))
        p.drawLine(QPointF(8.5, -3), QPointF(3.5, 3))
    else:
        w1 = QPainterPath()
        w1.moveTo(3.5, -3)
        w1.cubicTo(5.5, -1.5, 5.5, 1.5, 3.5, 3)
        p.drawPath(w1)
        if level > 0.5:
            w2 = QPainterPath()
            w2.moveTo(5.8, -6)
            w2.cubicTo(9.5, -3, 9.5, 3, 5.8, 6)
            p.drawPath(w2)
    p.restore()


def set_click_through(widget, on):
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        u.SetWindowLongW.restype = ctypes.c_long
        hwnd = int(widget.winId())
        style = u.GetWindowLongW(hwnd, -20)
        new = (style | 0x20) if on else (style & ~0x20)
        if new != style:
            u.SetWindowLongW(hwnd, -20, new)
    except Exception:
        pass


def desktop_host():
    u = ctypes.windll.user32
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowExW.restype = wintypes.HWND
    u.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    progman = u.FindWindowW("Progman", None)
    if not progman:
        return None
    res = ctypes.c_size_t(0)
    u.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(res))
    child = u.FindWindowExW(progman, None, "WorkerW", None)
    if child:
        return child
    found = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, lparam):
        if u.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            w = u.FindWindowExW(None, hwnd, "WorkerW", None)
            if w:
                found.append(w)
        return True

    u.EnumWindows.argtypes = [proc_type, wintypes.LPARAM]
    u.EnumWindows(proc_type(visit), 0)
    return found[0] if found else None


def desktop_attach(hwnd):
    try:
        u = ctypes.windll.user32
        host = desktop_host()
        if not host:
            return None
        u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        u.SetParent.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        u.SetWindowLongW.restype = ctypes.c_long
        u.SetParent(hwnd, host)
        style = u.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
        style = (style & ~0x80000000) | 0x40000000
        u.SetWindowLongW(hwnd, -16, style)
        return host
    except Exception:
        return None


def desktop_place(hwnd, host, x, y, w, h):
    try:
        u = ctypes.windll.user32
        r = wintypes.RECT()
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect(host, ctypes.byref(r))
        u.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        u.SetWindowPos(hwnd, None, int(x - r.left), int(y - r.top), int(w), int(h), 0x34)
    except Exception:
        pass


def wallpaper_path():
    try:
        buf = ctypes.create_unicode_buffer(520)
        ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buf, 0)
        return buf.value
    except Exception:
        return ""


def wallpaper_style():
    mode, tile, rgb = 10, 0, (0, 0, 0)
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            mode = int(winreg.QueryValueEx(k, "WallpaperStyle")[0])
            tile = int(winreg.QueryValueEx(k, "TileWallpaper")[0])
    except Exception:
        pass
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors") as k:
            parts = [int(x) for x in str(winreg.QueryValueEx(k, "Background")[0]).split()]
            if len(parts) == 3:
                rgb = tuple(clamp(x, 0, 255) for x in parts)
    except Exception:
        pass
    return mode, tile, rgb


def build_wallpaper(img, style, W, H, dpr, org, virt):
    mode, tile, rgb = style
    pw = max(1, int(round(W * dpr)))
    ph = max(1, int(round(H * dpr)))
    pm = QPixmap(pw, ph)
    pm.fill(QColor(*rgb))
    if img is not None:
        q = QPainter(pm)
        q.setRenderHints(AA)
        smooth = Qt.TransformationMode.SmoothTransformation
        if mode == 22:
            vw = max(1, int(virt.width() * dpr))
            vh = max(1, int(virt.height() * dpr))
            sc = img.scaled(vw, vh, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
            dx = -(org.x() - virt.x()) * dpr - (sc.width() - vw) / 2.0
            dy = -(org.y() - virt.y()) * dpr - (sc.height() - vh) / 2.0
            q.drawImage(QPointF(dx, dy), sc)
        elif mode == 2:
            q.drawImage(QRectF(0, 0, pw, ph), img)
        elif mode == 6:
            sc = img.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatio, smooth)
            q.drawImage((pw - sc.width()) // 2, (ph - sc.height()) // 2, sc)
        elif mode == 0 and tile:
            iw = max(1, img.width())
            ih = max(1, img.height())
            for yy in range(0, ph, ih):
                for xx in range(0, pw, iw):
                    q.drawImage(xx, yy, img)
        elif mode == 0:
            q.drawImage((pw - img.width()) // 2, (ph - img.height()) // 2, img)
        else:
            sc = img.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
            q.drawImage((pw - sc.width()) // 2, (ph - sc.height()) // 2, sc)
        q.end()
    pm.setDevicePixelRatio(dpr)
    return pm


class Hud(QWidget):
    MARGIN = 12
    COMPACT_H = 246

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.cache = LineCache()
        self.cover_pm = None
        self.cover_sig = None
        self.bd_pm = None
        self.bd_sig = None
        self.last = time.monotonic()
        self.drag = None
        self.resize_from = None
        self.dirty = True
        self.ct_applied = None
        self.lock_timer = QTimer(self)
        self.lock_timer.setInterval(16)
        self.lock_timer.timeout.connect(self.poll_lock)
        self.hits = []
        self.rects = {}
        self.hover = None
        self.pressed = None
        self.seeking = False
        self.seek_frac = 0.0
        self.vol_drag = False
        self.hv = {}
        self.appear = 0.0
        self.track_t = time.monotonic()
        self.mouse_x = 0.0
        self.compact = self.cfg["mode"] == "both"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.apply_flags()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(int(min(self.cfg["hud_w"], g.width() - 48)), int(min(self.cfg["hud_h"], g.height() - 48)))
        self.apply_size_limits()
        self.restore_pos()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.set_fps()
        self.state.track_changed.connect(self.on_track)
        self.state.lyrics_changed.connect(self.mark_dirty)
        self.state.offset_changed.connect(self.mark_dirty)

    def mark_dirty(self):
        self.dirty = True

    def on_track(self):
        self.track_t = time.monotonic()
        self.dirty = True

    def apply_size_limits(self):
        if self.compact:
            self.setMinimumSize(440, self.COMPACT_H)
            self.setMaximumSize(16777215, self.COMPACT_H)
            self.resize(self.width(), self.COMPACT_H)
        else:
            self.setMaximumSize(16777215, 16777215)
            self.setMinimumSize(440, 400)
            self.resize(self.width(), max(400, int(self.cfg["hud_h"])))

    def apply_flags(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        was = self.isVisible()
        self.setWindowFlags(flags)
        if was:
            self.show()

    def restore_pos(self):
        x, y = self.cfg["hud_x"], self.cfg["hud_y"]
        ok = False
        if x is not None and y is not None:
            for s in QGuiApplication.screens():
                if s.geometry().contains(QPoint(int(x) + 40, int(y) + 40)):
                    ok = True
        if not ok:
            self.reset_pos()
            return
        self.move(int(x), int(y))

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)
        self.save_geometry()

    def save_geometry(self):
        self.cfg["hud_x"] = self.x()
        self.cfg["hud_y"] = self.y()
        self.cfg["hud_w"] = self.width()
        if not self.compact:
            self.cfg["hud_h"] = self.height()
        self.cfg.save()

    def set_fps(self):
        self.timer.setInterval(int(1000 / max(10, int(self.cfg["fps"]))))

    def refresh(self):
        self.cache.clear()
        self.cover_sig = None
        self.bd_sig = None
        compact = self.cfg["mode"] == "both"
        if compact != self.compact:
            self.compact = compact
            self.apply_size_limits()
        self.sync_lock()
        self.set_fps()
        self.dirty = True
        self.update()

    def showEvent(self, e):
        self.last = time.monotonic()
        self.appear = 0.0 if self.cfg["ui_anim"] else 1.0
        self.timer.start()
        super().showEvent(e)
        self.sync_lock()

    def hideEvent(self, e):
        self.timer.stop()
        self.lock_timer.stop()
        super().hideEvent(e)

    def moveEvent(self, e):
        super().moveEvent(e)
        h = getattr(self.ctl, "holo", None)
        if h is not None:
            h.dirty = True

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = getattr(self.ctl, "holo", None)
        if h is not None:
            h.dirty = True

    def sync_lock(self):
        self.ct_applied = None
        if self.cfg["click_through"]:
            self.drag = None
            self.resize_from = None
            if self.isVisible():
                self.lock_timer.start()
        else:
            self.lock_timer.stop()
            if self.isVisible():
                set_click_through(self, False)
            self.ct_applied = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.dirty = True

    def poll_lock(self):
        if not self.isVisible():
            return
        want = False
        if self.cfg["click_through"]:
            busy = self.seeking or self.vol_drag or self.pressed is not None
            if not busy:
                want = self.hit_at(QPointF(self.mapFromGlobal(QCursor.pos()))) is None
        if want != self.ct_applied:
            self.ct_applied = want
            set_click_through(self, want)
            if want and self.hover is not None:
                self.hover = None
                self.dirty = True

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        busy = self.state.step_palette()
        ui = bool(self.cfg["ui_anim"])
        for name in set(self.hv) | {self.hover}:
            if name is None:
                continue
            target = 1.0 if name == self.hover else 0.0
            cur = self.hv.get(name, 0.0)
            if ui:
                new = cur + (target - cur) * (1.0 - math.exp(-dt * 16.0))
                if abs(target - new) < 0.01:
                    new = target
            else:
                new = target
            if new != cur:
                busy = True
            if new <= 0.0 and target == 0.0:
                self.hv.pop(name, None)
            else:
                self.hv[name] = new
        if self.appear < 1.0:
            self.appear = min(1.0, self.appear + dt * 3.4) if ui else 1.0
            busy = True
        if now - self.track_t < 1.0:
            busy = True
        if self.state.playing or busy or self.dirty or self.seeking or self.vol_drag:
            self.dirty = False
            self.update()

    def add_hit(self, name, rect):
        r = QRectF(rect)
        self.hits.append((r, name))
        self.rects[name] = r

    def hit_at(self, pos):
        for r, name in self.hits:
            if r.contains(pos):
                return name
        return None

    def in_grip(self, pos):
        return not self.cfg["click_through"] and pos.x() > self.width() - 30 and pos.y() > self.height() - 30

    def frac_in(self, name, x):
        r = self.rects.get(name)
        if r is None or r.width() <= 0:
            return 0.0
        return clamp((x - r.left()) / r.width(), 0.0, 1.0)

    def apply_vol(self, x):
        self.ctl.set_volume(self.frac_in("vol", x))
        self.dirty = True

    def activate(self, name):
        st = self.state
        actions = {
            "play": st.toggle_play,
            "prev": st.skip_prev,
            "next": st.skip_next,
            "shuffle": st.toggle_shuffle,
            "repeat": st.cycle_repeat,
            "mute": self.ctl.toggle_mute,
            "gear": self.ctl.open_settings,
            "mode": self.ctl.cycle_mode,
            "close": self.ctl.hide_all,
            "sync_m": lambda: self.ctl.nudge(-100),
            "sync_p": lambda: self.ctl.nudge(100),
            "sync_r": lambda: self.ctl.nudge(None),
        }
        fn = actions.get(name)
        if fn:
            fn()
        self.dirty = True

    def mousePressEvent(self, e):
        gp = e.globalPosition().toPoint()
        pos = e.position()
        if e.button() == Qt.MouseButton.LeftButton:
            if self.in_grip(pos):
                self.resize_from = (gp, self.size())
                return
            name = self.hit_at(pos)
            if name == "seek":
                if self.state.dur > 0 and self.state.can.get("seek", True):
                    self.seeking = True
                    self.seek_frac = self.frac_in("seek", pos.x())
            elif name == "vol":
                self.vol_drag = True
                self.apply_vol(pos.x())
            elif name:
                self.pressed = name
            elif not self.cfg["click_through"]:
                self.drag = gp - self.frameGeometry().topLeft()
            self.dirty = True
        elif e.button() == Qt.MouseButton.RightButton:
            self.ctl.menu.exec(gp)

    def mouseMoveEvent(self, e):
        gp = e.globalPosition().toPoint()
        pos = e.position()
        self.mouse_x = pos.x()
        if self.resize_from is not None:
            origin, size = self.resize_from
            d = gp - origin
            self.resize(
                max(self.minimumWidth(), size.width() + d.x()),
                max(self.minimumHeight(), size.height() + d.y()),
            )
        elif self.seeking:
            self.seek_frac = self.frac_in("seek", pos.x())
        elif self.vol_drag:
            self.apply_vol(pos.x())
        elif self.drag is not None:
            self.move(gp - self.drag)
        else:
            name = self.hit_at(pos)
            if name != self.hover:
                self.hover = name
                self.dirty = True
            if self.in_grip(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif name:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e):
        pos = e.position()
        if self.seeking:
            self.seeking = False
            self.state.seek(self.seek_frac * self.state.dur)
        if self.vol_drag:
            self.vol_drag = False
        if self.pressed is not None:
            if self.hit_at(pos) == self.pressed:
                self.activate(self.pressed)
            self.pressed = None
        if self.drag is not None or self.resize_from is not None:
            self.drag = None
            self.resize_from = None
            self.save_geometry()
        self.dirty = True

    def leaveEvent(self, e):
        if self.hover is not None:
            self.hover = None
            self.dirty = True
        super().leaveEvent(e)

    def wheelEvent(self, e):
        step = 0.03 if e.angleDelta().y() > 0 else -0.03
        self.ctl.change_volume(step)
        self.dirty = True

    def chip_text(self):
        st = self.state
        if not st.active:
            return "Idle"
        parts = []
        if not st.playing:
            parts.append("Paused")
        parts.append({"loading": "Searching lyrics", "found": "Synced lyrics", "none": "No synced lyrics"}.get(st.status, ""))
        return "  ·  ".join(x for x in parts if x)

    def backdrop(self, card):
        img = self.state.cover
        if img is None:
            return None
        sig = (self.state.cover_id, int(card.width()), int(card.height()))
        if sig != self.bd_sig:
            tiny = img.scaled(
                8, 8, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            big = tiny.scaled(
                max(2, int(card.width() / 3)),
                max(2, int(card.height() / 3)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.bd_pm = QPixmap.fromImage(big)
            self.bd_sig = sig
        return self.bd_pm

    def paint_card(self, p, card, pal):
        rad = float(self.cfg["card_radius"])
        path = QPainterPath()
        path.addRoundedRect(card, rad, rad)
        g = QLinearGradient(card.topLeft(), card.bottomRight())
        g.setColorAt(0, with_alpha(pal.bg.lighter(125), 240))
        g.setColorAt(1, with_alpha(pal.bg.darker(150), 245))
        p.fillPath(path, QBrush(g))
        bd = self.backdrop(card)
        if bd is not None:
            p.save()
            p.setClipPath(path)
            p.setOpacity(p.opacity() * self.cfg["backdrop"] / 100.0)
            p.drawPixmap(card.toRect(), bd)
            p.restore()
        shade = QLinearGradient(card.topLeft(), card.bottomLeft())
        shade.setColorAt(0, with_alpha(pal.bg, 40))
        shade.setColorAt(0.55, with_alpha(pal.bg, 150))
        shade.setColorAt(1, with_alpha(pal.bg.darker(160), 215))
        p.fillPath(path, QBrush(shade))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(pal.accent, 20), 6))
        p.drawPath(path)
        glow = self.cfg["card_glow"] / 100.0
        if glow > 0.01:
            ang = (time.monotonic() * 45.0) % 360.0 if self.state.playing else 40.0
            cg = QConicalGradient(card.center(), ang)
            cg.setColorAt(0.0, with_alpha(pal.accent, int(235 * glow)))
            cg.setColorAt(0.22, with_alpha(pal.secondary, int(215 * glow)))
            cg.setColorAt(0.5, with_alpha(pal.accent, int(30 * glow)))
            cg.setColorAt(0.78, with_alpha(pal.secondary, int(215 * glow)))
            cg.setColorAt(1.0, with_alpha(pal.accent, int(235 * glow)))
            p.setPen(QPen(QBrush(cg), 1.6))
        else:
            p.setPen(QPen(with_alpha(pal.accent, 150), 1.0))
        p.drawPath(path)

    def paint_cover(self, p, r, pal, dpr):
        path = QPainterPath()
        path.addRoundedRect(r, 13, 13)
        p.save()
        p.setClipPath(path)
        img = self.state.cover
        if img is not None:
            sig = (self.state.cover_id, int(r.width()), int(dpr * 100))
            if sig != self.cover_sig:
                s = max(1, int(r.width() * dpr))
                sc = img.scaled(
                    s, s, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
                )
                sc = sc.copy((sc.width() - s) // 2, (sc.height() - s) // 2, s, s)
                self.cover_pm = QPixmap.fromImage(sc)
                self.cover_pm.setDevicePixelRatio(dpr)
                self.cover_sig = sig
            p.drawPixmap(r.topLeft(), self.cover_pm)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, with_alpha(pal.accent, 160))
            g.setColorAt(1, with_alpha(pal.secondary, 100))
            p.fillRect(r, QBrush(g))
            p.setFont(QFont("Segoe UI Symbol", 30, QFont.Weight.Bold))
            p.setPen(QColor(255, 255, 255, 200))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "♪")
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(pal.text, 55), 1.0))
        p.drawPath(path)

    def paint_progress(self, p, x0, x1, py, pal):
        st = self.state
        dur = st.dur
        frac = self.seek_frac if self.seeking else (clamp(st.position() / dur, 0.0, 1.0) if dur > 0 else 0.0)
        pos = frac * dur if dur > 0 else st.position()
        hv = 1.0 if self.seeking else self.hv.get("seek", 0.0)
        th = 4.0 + 3.0 * hv
        bar = QRectF(x0, py + 2.0 - th / 2.0, x1 - x0, th)
        hit = QRectF(x0, py - 9, x1 - x0, 24)
        self.add_hit("seek", hit)
        self.rects["seek"] = hit
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(bar, th / 2.0, th / 2.0)
        if frac > 0:
            fill = QRectF(x0, bar.top(), bar.width() * frac, th)
            g = QLinearGradient(fill.left(), 0, fill.right() + 1, 0)
            g.setColorAt(0, pal.accent)
            g.setColorAt(1, pal.secondary)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(fill, th / 2.0, th / 2.0)
            if hv > 0.02:
                p.setBrush(with_alpha(pal.secondary, int(70 * hv)))
                p.drawEllipse(QPointF(fill.right(), py + 2), 5.0 + 5.0 * hv, 5.0 + 5.0 * hv)
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(fill.right(), py + 2), 2.0 + 3.5 * hv, 2.0 + 3.5 * hv)
        if hv > 0.05 and dur > 0:
            mf = self.seek_frac if self.seeking else self.frac_in("seek", self.mouse_x)
            fb = self.theme.font(11, QFont.Weight.DemiBold)
            fmb = QFontMetrics(fb)
            label = fmt_time(mf * dur)
            bw = fmb.horizontalAdvance(label) + 16.0
            bx = clamp(x0 + (x1 - x0) * mf - bw / 2.0, x0 - 6.0, x1 - bw + 6.0)
            br = QRectF(bx, py - 30.0 + (1.0 - hv) * 6.0, bw, 20.0)
            p.setBrush(with_alpha(pal.bg, int(235 * hv)))
            p.setPen(QPen(with_alpha(pal.accent, int(160 * hv)), 1.0))
            p.drawRoundedRect(br, 7, 7)
            p.setFont(fb)
            p.setPen(with_alpha(pal.text, int(240 * hv)))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, label)
        f = self.theme.font(11, QFont.Weight.Medium)
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 140))
        base = py + 15 + fm.ascent()
        p.drawText(QPointF(x0, base), fmt_time(pos))
        right = fmt_time(dur) if dur > 0 else "--:--"
        p.drawText(QPointF(x1 - fm.horizontalAdvance(right), base), right)

    def button(self, p, name, cx, cy, size, draw, pal, enabled=True, active=False, **kw):
        hv = self.hv.get(name, 0.0)
        press = 0.9 if self.pressed == name else 1.0
        if enabled:
            self.add_hit(name, QRectF(cx - size * 0.95, cy - size * 0.95, size * 1.9, size * 1.9))
            if hv > 0.01:
                rr = size * (0.8 + 0.15 * hv)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pal.text, int(38 * hv)))
                p.drawEllipse(QPointF(cx, cy), rr, rr)
        if not enabled:
            col = with_alpha(pal.text, 70)
        elif active:
            col = QColor(pal.accent)
        else:
            col = with_alpha(mix(pal.text, pal.accent, 0.5 * hv), 215 + int(40 * hv))
        draw(p, cx, cy, size * (1.0 + 0.14 * hv) * press, col, **kw)

    def paint_controls(self, p, x0, x1, cy, pal):
        st = self.state
        cfg = self.cfg
        can = st.can
        vol_on = bool(cfg["show_volume"]) and self.ctl.volume.available
        vw = clamp((x1 - x0) * 0.22, 64, 120)
        right_start = x1 - ((vw + 42) if vol_on else 0)
        mid = (x0 + right_start) / 2.0
        self.button(p, "shuffle", mid - 100, cy, 14, icon_shuffle, pal, can.get("shuffle", True), st.shuffle)
        self.button(p, "prev", mid - 52, cy, 18, icon_prev, pal, can.get("prev", True))
        hp = self.hv.get("play", 0.0)
        glow_r = 36.0 + 6.0 * hp
        r = 23.0 * (1.0 + 0.07 * hp) * (0.94 if self.pressed == "play" else 1.0)
        rg = QRadialGradient(mid, cy, glow_r)
        rg.setColorAt(0, with_alpha(pal.accent, int(60 + 50 * hp)))
        rg.setColorAt(1, with_alpha(pal.accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(mid, cy), glow_r, glow_r)
        g = QLinearGradient(mid - r, cy - r, mid + r, cy + r)
        g.setColorAt(0, pal.accent)
        g.setColorAt(1, pal.secondary)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(mid, cy), r, r)
        if hp > 0.02:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(pal.text, int(190 * hp)), 2))
            p.drawEllipse(QPointF(mid, cy), r + 3, r + 3)
        self.add_hit("play", QRectF(mid - 23, cy - 23, 46, 46))
        (icon_pause if st.playing else icon_play)(
            p, mid + (0 if st.playing else 1.5), cy, 20 * (1.0 + 0.07 * hp), pal.bg
        )
        self.button(p, "next", mid + 52, cy, 18, icon_next, pal, can.get("next", True))
        self.button(p, "repeat", mid + 100, cy, 14, icon_repeat, pal, can.get("repeat", True), st.repeat != 0, mode=st.repeat)
        if vol_on:
            level = 0.0 if self.ctl.vol_muted else self.ctl.vol_level
            self.button(p, "mute", x1 - vw - 18, cy, 14, icon_speaker, pal, True, False, level=level, muted=self.ctl.vol_muted)
            hvv = 1.0 if self.vol_drag else self.hv.get("vol", 0.0)
            vth = 4.0 + 2.0 * hvv
            bar = QRectF(x1 - vw, cy - 2, vw, 4)
            self.add_hit("vol", bar.adjusted(-4, -11, 4, 11))
            self.rects["vol"] = bar
            track = QRectF(bar.left(), cy - vth / 2.0, vw, vth)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(track, vth / 2.0, vth / 2.0)
            fw = bar.width() * level
            if fw > 0:
                vg = QLinearGradient(bar.left(), 0, bar.right(), 0)
                vg.setColorAt(0, pal.accent)
                vg.setColorAt(1, pal.secondary)
                p.setBrush(QBrush(vg))
                p.drawRoundedRect(QRectF(bar.left(), track.top(), fw, vth), vth / 2.0, vth / 2.0)
            if hvv > 0.02:
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(bar.left() + fw, cy), 2.0 + 3.5 * hvv, 2.0 + 3.5 * hvv)

    def paint_lyric_area(self, p, area, dpr, op):
        st = self.state
        lines = st.active_lines()
        if not lines:
            return
        tp = st.pal_target
        ly = st.lyrics
        cfg = self.cfg
        size = float(cfg["font_size"])
        glow = cfg["glow"] / 100.0
        maxw = area.width() - 24
        karaoke = bool(cfg["karaoke"])
        sty = lyric_style(cfg)
        fill, fill2, gcol = lyric_colors(cfg, tp)
        dim_a = cfg["dim_level"] / 100.0
        mo = cfg["motion"] / 100.0
        lop = cfg["lyric_opacity"] / 100.0
        p.save()
        p.setClipRect(area)
        for i, a, prog, age, eo in lines:
            text = ly.texts[i]
            bright = cached_line(self.cache, self.theme, text, size, fill, gcol, glow, maxw, dpr, False, "c", sty, fill2)
            dim = (
                cached_line(self.cache, self.theme, text, size, fill, gcol, 0.0, maxw, dpr, False, "c", sty, fill2)
                if karaoke
                else None
            )
            enter = ease(age / 0.5)
            yy = area.center().y() + 16 * mo * (1.0 - enter) - 18 * mo * ease(eo)
            p.save()
            p.translate(area.center().x(), yy)
            draw_karaoke(p, dim, bright, prog, a * op * lop, karaoke, 1.0, dim_a)
            p.restore()
        p.restore()
        p.setOpacity(op)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        th = self.theme
        st = self.state
        cfg = self.cfg
        dpr = self.devicePixelRatioF()
        pal = st.palette
        now = time.monotonic()
        ui = bool(cfg["ui_anim"])
        ap = ease(self.appear)
        op = cfg["opacity"] / 100.0
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        self.hits = []
        p.translate(0.0, (1.0 - ap) * 14.0)
        p.setOpacity(op * ap)
        self.paint_card(p, card, pal)
        pad = 20.0
        x0 = card.left() + pad
        x1 = card.right() - pad
        top = card.top() + pad
        age = now - self.track_t
        ta = ease(age / 0.55) if ui else 1.0
        ta2 = ease((age - 0.08) / 0.55) if ui else 1.0
        ta3 = ease((age - 0.16) / 0.55) if ui else 1.0
        show_cover = bool(cfg["show_cover"])
        cs = 88.0 if show_cover else 70.0
        if show_cover:
            cr = QRectF(x0, top, cs, cs)
            if ui and st.playing:
                pulse = 0.5 + 0.5 * math.sin(now * 2.4)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(with_alpha(pal.accent, int(30 + 60 * pulse)), 3.0))
                p.drawRoundedRect(cr.adjusted(-1.5, -1.5, 1.5, 1.5), 14, 14)
            p.save()
            c = cr.center()
            sc = 0.9 + 0.1 * ta
            p.translate(c)
            p.scale(sc, sc)
            p.translate(-c.x(), -c.y())
            p.setOpacity(op * ap * ta)
            self.paint_cover(p, cr, pal, dpr)
            p.restore()
        tx = x0 + (cs + 16.0 if show_cover else 0.0)
        tw = max(40.0, x1 - tx - 74.0)
        if st.active:
            title, artist, album = st.title, st.artist, st.album
        else:
            title, artist, album = "Waiting for media", "Play something in Spotify or your browser", ""
        cy = top
        ft = th.font(21, QFont.Weight.Bold)
        fm = QFontMetrics(ft)
        p.setFont(ft)
        p.setPen(with_alpha(pal.text, int(255 * ta)))
        p.drawText(
            QPointF(tx + (1.0 - ta) * 18.0, cy + fm.ascent()),
            fm.elidedText(title, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 2
        fa = th.font(15, QFont.Weight.Medium)
        fm = QFontMetrics(fa)
        p.setFont(fa)
        p.setPen(with_alpha(pal.text, int(215 * ta2)))
        p.drawText(
            QPointF(tx + (1.0 - ta2) * 18.0, cy + fm.ascent()),
            fm.elidedText(artist, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 1
        if album and cfg["show_album"]:
            fb = th.font(12, QFont.Weight.Normal)
            fm = QFontMetrics(fb)
            p.setFont(fb)
            p.setPen(with_alpha(pal.text, int(120 * ta3)))
            p.drawText(
                QPointF(tx + (1.0 - ta3) * 18.0, cy + fm.ascent()),
                fm.elidedText(album, Qt.TextElideMode.ElideRight, int(tw)),
            )
        gx = card.right() - 14
        sym = QFont("Segoe UI Symbol", 10)
        for name, glyph in (("close", "✕"), ("mode", "▣"), ("gear", "⚙")):
            r = QRectF(gx - 22, card.top() + 10, 22, 22)
            self.add_hit(name, r)
            hv = self.hv.get(name, 0.0)
            if hv > 0.01:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pal.text, int(38 * hv)))
                p.drawEllipse(r.adjusted(1, 1, -1, -1))
            p.setFont(sym)
            p.setPen(with_alpha(pal.text, int(110 + 80 * hv)))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, glyph)
            gx -= 24
        sync_on = bool(cfg["show_sync"]) and st.active and st.lyrics is not None
        if cfg["show_status"]:
            fc = th.font(11, QFont.Weight.Medium, 0.6)
            fmc = QFontMetrics(fc)
            base = top + cs - 2
            off = 20.0 if cfg["show_eq"] else 14.0
            p.setPen(Qt.PenStyle.NoPen)
            if cfg["show_eq"]:
                lit = st.playing
                p.setBrush(pal.accent if lit else with_alpha(pal.text, 110))
                for k in range(4):
                    hgt = 3.0 + 8.0 * (0.5 + 0.5 * math.sin(now * (5.0 + k * 1.9) + k * 1.3)) if lit else 3.0
                    p.drawRoundedRect(QRectF(tx + k * 4.0, base - 2.0 - hgt, 2.6, hgt), 1.3, 1.3)
            else:
                p.setBrush(pal.accent if st.playing else with_alpha(pal.text, 110))
                p.drawEllipse(QPointF(tx + 3.5, base - 4.2), 3.0, 3.0)
            p.setFont(fc)
            p.setPen(with_alpha(pal.text, 150))
            avail = x1 - tx - off - (120.0 if sync_on else 0.0)
            p.drawText(
                QPointF(tx + off, base),
                fmc.elidedText(self.chip_text(), Qt.TextElideMode.ElideRight, int(max(20.0, avail))),
            )
        if sync_on:
            self.paint_sync(p, x1, top + cs - 6.0, pal)
        py = top + cs + 20.0
        self.paint_progress(p, x0, x1, py, pal)
        cyc = py + 50.0
        self.paint_controls(p, x0, x1, cyc, pal)
        if not self.compact:
            area_top = cyc + 23 + 14
            area = QRectF(x0 - 8, area_top, x1 - x0 + 16, card.bottom() - pad + 4 - area_top)
            if area.height() > 40:
                p.setPen(QPen(with_alpha(pal.text, 26), 1))
                p.drawLine(QPointF(x0, area_top - 6), QPointF(x1, area_top - 6))
                self.paint_lyric_area(p, area, dpr, op * ap)
        if not cfg["click_through"]:
            p.setPen(QPen(with_alpha(pal.text, 70), 1.2))
            gx2 = card.right() - 10
            gy2 = card.bottom() - 10
            for k in (6, 11, 16):
                p.drawLine(QPointF(gx2 - k, gy2), QPointF(gx2, gy2 - k))

    def mini(self, p, name, cx, cy, text, pal):
        hv = self.hv.get(name, 0.0)
        r = QRectF(cx - 10, cy - 10, 20, 20)
        self.add_hit(name, r)
        rr = 8.5 + 1.5 * hv
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(pal.text, int(18 + 50 * hv)))
        p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.setFont(self.theme.font(14, QFont.Weight.Bold))
        p.setPen(with_alpha(mix(pal.text, pal.accent, hv), int(150 + 90 * hv)))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def paint_sync(self, p, x1, cy, pal):
        val = self.state.sync_ms()
        self.mini(p, "sync_p", x1 - 10, cy, "+", pal)
        self.mini(p, "sync_m", x1 - 102, cy, "\u2212", pal)
        hv = self.hv.get("sync_r", 0.0)
        lr = QRectF(x1 - 92, cy - 10, 68, 20)
        self.add_hit("sync_r", lr)
        label = f"{val:+d} ms" if val else "0 ms"
        col = pal.accent if val else pal.text
        p.setFont(self.theme.font(11, QFont.Weight.DemiBold))
        p.setPen(with_alpha(mix(col, pal.text, hv * 0.4), int((210 if val else 130) + 40 * hv)))
        p.drawText(lr, Qt.AlignmentFlag.AlignCenter, label)


class Holo(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.cache = LineCache(160)
        self.fade = 0.0
        self.last = time.monotonic()
        self.t0 = self.last
        self.particles = []
        self.dots = {}
        self.assign = {}
        self.last_pos = None
        self.next_glitch = self.last + 5.0
        self.wall = self.cfg["layer"] == "wall"
        self.attached = False
        self.host = None
        self.org = QPoint(0, 0)
        self.wp_img = None
        self.wp_src = None
        self.wp_next = 0.0
        self.wp_pm = None
        self.wp_sig = None
        self.glitch_until = 0.0
        self.dirty = True
        self.build_window()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.set_fps()
        self.state.track_changed.connect(self.on_track)
        self.state.lyrics_changed.connect(self.on_track)

    def on_track(self):
        self.assign.clear()
        self.last_pos = None
        self.dirty = True

    def place(self):
        screens = QGuiApplication.screens()
        i = int(clamp(int(self.cfg["holo_screen"]), 0, len(screens) - 1))
        g = screens[i].geometry().adjusted(0, 0, -1, -1)
        self.org = g.topLeft()
        if self.wall and self.attached:
            self.move_native()
        elif self.geometry() != g:
            self.setGeometry(g)
            self.particles = []
        self.spawn_particles()

    def spawn_particles(self):
        want = int(self.cfg["particle_count"]) if self.cfg["particles"] else 0
        if len(self.particles) == want:
            return
        W, H = max(1, self.width()), max(1, self.height())
        self.particles = [
            [random.random() * W, random.random() * H, random.uniform(14, 40), random.uniform(0.4, 1.2), random.random() * 6.28]
            for _ in range(want)
        ]

    def set_fps(self):
        self.timer.setInterval(int(1000 / max(10, int(self.cfg["fps"]))))

    def refresh(self):
        self.apply_layer()
        self.cache.clear()
        self.dots.clear()
        self.wp_pm = None
        self.wp_src = None
        self.wp_next = 0.0
        self.set_fps()
        if self.isVisible():
            self.place()
        self.dirty = True
        self.update()

    def showEvent(self, e):
        self.last = time.monotonic()
        self.timer.start()
        super().showEvent(e)
        if self.wall:
            QTimer.singleShot(0, self.attach_wall)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        st = self.state
        animate = st.step_palette()
        if self.wall and self.attached and self.wall_poll(now):
            animate = True
        tf = 1.0 if st.active else 0.0
        if self.fade != tf:
            df = tf - self.fade
            if abs(df) > 0.005:
                self.fade += df * (1 - math.exp(-dt * 3.5))
            else:
                self.fade = tf
            animate = True
        if self.fade > 0.01 and st.playing and self.particles:
            H = self.height()
            W = self.width()
            t = now - self.t0
            ps = self.cfg["particle_speed"] / 100.0
            for pt in self.particles:
                pt[1] -= pt[2] * dt * ps
                pt[0] += math.sin(t * 0.5 + pt[4]) * 9 * dt * ps
                pt[4] += dt * 1.6
                if pt[1] < -30:
                    pt[1] = H + 30
                    pt[0] = random.random() * W
            animate = True
        if now > self.next_glitch:
            self.glitch_until = now + 0.14
            self.next_glitch = now + random.uniform(4.0, 10.0)
        if self.fade > 0.01 and st.playing and st.lyrics is not None and st.active_lines():
            animate = True
        if now - st.track_started < float(self.cfg["toast_secs"]) and st.active and self.cfg["show_toast"]:
            animate = True
        if animate or self.dirty:
            self.dirty = False
            self.update()

    def dot(self, color):
        key = color.rgba()
        d = self.dots.get(key)
        if d is None:
            d = QPixmap(48, 48)
            d.fill(Qt.GlobalColor.transparent)
            q = QPainter(d)
            q.setRenderHints(AA)
            g = QRadialGradient(24, 24, 24)
            g.setColorAt(0, with_alpha(color, 255))
            g.setColorAt(0.25, with_alpha(color, 70))
            g.setColorAt(1, with_alpha(color, 0))
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QBrush(g))
            q.drawEllipse(0, 0, 48, 48)
            q.end()
            self.dots[key] = d
        return d

    def paint_particles(self, p, pal, fade):
        da = self.dot(pal.accent)
        ds = self.dot(pal.secondary)
        src = QRectF(0, 0, 48, 48)
        for k, pt in enumerate(self.particles):
            x, y, _vy, s, ph = pt
            r = (3.0 + s * 5.0) * self.cfg["particle_size"] / 100.0
            p.setOpacity(fade * (0.2 + 0.35 * (0.5 + 0.5 * math.sin(ph))))
            p.drawPixmap(QRectF(x - r, y - r, 2 * r, 2 * r), ds if k % 3 == 0 else da, src)

    def paint_toast(self, p, W, H, pal):
        st = self.state
        if not st.active or not self.cfg["show_toast"]:
            return
        age = time.monotonic() - st.track_started
        span = max(2.0, float(self.cfg["toast_secs"]))
        if age > span:
            return
        a = ease(age / 0.6) * (1.0 - ease((age - (span - 1.2)) / 1.1))
        if a <= 0.01:
            return
        f = self.theme.font(15, QFont.Weight.DemiBold, 4.0)
        fm = QFontMetrics(f)
        label = fm.elidedText(f"{st.title}  //  {st.artist}".upper(), Qt.TextElideMode.ElideRight, int(W * 0.6))
        ty = H * 0.075 + (1.0 - ease(age / 0.6)) * -14
        p.setFont(f)
        p.setPen(pal.accent.lighter(130))
        p.setOpacity(a * 0.95)
        p.drawText(QPointF((W - fm.horizontalAdvance(label)) / 2.0, ty), label)
        bw = 320.0
        bx = (W - bw) / 2.0
        p.setPen(QPen(with_alpha(pal.accent, 70), 2))
        p.setOpacity(a)
        p.drawLine(QPointF(bx, ty + 14), QPointF(bx + bw, ty + 14))
        if st.dur > 0:
            frac = clamp(st.position() / st.dur, 0.0, 1.0)
            p.setPen(QPen(pal.accent, 2))
            p.drawLine(QPointF(bx, ty + 14), QPointF(bx + bw * frac, ty + 14))

    def pos_for(self, i, current):
        mode = self.cfg["placement"]
        if mode in POS:
            return mode
        got = self.assign.get(i)
        if got:
            return got
        pool = [k for k in self.cfg["positions"] if k in POS] or list(POS_KEYS)
        used = {self.assign.get(j) for j in current if j != i}
        cands = [k for k in pool if k not in used and k != self.last_pos]
        if not cands:
            cands = [k for k in pool if k != self.last_pos] or pool
        k = random.choice(cands)
        self.assign[i] = k
        self.last_pos = k
        return k

    def card_rect(self):
        hud = self.ctl.hud
        if self.wall or not hud.isVisible():
            return None
        m = hud.MARGIN
        gap = float(self.cfg["card_gap"])
        r = QRectF(
            hud.x() + m - self.org.x(),
            hud.y() + m - self.org.y(),
            hud.width() - 2 * m,
            hud.height() - 2 * m,
        )
        return r.adjusted(-gap, -gap, gap, gap)

    def fit(self, left, topy, bw, bh, side, mo, ghost_pad, card, W, H):
        if card is None:
            return left, topy
        il = 4.0 + bw * 0.02 + ghost_pad + (60.0 * mo if side < 0 else 0.0)
        ir = 4.0 + bw * 0.02 + (60.0 * mo if side > 0 else 0.0)
        it = 8.0 + bh * 0.02 + 20.0 * mo
        ib = 8.0 + bh * 0.02 + (30.0 * mo if side == 0 else 0.0)

        def clear(l, t):
            return (
                l + bw + ir <= card.left()
                or l - il >= card.right()
                or t + bh + ib <= card.top()
                or t - it >= card.bottom()
            )

        if clear(left, topy):
            return left, topy
        xmin, xmax = 8.0, max(8.0, W - bw - 8.0)
        ymin, ymax = 16.0, max(16.0, H - bh - 16.0)
        opts = []
        for nl in (card.left() - ir - bw, card.right() + il):
            if xmin <= nl <= xmax:
                opts.append((abs(nl - left), nl, topy))
        for nt in (card.top() - ib - bh, card.bottom() + it):
            if ymin <= nt <= ymax:
                opts.append((abs(nt - topy), left, nt))
        if not opts:
            return None
        opts.sort(key=lambda o: o[0])
        return opts[0][1], opts[0][2]

    def paintEvent(self, e):
        if self.fade < 0.01 and not self.wall:
            return
        p = QPainter(self)
        p.setRenderHints(AA)
        st = self.state
        cfg = self.cfg
        th = self.theme
        W = self.width()
        H = self.height()
        dpr = self.devicePixelRatioF()
        now = time.monotonic()
        t = now - self.t0
        pal = st.pal_target
        fade = self.fade
        if self.wall:
            self.paint_wall(p, W, H, dpr)
        if fade < 0.01:
            return
        if cfg["particles"] and self.particles:
            self.paint_particles(p, pal, fade)
        self.paint_toast(p, W, H, pal)
        lines = st.active_lines()
        if not lines:
            return
        ly = st.lyrics
        base_px = cfg["font_size"] * 1.6 * cfg["holo_scale"] / 100.0
        glow = cfg["glow"] / 100.0
        scan = bool(cfg["scanlines"])
        karaoke = bool(cfg["karaoke"])
        glitch_on = bool(cfg["glitch"])
        tilt_on = bool(cfg["tilt"])
        fi = max(0.15, cfg["fade_ms"] / 1000.0 * 0.65)
        glitching = glitch_on and now < self.glitch_until
        current = [x[0] for x in lines]
        sty = lyric_style(cfg)
        sty_g = sty[:4] + (0, 0) + sty[6:]
        fill, fill2, gcol = lyric_colors(cfg, pal)
        dim_a = cfg["dim_level"] / 100.0
        mo = cfg["motion"] / 100.0
        lop = cfg["lyric_opacity"] / 100.0
        wf = cfg["holo_width"] / 100.0
        gs = cfg["ghost"] / 100.0
        es = cfg["enter_style"]
        ghost_pad = 34.0 if glitch_on else 3.0
        card = self.card_rect()
        for i, a, prog, age, eo in lines:
            key = self.pos_for(i, current)
            ax, ay, align = POS[key]
            side = -1 if align == "l" else (1 if align == "r" else 0)
            maxw = W * (min(0.9, wf * 1.39) if align == "c" else wf)
            text = ly.texts[i]
            placed = None
            for attempt in (0, 1):
                bright = cached_line(self.cache, th, text, base_px, fill, gcol, glow, maxw, dpr, scan, align, sty, fill2)
                dim = (
                    cached_line(self.cache, th, text, base_px, fill, gcol, 0.0, maxw, dpr, scan, align, sty, fill2)
                    if karaoke
                    else None
                )
                ghost = cached_line(
                    self.cache, th, text, base_px, pal.secondary, pal.secondary, 0.2, maxw, dpr, False, align, sty_g
                )
                bw, bh = bright[1], bright[2]
                if align == "l":
                    left = ax * W
                elif align == "r":
                    left = ax * W - bw
                else:
                    left = ax * W - bw / 2.0
                topy = ay * H - bh / 2.0
                left = clamp(left, 8, max(8, W - bw - 8))
                topy = clamp(topy, 16, max(16, H - bh - 16))
                placed = self.fit(left, topy, bw, bh, side, mo, ghost_pad, card, W, H)
                if placed is not None or card is None or attempt == 1:
                    break
                room = max(card.left(), W - card.right()) - 8.0 - (64.0 * mo + 40.0)
                if room < 160 or room >= maxw:
                    break
                maxw = room
            if placed is None:
                continue
            left, topy = placed
            enter = ease(age / fi)
            if es == "rise":
                ox = 0.0
                oy_in = 44.0 * mo * (1.0 - enter)
                sc_in = 1.0
            elif es == "zoom":
                ox = 0.0
                oy_in = 0.0
                sc_in = 1.0 - 0.24 * mo * (1.0 - enter)
            elif es == "fade":
                ox = 0.0
                oy_in = 0.0
                sc_in = 1.0
            else:
                ox = side * 60.0 * mo * (1.0 - enter)
                oy_in = 30.0 * mo * (1.0 - enter) if side == 0 else 0.0
                sc_in = 1.0 - 0.06 * mo * (1.0 - enter)
            oy = oy_in - 20.0 * mo * ease(eo) + math.sin(t * 1.2 + i) * 5.0 * min(1.0, mo)
            sc = sc_in * (1.0 + 0.03 * mo * ease(eo))
            base_tilt = (14.0 if side < 0 else (-14.0 if side > 0 else 0.0)) if tilt_on else 0.0
            rot = base_tilt * (1.6 - 0.6 * enter)
            tr = QTransform()
            tr.translate(left + bw / 2.0 + ox, topy + bh / 2.0 + oy)
            tr.rotate(rot, Qt.Axis.YAxis)
            tr.scale(sc, sc)
            p.setTransform(tr)
            gx = 3.0
            flick = 0.95 + 0.05 * math.sin(t * 37.0)
            if glitch_on:
                gx += 16.0 * (1.0 - enter)
                if glitching:
                    gx += random.uniform(6, 14)
                    flick *= random.uniform(0.65, 1.0)
            if gs > 0.01:
                p.setOpacity(clamp(a * 0.4 * fade * gs * lop, 0.0, 1.0))
                p.drawPixmap(QPointF(-ghost[1] / 2.0 - gx, -ghost[2] / 2.0 + 1), ghost[0])
            draw_karaoke(p, dim, bright, prog, a * fade * lop, karaoke, flick, dim_a)
            p.resetTransform()
        p.setOpacity(1.0)

    def build_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if not self.wall:
            flags |= Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self.wall)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, self.wall)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not self.wall)

    def apply_layer(self):
        want = self.cfg["layer"] == "wall"
        if want == self.wall:
            return
        self.wall = want
        self.attached = False
        self.host = None
        self.wp_pm = None
        self.build_window()
        self.dirty = True

    def native_rect(self):
        screens = QGuiApplication.screens()
        s = screens[int(clamp(int(self.cfg["holo_screen"]), 0, len(screens) - 1))]
        g = s.geometry()
        d = s.devicePixelRatio()
        return g.x(), g.y(), int(round(g.width() * d)), int(round(g.height() * d))

    def attach_wall(self):
        if not self.wall:
            return
        if not self.attached:
            host = desktop_attach(int(self.winId()))
            if not host:
                self.cfg["layer"] = "top"
                self.cfg.save()
                self.ctl.refresh()
                self.ctl.tray.showMessage(
                    "Lyrics HUD", "The wallpaper layer is not available on this system, using the top layer instead."
                )
                return
            self.host = host
            self.attached = True
        self.move_native()

    def move_native(self):
        x, y, w, h = self.native_rect()
        desktop_place(int(self.winId()), self.host, x, y, w, h)
        self.dirty = True
        self.update()

    def wall_poll(self, now):
        if now < self.wp_next:
            return False
        self.wp_next = now + 3.0
        path = wallpaper_path()
        try:
            stamp = os.stat(path).st_mtime_ns if path else 0
        except OSError:
            stamp = 0
        src = (path, stamp, wallpaper_style())
        if src == self.wp_src:
            return False
        self.wp_src = src
        img = QImage(path) if path else QImage()
        self.wp_img = None if img.isNull() else img
        self.wp_pm = None
        return True

    def paint_wall(self, p, W, H, dpr):
        if self.wp_src is None:
            self.wall_poll(time.monotonic())
        style = self.wp_src[2] if self.wp_src else (10, 0, (0, 0, 0))
        sig = (self.wp_src, W, H, int(dpr * 100), self.org.x(), self.org.y())
        if self.wp_pm is None or self.wp_sig != sig:
            virt = QGuiApplication.primaryScreen().virtualGeometry()
            self.wp_pm = build_wallpaper(self.wp_img, style, W, H, dpr, self.org, virt)
            self.wp_sig = sig
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawPixmap(0, 0, self.wp_pm)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        dim = int(self.cfg["wall_dim"] * 2.55)
        if dim > 0:
            p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, dim))
        p.setCompositionMode(BLEND.get(self.cfg["wall_blend"], BLEND["normal"]))


class Switch(QCheckBox):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 26)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        on = self.isChecked()
        enabled = self.isEnabled()
        track = QColor(pal.accent) if on else mix(pal.surface, pal.text, 0.18)
        if not enabled:
            track.setAlpha(80)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(1, 3, 46, 20), 10, 10)
        kx = 47 - 3 - 8 if on else 1 + 3 + 8
        p.setBrush(pal.bg if (on and enabled) else pal.text)
        p.drawEllipse(QPointF(kx, 13), 7.5, 7.5)


def cover_thumb(state, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(AA)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 10, 10)
    p.setClipPath(path)
    if state.cover is not None:
        sc = state.cover.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        p.drawImage((size - sc.width()) // 2, (size - sc.height()) // 2, sc)
    else:
        pal = state.pal_target
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, with_alpha(pal.accent, 190))
        g.setColorAt(1, with_alpha(pal.secondary, 120))
        p.fillRect(QRectF(0, 0, size, size), QBrush(g))
        p.setFont(QFont("Segoe UI Symbol", int(size * 0.34), QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return pm


def dark_titlebar(widget, pal):
    try:
        import ctypes

        hwnd = int(widget.winId())
        one = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(one), ctypes.sizeof(one))
        c = pal.bg
        ref = ctypes.c_uint(c.red() | (c.green() << 8) | (c.blue() << 16))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ref), ctypes.sizeof(ref))
        t = pal.text
        tref = ctypes.c_uint(t.red() | (t.green() << 8) | (t.blue() << 16))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(tref), ctypes.sizeof(tref))
    except Exception:
        pass


def list_font_files():
    out = []
    try:
        for p in sorted(FONT_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and p.suffix.lower() in FONT_EXTS:
                out.append(p)
    except Exception:
        pass
    return out


def google_font_index():
    req = urlrequest.Request(GF_META, headers={"User-Agent": UA})
    with urlrequest.urlopen(req, timeout=15) as r:
        raw = r.read().decode("utf-8", "replace")
    data = json.loads(raw[raw.find("{"):])
    out = []
    for f in data.get("familyMetadataList", []):
        name = f.get("family")
        if name:
            out.append((name, f.get("category") or "", list((f.get("fonts") or {}).keys())))
    return out


def download_google_font(family, variants):
    weight = "400" if "400" in variants else next((v for v in variants if v.isdigit()), "400")
    query = urlparse.urlencode({"family": family + ":" + weight})
    req = urlrequest.Request(GF_CSS + "?" + query, headers={"User-Agent": UA})
    with urlrequest.urlopen(req, timeout=15) as r:
        css = r.read().decode("utf-8", "replace")
    urls = re.findall(r"url\((https?://[^)\s]+)\)", css)
    if not urls:
        raise ValueError("no font file found")
    url = next((u for u in urls if u.lower().endswith((".ttf", ".otf"))), urls[0])
    ext = os.path.splitext(urlparse.urlparse(url).path)[1].lower()
    if ext not in FONT_EXTS:
        ext = ".ttf"
    safe = re.sub(r"[^A-Za-z0-9]+", "", family) or "Font"
    dest = FONT_DIR / (safe + "-Regular" + ext)
    req = urlrequest.Request(url, headers={"User-Agent": UA})
    with urlrequest.urlopen(req, timeout=30) as r:
        blob = r.read()
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(blob)
    os.replace(str(tmp), str(dest))
    return dest


class FontNet(QObject):
    index_ready = pyqtSignal()
    index_failed = pyqtSignal(str)
    downloaded = pyqtSignal(str)
    failed = pyqtSignal(str)
    index = None

    def _emit(self, sig, *args):
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def load_index(self):
        if FontNet.index is not None:
            self.index_ready.emit()
            return

        def run():
            try:
                FontNet.index = google_font_index()
            except Exception as e:
                self._emit(self.index_failed, str(e))
                return
            self._emit(self.index_ready)

        threading.Thread(target=run, daemon=True).start()

    def download(self, family, variants):
        def run():
            try:
                path = str(download_google_font(family, variants))
            except Exception as e:
                self._emit(self.failed, str(e))
                return
            self._emit(self.downloaded, path)

        threading.Thread(target=run, daemon=True).start()


class FontCombo(QComboBox):
    about_to_open = pyqtSignal()

    def showPopup(self):
        self.about_to_open.emit()
        super().showPopup()


class SettingsDialog(QDialog):
    PAGES = ("Appearance", "Lyrics", "Overlay", "Player", "About")

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.state = ctl.state
        self.switches = []
        self.manual = []
        self.pos_buttons = {}
        self.setWindowTitle("Lyrics HUD")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(820, 600)
        self.setMinimumSize(720, 480)
        self.setStyleSheet(build_qss(self.state.pal_target))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 14)
        sl.setSpacing(0)
        brand = QLabel("LYRICS HUD")
        brand.setObjectName("brand")
        sl.addWidget(brand)
        credit = QLabel("by CyberSecPwner")
        credit.setObjectName("hint")
        credit.setContentsMargins(20, 0, 20, 10)
        sl.addWidget(credit)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for name in self.PAGES:
            self.nav.addItem(name)
        sl.addWidget(self.nav, 1)
        self.np = QWidget()
        self.np.setObjectName("npcard")
        npl = QHBoxLayout(self.np)
        npl.setContentsMargins(10, 10, 10, 10)
        self.np_cover = QLabel()
        self.np_cover.setFixedSize(46, 46)
        npl.addWidget(self.np_cover)
        npt = QVBoxLayout()
        npt.setSpacing(1)
        self.np_title = QLabel()
        self.np_title.setObjectName("nptitle")
        self.np_artist = QLabel()
        self.np_artist.setObjectName("npartist")
        npt.addStretch(1)
        npt.addWidget(self.np_title)
        npt.addWidget(self.np_artist)
        npt.addStretch(1)
        npl.addLayout(npt, 1)
        npw = QHBoxLayout()
        npw.setContentsMargins(12, 0, 12, 0)
        npw.addWidget(self.np)
        sl.addLayout(npw)
        root.addWidget(side)

        main = QWidget()
        main.setObjectName("main")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.header = QLabel("Appearance")
        self.header.setObjectName("title")
        ml.addWidget(self.header)
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(28, 10, 28, 18)
        reset = QPushButton("Reset defaults")
        close = QPushButton("Done")
        close.setObjectName("primary")
        reset.clicked.connect(self.on_reset)
        close.clicked.connect(self.close)
        foot.addWidget(reset)
        foot.addStretch(1)
        foot.addWidget(close)
        ml.addLayout(foot)
        root.addWidget(main, 1)

        self.build_appearance()
        self.build_lyrics()
        self.build_overlay()
        self.build_player()
        self.build_about()
        self.nav.currentRowChanged.connect(self.on_nav)
        self.nav.setCurrentRow(0)
        self.state.track_changed.connect(self.np_update)
        self.state.track_changed.connect(self.song_off_update)
        self.state.offset_changed.connect(self.song_off_update)
        self.state.palette_changed.connect(self.on_palette)
        self.np_update()
        self.sync_manual()

    def showEvent(self, e):
        dark_titlebar(self, self.state.pal_target)
        super().showEvent(e)

    def on_nav(self, i):
        self.stack.setCurrentIndex(max(0, i))
        self.header.setText(self.PAGES[max(0, i)])

    def on_palette(self):
        for s in self.switches:
            s.update()
        self.np_update()
        dark_titlebar(self, self.state.pal_target)

    def np_update(self):
        st = self.state
        self.np_cover.setPixmap(cover_thumb(st, 46))
        fm = QFontMetrics(self.np_title.font())
        self.np_title.setText(fm.elidedText(st.title if st.active else "Nothing playing", Qt.TextElideMode.ElideRight, 110))
        self.np_artist.setText(fm.elidedText(st.artist if st.active else "", Qt.TextElideMode.ElideRight, 110))

    def new_page(self):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 0, 28, 24)
        lay.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        return lay

    def sec(self, lay, text):
        l = QLabel(text.upper())
        l.setObjectName("section")
        lay.addWidget(l)

    def row(self, lay, label, widget, hint=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 5, 0, 5)
        left = QVBoxLayout()
        left.setSpacing(2)
        l = QLabel(label)
        l.setObjectName("rowlabel")
        left.addWidget(l)
        if hint:
            hl = QLabel(hint)
            hl.setObjectName("hint")
            hl.setWordWrap(True)
            left.addWidget(hl)
        h.addLayout(left, 1)
        h.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(w)
        return w

    def set_val(self, key, value, refresh=True):
        self.cfg[key] = value
        if refresh:
            self.ctl.refresh()
        else:
            self.cfg.save()

    def switch(self, key, after=None):
        s = Switch(self.state)
        s.setChecked(bool(self.cfg[key]))

        def toggled(v):
            self.set_val(key, bool(v))
            if after:
                after()

        s.toggled.connect(toggled)
        self.switches.append(s)
        return s

    def slider(self, key, lo, hi, suffix=""):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(self.cfg[key]))
        s.setFixedWidth(200)
        lab = QLabel(f"{int(self.cfg[key])}{suffix}")
        lab.setFixedWidth(64)
        lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        def changed(v):
            lab.setText(f"{v}{suffix}")
            self.set_val(key, v)

        s.valueChanged.connect(changed)
        box = QWidget()
        l = QHBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(s)
        l.addWidget(lab)
        return box

    def color(self, key):
        b = QPushButton()
        b.setFixedWidth(120)

        def paint():
            c = QColor(self.cfg[key])
            fg = "#000" if c.lightness() > 140 else "#fff"
            b.setText(c.name().upper())
            b.setStyleSheet(
                f"QPushButton{{background:{c.name()};color:{fg};border:1px solid rgba(255,255,255,40);border-radius:9px;padding:7px;font-weight:700;}}"
            )

        def pick():
            c = QColorDialog.getColor(QColor(self.cfg[key]), self, "Pick color")
            if c.isValid():
                self.cfg[key] = c.name()
                paint()
                self.ctl.refresh()

        b.clicked.connect(pick)
        paint()
        self.manual.append(b)
        return b

    def combo(self, key, items, cast=None):
        c = QComboBox()
        c.setFixedWidth(200)
        for label, val in items:
            c.addItem(label, val)
        c.setCurrentIndex(max(0, c.findData(self.cfg[key])))
        c.currentIndexChanged.connect(lambda _: self.set_val(key, c.currentData()))
        return c

    def segmented(self, key, items):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        group = QButtonGroup(box)
        group.setExclusive(True)
        for label, val in items:
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(self.cfg[key] == val)
            b.clicked.connect(lambda _=False, v=val: self.set_val(key, v))
            group.addButton(b)
            h.addWidget(b)
        return box

    def sync_manual(self):
        for w in self.manual:
            w.setEnabled(not self.cfg["adaptive"])

    def build_appearance(self):
        lay = self.new_page()
        self.sec(lay, "Layout")
        self.row(
            lay,
            "Display mode",
            self.segmented("mode", (("Player", "hud"), ("Floating lyrics", "holo"), ("Both", "both"))),
            "Player card, fullscreen floating lyrics, or the compact card plus overlay",
        )
        self.sec(lay, "Colors")
        self.row(
            lay,
            "Adaptive colors",
            self.switch("adaptive", self.sync_manual),
            "Pulls the palette from the album art so the card, menus, settings and lyrics all follow the cover",
        )
        self.row(lay, "Accent", self.color("accent"), "Used when adaptive colors are off")
        self.row(lay, "Secondary", self.color("secondary"))
        self.row(lay, "Text", self.color("text"))
        self.sec(lay, "Typography")
        self.fnet = FontNet()
        self.fnet.index_ready.connect(self.on_index_ready)
        self.fnet.index_failed.connect(self.on_index_failed)
        self.fnet.downloaded.connect(self.on_downloaded)
        self.fnet.failed.connect(self.on_download_failed)
        self.font_combo = FontCombo()
        self.font_combo.setFixedWidth(200)
        self.fill_font_combo()
        self.font_combo.about_to_open.connect(self.fill_font_combo)
        self.font_combo.currentIndexChanged.connect(self.on_font_combo)
        self.row(lay, "Font", self.font_combo, f"Every font file inside {FONT_DIR} shows up here")
        self.font_query = QLineEdit()
        self.font_query.setPlaceholderText("Search Google Fonts")
        self.font_query.setFixedWidth(120)
        self.font_query.returnPressed.connect(self.search_fonts)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_fonts)
        qbox = QWidget()
        ql = QHBoxLayout(qbox)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.addWidget(self.font_query)
        ql.addWidget(search_btn)
        self.row(lay, "Download fonts", qbox, "Downloaded fonts are saved into the Font folder")
        self.result_combo = QComboBox()
        self.result_combo.setFixedWidth(200)
        self.dl_button = QPushButton("Download")
        self.dl_button.setEnabled(False)
        self.dl_button.clicked.connect(self.download_font)
        rbox = QWidget()
        rl = QHBoxLayout(rbox)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.result_combo)
        rl.addWidget(self.dl_button)
        self.row(lay, "Search results", rbox)
        self.dl_info = QLabel()
        self.dl_info.setObjectName("hint")
        self.dl_info.setWordWrap(True)
        lay.addWidget(self.dl_info)
        self.font_edit = QLineEdit(self.cfg["font_path"])
        self.font_edit.setReadOnly(True)
        self.font_edit.setPlaceholderText("Default (Segoe UI)")
        self.font_edit.setFixedWidth(170)
        browse = QPushButton("Browse")
        clear = QPushButton("Clear")
        browse.clicked.connect(self.pick_font)
        clear.clicked.connect(self.clear_font)
        fbox = QWidget()
        fl = QHBoxLayout(fbox)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.font_edit)
        fl.addWidget(browse)
        fl.addWidget(clear)
        self.font_info = QLabel()
        self.font_info.setObjectName("hint")
        self.row(lay, "Custom font file", fbox, ".ttf, .otf or .ttc")
        lay.addWidget(self.font_info)
        self.update_font_info()
        self.row(lay, "Lyric size", self.slider("font_size", 14, 72, " px"))
        self.row(
            lay,
            "Lyric weight",
            self.combo("lyric_weight", [("Medium", 500), ("Semi-bold", 600), ("Bold", 700), ("Black", 900)]),
        )
        self.row(lay, "Letter spacing", self.slider("lyric_spacing", 0, 12, " px"))
        self.row(lay, "Line spacing", self.slider("lyric_gap", 80, 160, "%"), "Space between wrapped lines")
        self.row(
            lay,
            "Text case",
            self.combo("lyric_case", [("As written", "none"), ("UPPERCASE", "upper"), ("lowercase", "lower")]),
        )
        self.sec(lay, "Lyric style")
        self.row(
            lay,
            "Text fill",
            self.combo("lyric_fill", [("Solid", "solid"), ("Soft gradient", "soft"), ("Accent to secondary", "duo")]),
            "Soft gradient fades the text color into the secondary color across each line",
        )
        self.row(lay, "Glow", self.slider("glow", 0, 100, "%"))
        self.row(lay, "Lyric opacity", self.slider("lyric_opacity", 10, 100, "%"))
        self.row(
            lay,
            "Glow color",
            self.combo("glow_color", [("Accent", "accent"), ("Secondary", "secondary"), ("Text", "text")]),
        )
        self.row(lay, "Outline", self.slider("lyric_outline", 0, 6, " px"), "Dark edge that keeps text readable on bright backgrounds")
        self.row(lay, "Shadow", self.slider("lyric_shadow", 0, 100, "%"))
        self.sec(lay, "Player card")
        self.row(lay, "Card opacity", self.slider("opacity", 30, 100, "%"))
        self.row(lay, "Corner roundness", self.slider("card_radius", 8, 32, " px"))
        self.row(lay, "Cover tint", self.slider("backdrop", 0, 100, "%"), "How strongly the album art colors the card background")
        self.row(lay, "Animated border glow", self.slider("card_glow", 0, 100, "%"), "Light that travels around the card edge while music plays")
        self.row(lay, "Equalizer bars", self.switch("show_eq"), "Replaces the status dot with live bars")
        self.row(lay, "Interface animations", self.switch("ui_anim"), "Hover effects, entrance animation and track change transitions")
        self.row(lay, "Show sync buttons", self.switch("show_sync"), "Quick offset buttons on the card for the current song")
        self.row(lay, "Show cover art", self.switch("show_cover"))
        self.row(lay, "Show album name", self.switch("show_album"))
        self.row(lay, "Show status line", self.switch("show_status"))
        lay.addStretch(1)

    def build_lyrics(self):
        lay = self.new_page()
        self.sec(lay, "Timing")
        self.row(
            lay,
            "Auto sync",
            self.switch("auto_sync"),
            "Picks the lyric version closest to the track length, follows playback speed and remembers your nudges for each song",
        )
        self.song_off = QLabel()
        song_reset = QPushButton("Reset")
        song_reset.clicked.connect(lambda: self.state.set_track_ms(0))
        song_box = QWidget()
        sbl = QHBoxLayout(song_box)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.addWidget(self.song_off)
        sbl.addWidget(song_reset)
        self.row(lay, "This song's offset", song_box, "Saved per song and applied automatically. Nudge it from the tray menu while the song plays")
        self.song_off_update()
        self.row(lay, "Anticipation", self.slider("anticipation", 0, 600, " ms"), "Shows each line slightly before it is sung so the fade-in finishes right on the beat")
        snap_box = QWidget()
        snl = QHBoxLayout(snap_box)
        snl.setContentsMargins(0, 0, 0, 0)
        snap_cur = QPushButton("Current line starts now")
        snap_next = QPushButton("Next line starts now")
        snap_cur.clicked.connect(lambda: self.ctl.snap(0))
        snap_next.clicked.connect(lambda: self.ctl.snap(1))
        snl.addWidget(snap_cur)
        snl.addWidget(snap_next)
        self.row(lay, "Tap sync", snap_box, "Press when you hear a line begin to lock the lyrics to the song. The result is saved for this song")
        self.row(lay, "Global hotkeys", self.switch("hotkeys"), "Ctrl+Shift+Alt with K earlier, J later, H reset, N next line starts now, V show or hide")
        self.row(
            lay,
            "Lyrics only while sung",
            self.switch("karaoke"),
            "Karaoke fill: the line lights up word by word as it is sung. Lines always fade away once they end",
        )
        self.row(lay, "Unsung brightness", self.slider("dim_level", 10, 80, "%"), "How bright the part of the line that has not been sung yet stays")
        off = QSpinBox()
        off.setRange(-5000, 5000)
        off.setSingleStep(50)
        off.setSuffix(" ms")
        off.setFixedWidth(120)
        off.setValue(int(self.cfg["offset_ms"]))
        off.valueChanged.connect(lambda v: self.set_val("offset_ms", v, False))
        self.row(lay, "Sync offset", off, "Positive shows lyrics earlier, negative later")
        self.row(lay, "Line hold", self.slider("hold", 50, 200, "%"), "How long a line stays up before fading, relative to the estimate")
        self.row(lay, "Fade time", self.slider("fade_ms", 150, 1200, " ms"))
        self.sec(lay, "Placement")
        items = [("Random", "random")] + [(POS_LABELS[k], k) for k in POS_KEYS]
        self.row(lay, "Position", self.combo("placement", items), "Random picks a new spot for every line")
        grid_host = QWidget()
        gl = QGridLayout(grid_host)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        layout_map = {"tl": (0, 0), "tr": (0, 2), "ml": (1, 0), "m": (1, 1), "mr": (1, 2), "bl": (2, 0), "br": (2, 2)}
        short = {"tl": "TL", "tr": "TR", "m": "MID", "ml": "ML", "mr": "MR", "bl": "BL", "br": "BR"}
        for k, (r, c) in layout_map.items():
            b = QPushButton(short[k])
            b.setObjectName("pos")
            b.setCheckable(True)
            b.setFixedSize(64, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(k in self.cfg["positions"])
            b.toggled.connect(lambda v, key=k: self.toggle_pos(key, v))
            gl.addWidget(b, r, c)
            self.pos_buttons[k] = b
        self.row(lay, "Random spots", grid_host, "Pick which screen positions random placement may use")
        lay.addStretch(1)

    def song_off_update(self):
        st = self.state
        self.song_off.setText(f"{st.track_ms():+d} ms" if st.active else "No song")

    def toggle_pos(self, key, on):
        cur = [k for k in POS_KEYS if k in self.cfg["positions"]]
        if on and key not in cur:
            cur.append(key)
        if not on and key in cur:
            if len(cur) <= 1:
                self.pos_buttons[key].blockSignals(True)
                self.pos_buttons[key].setChecked(True)
                self.pos_buttons[key].blockSignals(False)
                return
            cur.remove(key)
        self.set_val("positions", cur)

    def build_overlay(self):
        lay = self.new_page()
        self.sec(lay, "Layer")
        self.row(
            lay,
            "Lyrics layer",
            self.combo("layer", [("Above everything", "top"), ("Wallpaper (desktop)", "wall")]),
            "Wallpaper paints the lyrics into your desktop background, so windows and icons always stay on top of them",
        )
        self.row(lay, "Wallpaper dimming", self.slider("wall_dim", 0, 80, "%"), "Darkens the wallpaper layer so lyrics stay readable")
        self.row(
            lay,
            "Wallpaper blend",
            self.combo(
                "wall_blend",
                [("Normal", "normal"), ("Screen", "screen"), ("Overlay", "overlay"), ("Soft light", "soft"), ("Additive", "add")],
            ),
            "How the lyrics mix with the wallpaper colors",
        )
        self.sec(lay, "Screen")
        mon = QSpinBox()
        mon.setRange(1, max(1, len(QGuiApplication.screens())))
        mon.setValue(int(self.cfg["holo_screen"]) + 1)
        mon.setFixedWidth(100)
        mon.valueChanged.connect(lambda v: self.set_val("holo_screen", v - 1))
        self.row(lay, "Overlay monitor", mon)
        self.row(lay, "Overlay lyric size", self.slider("holo_scale", 50, 220, "%"))
        self.row(lay, "Line width", self.slider("holo_width", 25, 70, "%"), "Maximum width of a lyric line as a share of the screen")
        self.row(lay, "Distance from card", self.slider("card_gap", 0, 80, " px"), "Lyrics always stay clear of the player card by at least this much")
        self.row(lay, "Motion", self.slider("motion", 0, 200, "%"), "How far lines slide, drift and zoom as they enter and leave. 0 is a plain fade")
        self.row(
            lay,
            "Animation rate",
            self.combo("fps", [("24 fps", 24), ("30 fps", 30), ("45 fps", 45), ("60 fps", 60)]),
            "Lower values use less CPU on large screens",
        )
        self.row(
            lay,
            "Line entrance",
            self.combo("enter_style", [("Classic slide", "classic"), ("Rise", "rise"), ("Zoom", "zoom"), ("Fade only", "fade")]),
            "How each lyric line arrives",
        )
        self.sec(lay, "Effects")
        self.row(lay, "3D tilt", self.switch("tilt"), "Lines swing in with a perspective tilt toward the screen center")
        self.row(lay, "Scanlines", self.switch("scanlines"))
        self.row(lay, "Glitch and chroma ghost", self.switch("glitch"))
        self.row(lay, "Chroma ghost strength", self.slider("ghost", 0, 200, "%"))
        self.row(lay, "Floating particles", self.switch("particles"))
        self.row(lay, "Particle count", self.slider("particle_count", 0, 120))
        self.row(lay, "Particle speed", self.slider("particle_speed", 20, 300, "%"))
        self.row(lay, "Particle size", self.slider("particle_size", 40, 300, "%"))
        self.row(lay, "Now playing toast", self.switch("show_toast"), "Shows the title and artist at the top of the screen when a song starts")
        self.row(lay, "Toast duration", self.slider("toast_secs", 2, 12, " s"))
        lay.addStretch(1)

    def build_player(self):
        lay = self.new_page()
        self.sec(lay, "Controls")
        self.row(lay, "Show volume bar", self.switch("show_volume"), "Controls system output volume; scroll over the card to change it too")
        self.sec(lay, "Window")
        self.row(
            lay,
            "Lock card in place",
            self.switch("click_through"),
            "The card can't be moved or resized, clicks pass through it everywhere except the controls. Unlock again from the tray menu",
        )
        reset = QPushButton("Reset card position")
        reset.clicked.connect(self.ctl.reset_hud)
        self.row(lay, "Card position", reset)
        lay.addStretch(1)

    def build_about(self):
        lay = self.new_page()
        self.sec(lay, "How it works")
        for t in (
            "Reads the Windows media session, so Spotify, YouTube Music in a browser and other players work with no client ID.",
            "Synced lyrics come from LRCLIB and are cached on disk.",
            "Click the progress bar to seek. Scroll over the card for volume. Right-click the card for the quick menu.",
            "Browsers need hardware media control enabled, which is on by default in Chrome, Brave and Edge.",
        ):
            l = QLabel(t)
            l.setObjectName("hint")
            l.setWordWrap(True)
            l.setContentsMargins(0, 4, 0, 4)
            lay.addWidget(l)
        self.sec(lay, "Credits")
        cr = QLabel("Lyrics HUD is made by CyberSecPwner.")
        cr.setObjectName("rowlabel")
        cr.setWordWrap(True)
        cr.setContentsMargins(0, 4, 0, 4)
        lay.addWidget(cr)
        lay.addStretch(1)

    def update_font_info(self):
        th = self.ctl.theme
        if self.cfg["font_path"] and not th.font_ok:
            self.font_info.setText("Could not load this font file, using the default")
        elif self.cfg["font_path"]:
            self.font_info.setText(f"Loaded family: {th.family}")
        else:
            self.font_info.setText("Using Segoe UI")

    def pick_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose font file", str(FONT_DIR), "Fonts (*.ttf *.otf *.ttc)")
        if path:
            self.cfg["font_path"] = path
            self.font_edit.setText(path)
            self.ctl.refresh()
            self.update_font_info()
            self.fill_font_combo()

    def clear_font(self):
        self.cfg["font_path"] = ""
        self.font_edit.setText("")
        self.ctl.refresh()
        self.update_font_info()
        self.fill_font_combo()

    def fill_font_combo(self):
        c = self.font_combo
        c.blockSignals(True)
        c.clear()
        c.addItem("Default (Segoe UI)", "")
        for p in list_font_files():
            c.addItem(p.stem, str(p))
        cur = self.cfg["font_path"]
        i = c.findData(cur)
        if cur and i < 0:
            c.addItem(Path(cur).name, cur)
            i = c.count() - 1
        c.setCurrentIndex(max(0, i))
        c.blockSignals(False)

    def on_font_combo(self, _):
        path = self.font_combo.currentData() or ""
        self.cfg["font_path"] = path
        self.font_edit.setText(path)
        self.ctl.refresh()
        self.update_font_info()

    def search_fonts(self):
        self.dl_info.setText("Searching...")
        self.fnet.load_index()

    def on_index_ready(self):
        q = self.font_query.text().strip().lower()
        found = [f for f in (FontNet.index or []) if q in f[0].lower()]
        found.sort(key=lambda f: (not f[0].lower().startswith(q), f[0].lower()))
        self.result_combo.clear()
        for name, cat, variants in found[:60]:
            self.result_combo.addItem(f"{name} ({cat})" if cat else name, (name, variants))
        self.dl_button.setEnabled(bool(found))
        if found:
            self.dl_info.setText(f"{len(found)} found" + (", showing the first 60" if len(found) > 60 else ""))
        else:
            self.dl_info.setText("No fonts found")

    def on_index_failed(self, msg):
        self.dl_info.setText("Could not reach Google Fonts: " + msg)

    def download_font(self):
        d = self.result_combo.currentData()
        if not d:
            return
        self.dl_info.setText(f"Downloading {d[0]}...")
        self.dl_button.setEnabled(False)
        self.fnet.download(d[0], d[1])

    def on_downloaded(self, path):
        self.dl_button.setEnabled(True)
        self.dl_info.setText("Saved to " + path)
        self.fill_font_combo()

    def on_download_failed(self, msg):
        self.dl_button.setEnabled(True)
        self.dl_info.setText("Download failed: " + msg)

    def on_reset(self):
        self.cfg.reset()
        self.ctl.refresh()
        self.close()
        self.ctl.open_settings()


def make_icon(pal):
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(AA)
    g = QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, pal.accent)
    g.setColorAt(1, pal.secondary)
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(4, 4, 56, 56), 14, 14)
    p.setFont(QFont("Segoe UI Symbol", 30, QFont.Weight.Bold))
    p.setPen(pal.bg)
    p.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return QIcon(pm)


class HotkeyWorker(QThread):
    fired = pyqtSignal(str)
    KEYS = (("later", 0x4A), ("earlier", 0x4B), ("reset", 0x48), ("snap", 0x4E), ("toggle", 0x56))

    def __init__(self):
        super().__init__()
        self.tid = 0

    def run(self):
        u = ctypes.windll.user32
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        ids = {}
        for n, (name, vk) in enumerate(self.KEYS, 1):
            if u.RegisterHotKey(None, n, 0x4007, vk):
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


class Controller:
    MODES = ("hud", "holo", "both")

    def __init__(self, app):
        self.app = app
        self.cfg = Config()
        self.theme = Theme(self.cfg)
        self.state = State(self.cfg)
        self.volume = VolumeControl()
        self.vol_level = 0.5
        self.vol_muted = False
        self.hud = Hud(self)
        self.holo = Holo(self)
        self.settings = None
        self.menu = self.build_menu()
        self.tray = QSystemTrayIcon(make_icon(self.state.pal_target))
        self.tray.setToolTip("Lyrics HUD")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.state.palette_changed.connect(self.on_palette)
        self.on_palette()
        self.worker = MediaWorker(self.state.cmds)
        self.worker.media.connect(self.state.on_media)
        self.worker.start()
        self.hotkeys = None
        self.vol_timer = QTimer()
        self.vol_timer.timeout.connect(self.poll_volume)
        self.vol_timer.start(500)
        self.poll_volume()
        self.apply_mode()
        self.apply_hotkeys()
        app.aboutToQuit.connect(self.shutdown)

    def build_menu(self):
        m = QMenu()
        m.addAction("Play / pause", self.state.toggle_play)
        m.addAction("Next track", self.state.skip_next)
        m.addAction("Previous track", self.state.skip_prev)
        m.addSeparator()
        m.addAction("Show / hide", self.toggle_visible)
        sub = m.addMenu("Display mode")
        group = QActionGroup(sub)
        group.setExclusive(True)
        self.mode_actions = {}
        for label, val in (("Player card", "hud"), ("Floating lyrics", "holo"), ("Card + floating lyrics", "both")):
            a = QAction(label, sub)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, v=val: self.set_mode(v))
            group.addAction(a)
            sub.addAction(a)
            self.mode_actions[val] = a
        self.act_lock = QAction("Lock card in place", m)
        self.act_lock.setCheckable(True)
        self.act_lock.triggered.connect(self.toggle_lock)
        m.addAction(self.act_lock)
        m.addSeparator()
        m.addAction("Lyrics earlier (+100 ms)", lambda: self.nudge(100))
        m.addAction("Lyrics later (-100 ms)", lambda: self.nudge(-100))
        m.addAction("Reset sync offset", lambda: self.nudge(None))
        m.addAction("Sync: current line starts now", lambda: self.snap(0))
        m.addAction("Sync: next line starts now", lambda: self.snap(1))
        m.addSeparator()
        m.addAction("Settings", self.open_settings)
        m.addAction("Reset card position", self.reset_hud)
        m.addSeparator()
        m.addAction("Quit", self.app.quit)
        m.aboutToShow.connect(self.sync_menu)
        return m

    def on_palette(self):
        pal = self.state.pal_target
        self.menu.setStyleSheet(build_qss(pal))
        self.tray.setIcon(make_icon(pal))
        self.hud.dirty = True
        self.holo.dirty = True

    def sync_menu(self):
        self.act_lock.setChecked(bool(self.cfg["click_through"]))
        for val, a in self.mode_actions.items():
            a.setChecked(self.cfg["mode"] == val)

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        self.cfg["visible"] = not self.cfg["visible"]
        self.apply_mode()
        self.cfg.save()

    def hide_all(self):
        self.cfg["visible"] = False
        self.apply_mode()
        self.cfg.save()

    def toggle_lock(self):
        self.cfg["click_through"] = not self.cfg["click_through"]
        self.refresh()

    def set_mode(self, mode):
        self.cfg["mode"] = mode
        self.cfg["visible"] = True
        self.refresh()

    def cycle_mode(self):
        i = self.MODES.index(self.cfg["mode"]) if self.cfg["mode"] in self.MODES else 0
        self.set_mode(self.MODES[(i + 1) % len(self.MODES)])

    def nudge(self, delta):
        st = self.state
        if self.cfg["auto_sync"] and st.active:
            if delta is None:
                st.set_track_ms(0)
                self.cfg["offset_ms"] = 0
            else:
                st.set_track_ms(st.track_ms() + delta)
        elif delta is None:
            self.cfg["offset_ms"] = 0
        else:
            self.cfg["offset_ms"] = int(clamp(self.cfg["offset_ms"] + delta, -5000, 5000))
        self.cfg.save()
        self.hud.dirty = True

    def reset_hud(self):
        self.hud.reset_pos()

    def poll_volume(self):
        r = self.volume.get()
        if r is None:
            return
        if r != (self.vol_level, self.vol_muted):
            self.vol_level, self.vol_muted = r
            self.hud.dirty = True

    def set_volume(self, v):
        v = clamp(v, 0.0, 1.0)
        self.volume.set(v)
        self.vol_level = v
        self.vol_muted = False
        self.hud.dirty = True

    def change_volume(self, d):
        self.set_volume(self.vol_level + d)

    def toggle_mute(self):
        self.vol_muted = not self.vol_muted
        self.volume.set_mute(self.vol_muted)
        self.hud.dirty = True

    def open_settings(self):
        if self.settings is not None and self.settings.isVisible():
            self.settings.raise_()
            self.settings.activateWindow()
            return
        self.settings = SettingsDialog(self)
        self.settings.show()

    def apply_mode(self):
        mode = self.cfg["mode"]
        visible = bool(self.cfg["visible"])
        if visible and mode in ("hud", "both"):
            if not self.hud.isVisible():
                self.hud.show()
        else:
            self.hud.hide()
        if visible and mode in ("holo", "both"):
            self.holo.place()
            self.holo.attach_wall()
            if not self.holo.isVisible():
                self.holo.show()
        else:
            self.holo.hide()

    def refresh(self):
        self.theme.reload()
        self.state.recompute_palette()
        self.hud.refresh()
        self.holo.refresh()
        self.apply_mode()
        self.apply_hotkeys()
        self.cfg.save()

    def shutdown(self):
        self.stop_hotkeys()
        self.worker.stop()
        self.worker.wait(1500)
        self.hud.save_geometry()
        self.cfg.save()
        self.tray.hide()

    def snap(self, which):
        if self.state.snap(which):
            self.cfg.save()
            self.hud.dirty = True

    def apply_hotkeys(self):
        if self.cfg["hotkeys"] and self.hotkeys is None:
            self.hotkeys = HotkeyWorker()
            self.hotkeys.fired.connect(self.on_hotkey)
            self.hotkeys.start()
        elif not self.cfg["hotkeys"]:
            self.stop_hotkeys()

    def stop_hotkeys(self):
        if self.hotkeys is not None:
            self.hotkeys.stop()
            self.hotkeys.wait(1500)
            self.hotkeys = None

    def on_hotkey(self, name):
        if name == "later":
            self.nudge(-100)
        elif name == "earlier":
            self.nudge(100)
        elif name == "reset":
            self.nudge(None)
        elif name == "snap":
            self.snap(1)
        elif name == "toggle":
            self.toggle_visible()


def selftest():
    """Build check: PyQt, winrt media session and optional volume control."""
    lines = []
    code = 0
    try:
        app = QApplication(sys.argv[:1])
        lines.append("PyQt6 OK")
    except Exception as e:
        lines.append("PyQt6 FAILED: %r" % (e,))
        code = 2
    try:
        async def go():
            mgr = await SessionManager.request_async()
            mgr.get_sessions()

        asyncio.run(go())
        lines.append("winrt media session OK")
    except Exception as e:
        lines.append("winrt media session FAILED: %r" % (e,))
        code = 2
    try:
        lines.append("volume control: " + ("OK" if VolumeControl().available else "unavailable (optional)"))
    except Exception as e:
        lines.append("volume control: unavailable (%r)" % (e,))
    try:
        out = Path(os.environ.get("TEMP") or Path.home()) / "LyricsScreen_selftest.txt"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return code


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("LyricsHUD")
    app.setQuitOnLastWindowClosed(False)
    ctl = Controller(app)
    code = app.exec()
    del ctl
    sys.exit(code)


if __name__ == "__main__":
    main()
