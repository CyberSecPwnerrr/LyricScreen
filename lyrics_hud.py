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
import base64
import zlib
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

os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*=false;qt.multimedia.ffmpeg.*=false;qt.multimedia.ffmpeg=false"
os.environ.setdefault("QT_FFMPEG_DEBUG", "0")

REQUIRED = [
    ("PyQt6", "PyQt6"),
    ("winrt.runtime", "winrt-runtime"),
    ("winrt.windows.foundation", "winrt-Windows.Foundation"),
    ("winrt.windows.foundation.collections", "winrt-Windows.Foundation.Collections"),
    ("winrt.windows.media", "winrt-Windows.Media"),
    ("winrt.windows.media.control", "winrt-Windows.Media.Control"),
    ("winrt.windows.storage.streams", "winrt-Windows.Storage.Streams"),
]

OPTIONAL = [("comtypes", "comtypes"), ("pycaw", "pycaw"), ("qrcode", "qrcode"), ("PIL", "pillow"), ("psutil", "psutil")]


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
    k = ctypes.windll.kernel32
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.windll.shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SEI)]
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    os.environ.pop("_MEIPASS2", None)
    sei = _SEI()
    sei.cbSize = ctypes.sizeof(_SEI)
    sei.fMask = 0x00000040
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = 0
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
    if "--install-copy" in sys.argv:
        i = sys.argv.index("--install-copy")
        sys.exit(_do_copy(Path(sys.argv[i + 1]), Path(sys.argv[i + 2])))
    if "--make-font-dir" in sys.argv:
        i = sys.argv.index("--make-font-dir")
        sys.exit(_make_font_dir(Path(sys.argv[i + 1])))
    exe = Path(sys.executable)
    target_dir = _install_dir()
    target = target_dir / EXE_NAME
    if _same_path(exe.parent, target_dir):
        return
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
            return
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
            creationflags=0x00000008 | 0x00000200,
        )
    except Exception as e:
        _msgbox("Installed, but could not start the app:\n" + str(e))
        sys.exit(1)
    sys.exit(0)


self_install()
if not FROZEN:
    ensure_packages()

from PyQt6.QtCore import (
    Qt,
    QThread,
    QObject,
    QTimer,
    QRect,
    QRectF,
    QPointF,
    QPoint,
    QUrl,
    QEvent,
    QAbstractAnimation,
    QPropertyAnimation,
    QVariantAnimation,
    QEasingCurve,
    pyqtSignal,
)
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
    QPolygonF,
    QMovie,
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
    QSizeGrip,
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
    QGraphicsOpacityEffect,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

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
PROFILE_DIR = APP_DIR / "profiles"
APP_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
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
    "optimize": "off",
    "show_cover": True,
    "show_volume": True,
    "click_through": False,
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
    "lyrics_over_ui": False,
    "always_on_top": True,
    "autohide_fullscreen": False,
    "app_volume": True,
    "text_image_on": False,
    "text_image": "",
    "clock_bg_image": "",
    "clock_bg_image_opacity": 60,
    "clock_bg_image_blur": 35,
    "bar_mode": "custom",
    "bar_pos": "top",
    "bar_align": "left",
    "bar_btn_pos": "right",
    "bar_height": 46,
    "bar_brand": True,
    "bar_page": True,
    "bar_eq": False,
    "bar_eq_style": "bars",
    "bar_eq_bars": 18,
    "bar_eq_color": "gradient",
    "show_toast": True,
    "card_radius": 20,
    "backdrop": 34,
    "show_album": True,
    "show_status": True,
    "layer": "top",
    "wall_dim": 25,
    "wall_blend": "normal",
    "enter_style": "classic",
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
    "theme": "cyber",
    "adaptive_mode": "vibrant",
    "custom_bg": False,
    "bg_color": "#0b0614",
    "glass": 92,
    "blur": True,
    "card_shadow": 55,
    "border_alpha": 100,
    "card_style": "gradient",
    "hud_scale": 100,
    "card_size": "medium",
    "ui_font": 100,
    "bg_image": "",
    "bg_image_opacity": 60,
    "bg_image_blur": 35,
    "exit_style": "float",
    "idle_anim": "float",
    "show_welcome": True,
    "welcomed": False,
    "show_clock": True,
    "clock_24h": True,
    "clock_seconds": True,
    "clock_date": True,
    "clock_scale": 100,
    "clock_opacity": 100,
    "clock_x": None,
    "clock_y": None,
    "lyric_color": "#ffffff",
    "lyric_color2": "#ffd1f0",
    "scan_strength": 35,
    "scan_gap": 3,
    "glitch_amount": 100,
    "flicker": 100,
    "frost": 70,
    "border_width": 1,
    "menu_image": "",
    "menu_image_opacity": 55,
    "menu_blur": 40,
    "menu_dim": 35,
    "menu_anim": True,
    "launch_audio_on": False,
    "launch_audio": "",
    "launch_audio_volume": 70,
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
QWidget#side{background:@BG2A@;border-right:1px solid @LINE@;}
QWidget#main{background:transparent;}
QLabel{color:@TX@;background:transparent;}
QLabel#brand{color:@ACC@;font-size:13px;font-weight:800;letter-spacing:5px;padding:20px 18px 0px 18px;}
QLabel#title{font-size:22px;font-weight:700;color:@TX@;padding:18px 24px 2px 24px;}
QLabel#brand,QLabel#title{font-family:"@FAM@";}
QLabel#section{color:@ACC@;font-size:11px;font-weight:800;letter-spacing:3px;padding:1px 0 1px 10px;margin:14px 0 6px 0;border-left:3px solid @ACC@;}
QPushButton#sechead{background:transparent;border:none;border-bottom:1px solid @LINE@;border-radius:0px;color:@DIM@;font-size:11px;font-weight:800;letter-spacing:2px;text-align:left;padding:11px 24px 9px 2px;margin-top:6px;}
QPushButton#sechead:hover{background:transparent;color:@TX@;border-bottom:1px solid @ACC@;}
QPushButton#sechead:checked{color:@ACC@;}
QLabel#rowlabel{color:@TX@;font-size:12px;font-weight:600;}
QLabel#hint{color:@DIM@;font-size:11px;}
QLabel#nptitle{color:@TX@;font-size:11px;font-weight:700;}
QLabel#npartist{color:@DIM@;font-size:10px;}
QWidget#npcard{background:@SFA@;border:1px solid @LINE@;border-radius:10px;}
QListWidget#nav{background:transparent;border:none;outline:none;padding:4px 8px;}
QListWidget#nav::item{color:@DIM@;padding:8px 14px;border:none;background:transparent;font-size:12px;font-weight:600;}
QListWidget#nav::item:hover{color:@TX@;background:transparent;}
QListWidget#nav::item:selected{color:@TX@;background:transparent;}
QScrollArea{border:none;background:transparent;}
QScrollArea>QWidget>QWidget{background:transparent;}
QScrollBar:vertical{background:transparent;width:6px;margin:2px;}
QScrollBar::handle:vertical{background:@LINE@;border-radius:3px;min-height:30px;}
QScrollBar::handle:vertical:hover{background:@ACC@;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QPushButton{background:@SFA@;border:1px solid @LINE@;border-radius:8px;padding:6px 14px;color:@TX@;font-size:12px;font-weight:600;}
QPushButton:hover{border-color:@ACC@;background:@ACCA@;}
QPushButton:pressed{background:@ACCA2@;}
QPushButton:disabled{color:@DIM@;border-color:@LINE@;}
QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);color:@BG@;border:none;font-weight:800;padding:7px 24px;}
QPushButton#primary:hover{background:@SEC@;}
QPushButton#seg{border-radius:8px;padding:6px 14px;}
QPushButton#seg:checked{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);color:@BG@;border-color:@ACC@;font-weight:800;}
QPushButton#pos{background:@SFA@;border:1px solid @LINE@;border-radius:7px;color:@DIM@;font-size:10px;font-weight:700;padding:0;}
QPushButton#pos:checked{background:@ACCA2@;border-color:@ACC@;color:@TX@;}
QSlider::groove:horizontal{height:4px;background:@LINE@;border-radius:2px;}
QSlider::sub-page:horizontal{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 @ACC@,stop:1 @SEC@);border-radius:2px;}
QSlider::handle:horizontal{background:@TX@;width:12px;height:12px;margin:-5px 0;border-radius:6px;border:2px solid @ACC@;}
QSlider::handle:horizontal:hover{background:@ACC@;width:14px;height:14px;margin:-6px 0;border-radius:7px;border:2px solid @TX@;}
QComboBox,QSpinBox,QLineEdit{background:@SFA@;border:1px solid @LINE@;border-radius:8px;padding:5px 10px;color:@TX@;font-size:12px;selection-background-color:@ACC@;selection-color:@BG@;}
QComboBox:hover,QSpinBox:hover,QLineEdit:hover{border-color:@ACC@;}
QComboBox::drop-down{border:none;width:22px;}
QComboBox QAbstractItemView{background:@BG2@;color:@TX@;border:1px solid @LINE@;border-radius:8px;selection-background-color:@ACCA@;outline:none;padding:4px;}
QSpinBox::up-button,QSpinBox::down-button{width:0;border:none;}
QToolTip{background:@BG2@;color:@TX@;border:1px solid @ACC@;border-radius:6px;padding:5px;}
QMenu{background:@BG2@;color:@TX@;border:1px solid @LINE@;border-radius:10px;padding:6px;}
QMenu::item{padding:8px 26px 8px 18px;border-radius:7px;}
QMenu::item:selected{background:@ACCA@;}
QMenu::separator{height:1px;background:@LINE@;margin:5px 8px;}
QMenu::indicator{width:14px;height:14px;}
QMenu#glass{background:transparent;border:none;padding:9px;}
QMenu#glass::item{padding:9px 30px 9px 18px;border-radius:10px;margin:1px 0;}
QMenu#glass::item:selected{background:@ACCA2@;}
QMenu#glass::separator{height:1px;background:@LINE@;margin:6px 12px;}
"""


class _MI(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def fullscreen_app_active():
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.MonitorFromWindow.restype = wintypes.HANDLE
        u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MI)]
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        pid = wintypes.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        r = wintypes.RECT()
        if not u.GetWindowRect(hwnd, ctypes.byref(r)):
            return False
        mon = u.MonitorFromWindow(hwnd, 2)
        mi = _MI()
        mi.cbSize = ctypes.sizeof(_MI)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
    except Exception:
        return False


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


OPTIMIZE_ITEMS = [("Off", "off"), ("Balanced", "balanced"), ("Performance", "performance")]
OPTIMIZE_CAPS = {"off": 144, "balanced": 45, "performance": 30}


def eff_fps(cfg):
    cap = OPTIMIZE_CAPS.get(cfg["optimize"], 144)
    return int(clamp(min(int(cfg["fps"]), cap), 10, 144))


def clear_lyrics_cache():
    count = 0
    size = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            size += f.stat().st_size
            f.unlink()
            count += 1
        except Exception:
            pass
    return count, size


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


LYRIC_GRADIENTS = {
    "fire": ("#ff3d00", "#ffd600"),
    "ocean": ("#00c6ff", "#7af7c1"),
    "sunset": ("#ff5f6d", "#ffc371"),
    "candy": ("#ff6ec7", "#7873f5"),
    "mint": ("#43e97b", "#38f9d7"),
    "gold": ("#f9d423", "#ff8a00"),
    "ice": ("#ffffff", "#74c7ff"),
    "rose": ("#ff9a9e", "#fad0c4"),
    "toxic": ("#b6ff3d", "#00ffa3"),
    "royal": ("#a259ff", "#4facfe"),
}


def lyric_colors(cfg, pal):
    white = QColor(255, 255, 255)
    fill = QColor(pal.text)
    fill2 = None
    mode = cfg["lyric_fill"]
    if cfg["adaptive"] and (mode == "custom" or mode in LYRIC_GRADIENTS):
        mode = "duo"
    if mode == "soft":
        fill2 = mix(pal.text, pal.secondary, 0.55)
    elif mode == "duo":
        fill = mix(pal.accent, white, 0.3)
        fill2 = mix(pal.secondary, white, 0.3)
    elif mode == "accent":
        fill = mix(pal.accent, white, 0.25)
    elif mode == "secondary":
        fill = mix(pal.secondary, white, 0.25)
    elif mode == "custom":
        fill = QColor(cfg["lyric_color"])
        fill2 = QColor(cfg["lyric_color2"])
    elif mode in LYRIC_GRADIENTS:
        fill, fill2 = (QColor(c) for c in LYRIC_GRADIENTS[mode])
    gc = {"secondary": pal.secondary, "text": pal.text}.get(cfg["glow_color"], pal.accent)
    return fill, fill2, QColor(gc)

PRESETS = [
    ("Neon Pink", "#ff2a6d", "#05d9e8", "#f4eeff"),
    ("Ocean", "#00b4ff", "#00ffd0", "#eafcff"),
    ("Sunset", "#ff7a3d", "#ffd23f", "#fff4ea"),
    ("Forest", "#3dff8b", "#b6ff3d", "#effff4"),
    ("Violet", "#a259ff", "#ff59d6", "#f6efff"),
    ("Crimson", "#ff3b3b", "#ff9a3b", "#fff0f0"),
    ("Ice", "#7ad7ff", "#ffffff", "#f5fbff"),
    ("Mono", "#ffffff", "#9a9a9a", "#f2f2f2"),
    ("Synthwave", "#ff3cac", "#2b86c5", "#fdf0ff"),
    ("Midnight", "#6ea8ff", "#9b8cff", "#eef3ff"),
    ("Sakura", "#ff8fb8", "#ffd1e3", "#fff5f9"),
    ("Ember", "#ff6a1a", "#ffb347", "#fff3e8"),
    ("Emerald", "#2ee6a6", "#7dffd8", "#eafff6"),
    ("Lavender", "#b69cff", "#e2d6ff", "#f7f3ff"),
    ("Gold", "#ffcc33", "#ff8a00", "#fffaf0"),
    ("Aqua", "#19e3ff", "#7affc4", "#effdff"),
    ("Cherry", "#ff2d55", "#ff8aa5", "#fff0f3"),
    ("Lime", "#c6ff3d", "#3dff9a", "#f8ffe9"),
    ("Candy", "#ff6ec7", "#7873f5", "#fff0fa"),
    ("Steel", "#8fa3b8", "#d6e2ee", "#f1f5f9"),
]

THEME_LABELS = [
    ("Cyber Neon", "cyber"),
    ("Frosted Glass", "frosted"),
    ("Pure Minimal", "minimal"),
    ("Aurora", "aurora"),
    ("Synthwave", "synthwave"),
    ("Midnight", "midnight"),
    ("Sakura", "sakura"),
    ("Ember", "ember"),
    ("Emerald", "emerald"),
    ("Crystal", "crystal"),
    ("Custom", "custom"),
]

THEME_HINTS = {
    "cyber": "Neon glow, animated border, scanlines and glitch effects with colors pulled from the album art.",
    "frosted": "Blurred glass with a soft grain, a light sheen that glides across the card and a bright glass edge.",
    "minimal": "A flat dark card with no glow and gentle fades.",
    "aurora": "A slowly drifting aurora of light behind the card, with rising lyrics.",
    "synthwave": "Pink and blue retro neon with a sunset lyric gradient, scanlines and glitch.",
    "midnight": "Deep navy with cool blue light and soft icy lyrics.",
    "sakura": "Blossom pink frosted glass with dropping lyrics and a gentle sway.",
    "ember": "Glowing orange on charcoal with fiery lyrics and bouncy entrances.",
    "emerald": "Green aurora light on a dark forest card with minty lyrics.",
    "crystal": "Bright, clear glass with a strong frost, a thick white edge and calm fades.",
    "custom": "Your own mix. Every setting stays exactly as you set it.",
}

THEMES = {
    "cyber": {
        "accent": "#ff2a6d",
        "secondary": "#05d9e8",
        "text": "#f4eeff",
        "adaptive": True,
        "adaptive_mode": "vibrant",
        "custom_bg": False,
        "card_style": "gradient",
        "glass": 92,
        "blur": True,
        "card_radius": 20,
        "backdrop": 34,
        "card_shadow": 55,
        "border_alpha": 100,
        "card_glow": 60,
        "glow": 70,
        "scanlines": True,
        "glitch": True,
        "tilt": True,
        "ghost": 100,
        "lyric_fill": "soft",
        "enter_style": "classic",
        "exit_style": "float",
        "idle_anim": "float",
        "motion": 100,
        "show_eq": True,
    },
    "frosted": {
        "accent": "#bfe3ff",
        "secondary": "#ffffff",
        "text": "#ffffff",
        "adaptive": False,
        "adaptive_mode": "vibrant",
        "custom_bg": True,
        "bg_color": "#243448",
        "card_style": "frosted",
        "glass": 58,
        "blur": True,
        "card_radius": 28,
        "backdrop": 26,
        "card_shadow": 70,
        "border_alpha": 150,
        "card_glow": 0,
        "glow": 22,
        "frost": 80,
        "border_width": 1,
        "scanlines": False,
        "glitch": False,
        "tilt": False,
        "ghost": 0,
        "lyric_fill": "solid",
        "enter_style": "fade",
        "exit_style": "fade",
        "idle_anim": "float",
        "motion": 70,
        "show_eq": True,
    },
    "minimal": {
        "accent": "#ffffff",
        "secondary": "#9a9a9a",
        "text": "#f2f2f2",
        "adaptive": False,
        "adaptive_mode": "vibrant",
        "custom_bg": True,
        "bg_color": "#101010",
        "card_style": "flat",
        "glass": 96,
        "blur": False,
        "card_radius": 12,
        "backdrop": 0,
        "card_shadow": 30,
        "border_alpha": 60,
        "card_glow": 0,
        "glow": 0,
        "scanlines": False,
        "glitch": False,
        "tilt": False,
        "ghost": 0,
        "lyric_fill": "solid",
        "enter_style": "fade",
        "exit_style": "fade",
        "idle_anim": "none",
        "motion": 40,
        "show_eq": False,
    },
    "aurora": {
        "accent": "#7cffcb",
        "secondary": "#8a7bff",
        "text": "#f5f8ff",
        "adaptive": False,
        "adaptive_mode": "vibrant",
        "custom_bg": True,
        "bg_color": "#071320",
        "card_style": "aurora",
        "glass": 80,
        "blur": True,
        "card_radius": 24,
        "backdrop": 25,
        "card_shadow": 60,
        "border_alpha": 110,
        "card_glow": 70,
        "glow": 60,
        "scanlines": False,
        "glitch": False,
        "tilt": True,
        "ghost": 60,
        "lyric_fill": "duo",
        "enter_style": "rise",
        "exit_style": "float",
        "idle_anim": "sway",
        "motion": 100,
        "show_eq": True,
    },
}

THEMES.update(
    {
        "synthwave": dict(
            THEMES["cyber"],
            accent="#ff3cac",
            secondary="#2b86c5",
            text="#fdf0ff",
            adaptive=False,
            custom_bg=True,
            bg_color="#140a2e",
            glow=80,
            lyric_fill="sunset",
            enter_style="stretch",
        ),
        "midnight": dict(
            THEMES["cyber"],
            accent="#6ea8ff",
            secondary="#9b8cff",
            text="#eef3ff",
            adaptive=False,
            custom_bg=True,
            bg_color="#070b1a",
            card_glow=40,
            glow=45,
            scanlines=False,
            glitch=False,
            ghost=40,
            lyric_fill="ice",
            enter_style="rise",
        ),
        "sakura": dict(
            THEMES["cyber"],
            accent="#ff8fb8",
            secondary="#ffd1e3",
            text="#fff5f9",
            adaptive=False,
            custom_bg=True,
            bg_color="#2a1520",
            card_style="frosted",
            glass=62,
            card_radius=26,
            backdrop=22,
            border_alpha=140,
            card_glow=0,
            glow=45,
            scanlines=False,
            glitch=False,
            tilt=False,
            ghost=0,
            lyric_fill="rose",
            enter_style="drop",
            idle_anim="sway",
        ),
        "ember": dict(
            THEMES["cyber"],
            accent="#ff6a1a",
            secondary="#ffb347",
            text="#fff3e8",
            adaptive=False,
            custom_bg=True,
            bg_color="#160a05",
            glow=75,
            scanlines=False,
            ghost=60,
            lyric_fill="fire",
            enter_style="bounce",
            idle_anim="pulse",
        ),
        "emerald": dict(
            THEMES["cyber"],
            accent="#2ee6a6",
            secondary="#7dffd8",
            text="#eafff6",
            adaptive=False,
            custom_bg=True,
            bg_color="#04140f",
            card_style="aurora",
            glass=82,
            card_glow=60,
            scanlines=False,
            glitch=False,
            ghost=40,
            lyric_fill="mint",
            enter_style="rise",
            idle_anim="sway",
        ),
        "crystal": dict(
            THEMES["frosted"],
            accent="#ffffff",
            secondary="#cfe8ff",
            bg_color="#3a5170",
            glass=46,
            card_radius=32,
            backdrop=34,
            border_alpha=170,
            border_width=2,
            frost=100,
            glow=18,
            motion=60,
        ),
    }
)

ADAPTIVE_MODES = [
    ("Vibrant (cover colors)", "vibrant"),
    ("Pastel", "pastel"),
    ("Deep", "deep"),
    ("Complementary", "complement"),
    ("Triadic", "triad"),
    ("Analogous", "analog"),
    ("Monochrome", "mono"),
]

CARD_STYLES = [
    ("Gradient", "gradient"),
    ("Frosted glass", "frosted"),
    ("Flat", "flat"),
    ("Aurora (animated)", "aurora"),
]

CARD_SIZES = {
    "small": (440, 400),
    "medium": (520, 540),
    "large": (640, 600),
    "wide": (780, 640),
    "huge": (940, 720),
}

CARD_SIZE_ITEMS = [("Small", "small"), ("Medium", "medium"), ("Large", "large"), ("Wide", "wide"), ("Huge", "huge")]

ENTER_ITEMS = [
    ("Classic slide", "classic"),
    ("Rise", "rise"),
    ("Drop", "drop"),
    ("Zoom", "zoom"),
    ("Fade only", "fade"),
    ("Flip", "flip"),
    ("Bounce", "bounce"),
    ("Stretch", "stretch"),
    ("Swing", "swing"),
    ("Spin", "spin"),
    ("Random", "random"),
]

EXIT_ITEMS = [
    ("Float away", "float"),
    ("Fade only", "fade"),
    ("Shrink", "shrink"),
    ("Sink", "drop"),
    ("Slide out", "slide"),
    ("Random", "random"),
]

RANDOM_ENTER = ["classic", "rise", "drop", "zoom", "fade", "flip", "bounce", "stretch", "swing", "spin"]
RANDOM_EXIT = ["float", "fade", "shrink", "drop", "slide"]
RAND_SALT = [0]


def random_pick(pool, i, salt):
    return random.Random(i * 7919 + RAND_SALT[0] + salt).choice(pool)

IDLE_ITEMS = [("Float", "float"), ("Pulse", "pulse"), ("Sway", "sway"), ("None", "none")]

LYRIC_FILL_ITEMS = [
    ("Solid", "solid"),
    ("Soft gradient", "soft"),
    ("Accent to secondary", "duo"),
    ("Accent", "accent"),
    ("Secondary", "secondary"),
    ("Custom colors", "custom"),
    ("Fire", "fire"),
    ("Ocean", "ocean"),
    ("Sunset", "sunset"),
    ("Candy", "candy"),
    ("Mint", "mint"),
    ("Gold", "gold"),
    ("Ice", "ice"),
    ("Rose", "rose"),
    ("Toxic", "toxic"),
    ("Royal", "royal"),
]

IMG_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
AUDIO_FILTER = "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.wma *.aac)"

PATH_KEYS = ("font_path", "bg_image", "menu_image", "launch_audio", "text_image", "clock_bg_image")

LOCAL_KEYS = ("hud_x", "hud_y", "hud_w", "hud_h", "clock_x", "clock_y", "welcomed")


def ease_back(x):
    x = clamp(x, 0.0, 1.0) - 1.0
    return 1.0 + 2.70158 * x * x * x + 1.70158 * x * x


def shape_colors(acc, sec, mode):
    white = QColor(255, 255, 255)
    black = QColor(0, 0, 0)
    if mode == "pastel":
        return mix(acc, white, 0.4), mix(sec, white, 0.4)
    if mode == "deep":
        return mix(acc, black, 0.28), mix(sec, black, 0.28)
    if mode == "mono":
        return acc, mix(acc, white, 0.5)
    h, s, v, _ = acc.getHsvF()
    shift = {"complement": 0.5, "triad": 1.0 / 3.0, "analog": 0.08}.get(mode)
    if shift is None:
        return acc, sec
    return acc, QColor.fromHsvF((max(0.0, h) + shift) % 1.0, clamp(s, 0.6, 1.0), 1.0)


def line_fx(cfg, enter, eo, side, t, i):
    mo = cfg["motion"] / 100.0
    es = cfg["enter_style"]
    if es == "random":
        es = random_pick(RANDOM_ENTER, i, 1)
    k = 1.0 - enter
    ox = oy = rx = rz = 0.0
    sc = sx = 1.0
    if es == "rise":
        oy = 44.0 * mo * k
    elif es == "drop":
        oy = -44.0 * mo * k
    elif es == "zoom":
        sc = 1.0 - 0.24 * mo * k
    elif es == "flip":
        rx = 80.0 * mo * k
    elif es == "bounce":
        kb = 1.0 - ease_back(enter)
        sc = 1.0 - 0.45 * mo * kb
        oy = 24.0 * mo * kb
    elif es == "stretch":
        sx = 1.0 - 0.7 * mo * k
    elif es == "swing":
        rz = -14.0 * mo * k
        oy = 20.0 * mo * k
    elif es == "spin":
        rz = 90.0 * mo * k
        sc = 1.0 - 0.3 * mo * k
    elif es == "classic":
        ox = side * 60.0 * mo * k
        oy = 30.0 * mo * k if side == 0 else 0.0
        sc = 1.0 - 0.06 * mo * k
    e = ease(eo)
    xs = cfg["exit_style"]
    if xs == "random":
        xs = random_pick(RANDOM_EXIT, i, 2)
    if xs == "shrink":
        sc *= 1.0 - 0.18 * mo * e
    elif xs == "drop":
        oy += 24.0 * mo * e
    elif xs == "slide":
        ox += (side or 1) * 70.0 * mo * e
    elif xs == "float":
        oy -= 20.0 * mo * e
        sc *= 1.0 + 0.03 * mo * e
    idle = cfg["idle_anim"]
    if idle == "float":
        oy += math.sin(t * 1.2 + i) * 5.0 * min(1.0, mo)
    elif idle == "pulse":
        sc *= 1.0 + 0.015 * mo * math.sin(t * 2.4 + i)
    elif idle == "sway":
        rz += math.sin(t * 0.9 + i) * 1.6 * min(1.0, mo)
    return ox, oy, sc, sx, rx, rz


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
    user = os.environ.get("USERNAME") or ""
    display = ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        size = wintypes.ULONG(256)
        if ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size)):
            display = buf.value
    except Exception:
        pass
    return display or user or "there", os.environ.get("COMPUTERNAME") or ""


def list_profiles():
    try:
        return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    except Exception:
        return []


def profile_path(name):
    safe = re.sub(r"[^\w\- ]+", "", name or "").strip()
    return PROFILE_DIR / (safe + ".json") if safe else None


class Config:
    def __init__(self):
        self.data = fresh_defaults()
        try:
            self.apply(json.loads(CFG_PATH.read_text("utf-8")))
        except Exception:
            pass

    def apply(self, loaded, skip=()):
        for k, v in loaded.items():
            if k in skip:
                continue
            if k in DEFAULTS and (not isinstance(DEFAULTS[k], list) or isinstance(v, list)):
                self.data[k] = v

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def save(self):
        try:
            CFG_PATH.write_text(json.dumps(self.data, indent=2), "utf-8")
        except Exception:
            pass

    def snapshot(self):
        return {k: v for k, v in self.data.items() if k not in LOCAL_KEYS}

    def write_to(self, path):
        Path(path).write_text(json.dumps(self.snapshot(), indent=2), "utf-8")

    def read_from(self, path):
        data = json.loads(Path(path).read_text("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a settings file")
        self.apply(data, LOCAL_KEYS)

    def share_code(self):
        diff = {}
        for k, v in self.snapshot().items():
            if v == DEFAULTS[k]:
                continue
            if k in PATH_KEYS:
                continue
            diff[k] = v
        raw = json.dumps(diff, separators=(",", ":")).encode("utf-8")
        return "LH1-" + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")

    def apply_code(self, code):
        code = "".join(code.split())
        if not code.startswith("LH1-"):
            raise ValueError("not a share code")
        body = code[4:]
        body += "=" * (-len(body) % 4)
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(body.encode("ascii"))).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a share code")
        for k in PATH_KEYS:
            data.pop(k, None)
        self.apply(data, LOCAL_KEYS)

    def reset(self):
        keep = {k: self.data[k] for k in LOCAL_KEYS}
        self.data = fresh_defaults()
        self.data.update(keep)


GRAIN = []


def grain():
    if not GRAIN:
        rnd = random.Random(7)
        data = bytearray()
        for _ in range(96 * 96):
            v = rnd.randrange(256)
            data += bytes((v, v, v, 255))
        GRAIN.append(QPixmap.fromImage(QImage(bytes(data), 96, 96, 96 * 4, QImage.Format.Format_ARGB32).copy()))
    return GRAIN[0]


class ImageSrc:
    def __init__(self, path, on_frame):
        self.img = QImage(path)
        self.frames = []
        self.delays = []
        self.total = 0
        self.movie = None
        self.timer = None
        self.t0 = time.monotonic()
        self.last = -1
        self.cb = on_frame
        if path.lower().endswith(".gif"):
            self.load_gif(path)
            if len(self.frames) > 1:
                self.timer = QTimer()
                self.timer.setInterval(33)
                self.timer.timeout.connect(self.poll)
                self.timer.start()
            else:
                self.frames = []
                m = QMovie(path)
                if m.isValid() and m.frameCount() != 1:
                    self.movie = m
                    m.frameChanged.connect(lambda _=0: on_frame())
                    m.start()

    def load_gif(self, path):
        try:
            from PIL import Image, ImageSequence

            im = Image.open(path)
            for fr in ImageSequence.Iterator(im):
                if len(self.frames) >= 240:
                    break
                d = max(20, int(fr.info.get("duration", 100) or 100))
                rgba = fr.convert("RGBA")
                if max(rgba.size) > 960:
                    rgba.thumbnail((960, 960))
                w, h = rgba.size
                qi = QImage(rgba.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
                self.frames.append(qi)
                self.delays.append(d)
            self.total = sum(self.delays)
        except Exception:
            self.frames = []
            self.delays = []
            self.total = 0

    def poll(self):
        n = self.number()
        if n != self.last:
            self.last = n
            self.cb()

    def frame(self):
        if self.frames:
            return self.frames[self.number()]
        if self.movie is not None:
            f = self.movie.currentImage()
            if not f.isNull():
                return f
        return self.img

    def number(self):
        if self.frames:
            ms = int((time.monotonic() - self.t0) * 1000) % max(1, self.total)
            acc = 0
            for i, d in enumerate(self.delays):
                acc += d
                if ms < acc:
                    return i
            return len(self.frames) - 1
        if self.movie is not None:
            return self.movie.currentFrameNumber()
        return 0

    def stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.movie is not None:
            self.movie.stop()
            self.movie = None


TEXT_IMG = {"path": None, "img": None, "sig": 0}


def set_text_image(cfg):
    path = cfg["text_image"] if cfg["text_image_on"] else ""
    if path and os.path.isfile(path):
        if TEXT_IMG["path"] != path:
            img = QImage(path)
            TEXT_IMG["img"] = None if img.isNull() else img
            TEXT_IMG["path"] = path
            TEXT_IMG["sig"] += 1
    elif TEXT_IMG["path"] is not None:
        TEXT_IMG["path"] = None
        TEXT_IMG["img"] = None
        TEXT_IMG["sig"] += 1


def cover_fit(src, w, h, blur):
    smooth = Qt.TransformationMode.SmoothTransformation
    ignore = Qt.AspectRatioMode.IgnoreAspectRatio
    sc = src.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
    sc = sc.copy((sc.width() - w) // 2, (sc.height() - h) // 2, w, h)
    if blur > 0:
        k = 1.0 - 0.97 * blur / 100.0
        sc = sc.scaled(max(2, int(w * k)), max(2, int(h * k)), ignore, smooth).scaled(w, h, ignore, smooth)
    return QPixmap.fromImage(sc)


class MenuPaint:
    def menu_init(self):
        self.mw_pm = None
        self.mw_sig = None
        self.mw_src = None
        self.mw_path = None

    def menu_wall(self, w, h):
        path = self.cfg["menu_image"]
        if not path or not os.path.isfile(path):
            if self.mw_src is not None:
                self.mw_src.stop()
                self.mw_src = None
                self.mw_path = None
                self.mw_sig = None
                self.mw_pm = None
            return None
        blur = int(self.cfg["menu_blur"])
        if self.mw_path != path:
            if self.mw_src is not None:
                self.mw_src.stop()
            self.mw_src = ImageSrc(path, self.update)
            self.mw_path = path
        sig = (path, w, h, blur, self.mw_src.number())
        if sig != self.mw_sig:
            self.mw_sig = sig
            self.mw_pm = None
            fr = self.mw_src.frame()
            if not fr.isNull():
                self.mw_pm = cover_fit(fr, w, h, blur)
        return self.mw_pm

    def paint_menu(self, p, rect, rad, pal):
        cfg = self.cfg
        path = QPainterPath()
        path.addRoundedRect(rect, rad, rad)
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, with_alpha(mix(pal.bg, pal.surface, 0.25), 244 if rad > 0 else 255))
        wall = self.menu_wall(max(2, int(rect.width())), max(2, int(rect.height())))
        if wall is not None:
            p.setOpacity(cfg["menu_image_opacity"] / 100.0)
            p.drawPixmap(rect.toRect(), wall)
            p.setOpacity(1.0)
            p.fillRect(rect, QColor(0, 0, 0, int(2.2 * cfg["menu_dim"])))
        if cfg["menu_anim"] and cfg["optimize"] != "performance":
            t = time.monotonic()
            span = max(rect.width(), rect.height()) * 0.55
            for k, col in enumerate((pal.accent, pal.secondary)):
                cx = rect.center().x() + math.sin(t * 0.3 + k * 2.6) * rect.width() * 0.38
                cy = rect.center().y() + math.cos(t * 0.23 + k * 1.9) * rect.height() * 0.34
                rg = QRadialGradient(cx, cy, span)
                rg.setColorAt(0, with_alpha(col, 30))
                rg.setColorAt(1, with_alpha(col, 0))
                p.fillRect(rect, QBrush(rg))
        p.restore()
        if rad > 0:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.5), 90), 1.0))
            p.drawPath(path)


class CardPaint:
    def card_init(self):
        self.bd_pm = None
        self.bd_sig = None
        self.img_pm = None
        self.img_sig = None
        self.img_src = None
        self.img_path = None
        self.img_key = "bg_image"

    def blur_card(self, card, s=1.0):
        if self.isVisible():
            set_blur(self, bool(self.cfg["blur"]) and self.cfg["glass"] < 100, card, self.cfg["card_radius"] * s)

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

    def image_backdrop(self, card):
        path = self.cfg[self.img_key]
        if not path or not os.path.isfile(path):
            if self.img_src is not None:
                self.img_src.stop()
                self.img_src = None
                self.img_path = None
                self.img_sig = None
                self.img_pm = None
            return None
        w = max(2, int(card.width()))
        h = max(2, int(card.height()))
        blur = int(self.cfg[self.img_key + "_blur"])
        if self.img_path != path:
            if self.img_src is not None:
                self.img_src.stop()
            self.img_src = ImageSrc(path, self.update)
            self.img_path = path
        sig = (path, w, h, blur, self.img_src.number())
        if sig != self.img_sig:
            self.img_sig = sig
            self.img_pm = None
            fr = self.img_src.frame()
            if not fr.isNull():
                self.img_pm = cover_fit(fr, w, h, blur)
        return self.img_pm

    def paint_card(self, p, card, pal):
        cfg = self.cfg
        rad = float(cfg["card_radius"])
        glass = cfg["glass"] / 100.0
        style = cfg["card_style"]
        ba = cfg["border_alpha"] / 100.0
        fr = cfg["frost"] / 100.0
        white = QColor(255, 255, 255)
        path = QPainterPath()
        path.addRoundedRect(card, rad, rad)
        sh = cfg["card_shadow"] / 100.0
        if sh > 0.01:
            outer = QPainterPath()
            outer.addRect(card.adjusted(-40, -40, 40, 40))
            p.save()
            p.setClipPath(outer.subtracted(path))
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(6, 0, -1):
                g = k * 1.8
                p.setBrush(QColor(0, 0, 0, int(clamp(sh * 22, 0, 255))))
                p.drawRoundedRect(card.adjusted(-g, -g + 4, g, g + 4), rad + g, rad + g)
            p.restore()
        if style == "flat":
            p.fillPath(path, with_alpha(pal.bg.lighter(110), int(255 * glass)))
        elif style == "frosted":
            base = mix(pal.bg, white, 0.2)
            g = QLinearGradient(card.topLeft(), card.bottomRight())
            g.setColorAt(0, with_alpha(mix(base, white, 0.3 * fr), int(205 * glass)))
            g.setColorAt(1, with_alpha(base, int(150 * glass)))
            p.fillPath(path, QBrush(g))
        elif style == "aurora":
            p.fillPath(path, with_alpha(pal.bg.darker(130), int(245 * glass)))
            t = time.monotonic()
            third = QColor.fromHsvF((max(0.0, pal.accent.hsvHueF()) + 0.33) % 1.0, 0.7, 1.0)
            span = max(card.width(), card.height()) * 0.6
            for k, col in enumerate((pal.accent, pal.secondary, third)):
                cx = card.center().x() + math.sin(t * 0.35 + k * 2.1) * card.width() * 0.35
                cy = card.center().y() + math.cos(t * 0.28 + k * 1.7) * card.height() * 0.3
                rg = QRadialGradient(cx, cy, span)
                rg.setColorAt(0, with_alpha(col, int(120 * glass)))
                rg.setColorAt(1, with_alpha(col, 0))
                p.fillPath(path, QBrush(rg))
        else:
            g = QLinearGradient(card.topLeft(), card.bottomRight())
            g.setColorAt(0, with_alpha(pal.bg.lighter(125), int(240 * glass)))
            g.setColorAt(1, with_alpha(pal.bg.darker(150), int(245 * glass)))
            p.fillPath(path, QBrush(g))
        bd = self.backdrop(card)
        if bd is not None and cfg["backdrop"] > 0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(p.opacity() * cfg["backdrop"] / 100.0)
            p.drawPixmap(card.toRect(), bd)
            p.restore()
        im = self.image_backdrop(card)
        if im is not None:
            p.save()
            p.setClipPath(path)
            p.setOpacity(p.opacity() * cfg[self.img_key + "_opacity"] / 100.0)
            p.drawPixmap(card.toRect(), im)
            p.restore()
        k = {"flat": 0.0, "frosted": 0.18, "aurora": 0.45}.get(style, 1.0)
        if im is not None:
            k *= 0.55
        if k > 0:
            shade = QLinearGradient(card.topLeft(), card.bottomLeft())
            shade.setColorAt(0, with_alpha(pal.bg, int(40 * k)))
            shade.setColorAt(0.55, with_alpha(pal.bg, int(150 * k)))
            shade.setColorAt(1, with_alpha(pal.bg.darker(160), int(215 * k)))
            p.fillPath(path, QBrush(shade))
        if style == "frosted" and fr > 0.01:
            p.save()
            p.setClipPath(path)
            top = QLinearGradient(card.topLeft(), QPointF(card.left(), card.top() + card.height() * 0.45))
            top.setColorAt(0, with_alpha(white, int(70 * fr)))
            top.setColorAt(1, with_alpha(white, 0))
            p.fillPath(path, QBrush(top))
            phase = (time.monotonic() * 0.07) % 1.8 - 0.4 if self.state.playing else 0.3
            sx = card.left() + card.width() * phase
            sheen = QLinearGradient(
                sx - card.width() * 0.2, card.top(), sx + card.width() * 0.2, card.top() + card.height() * 0.35
            )
            sheen.setColorAt(0.0, with_alpha(white, 0))
            sheen.setColorAt(0.5, with_alpha(white, int(34 * fr)))
            sheen.setColorAt(1.0, with_alpha(white, 0))
            p.fillPath(path, QBrush(sheen))
            p.setOpacity(p.opacity() * 0.07 * fr)
            p.fillPath(path, QBrush(grain()))
            p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        glow = cfg["card_glow"] / 100.0
        bw = float(cfg["border_width"])

        def al(v):
            return int(clamp(v * ba, 0, 255))

        if style == "frosted":
            edge = QLinearGradient(card.topLeft(), card.bottomRight())
            edge.setColorAt(0.0, with_alpha(white, al(200)))
            edge.setColorAt(0.5, with_alpha(white, al(55)))
            edge.setColorAt(1.0, with_alpha(white, al(110)))
            p.setPen(QPen(QBrush(edge), bw + 0.4))
            p.drawPath(path)
        if glow > 0.01:
            p.setPen(QPen(with_alpha(pal.accent, int(20 * glow)), 6))
            p.drawPath(path)
            ang = (time.monotonic() * 45.0) % 360.0 if self.state.playing else 40.0
            cg = QConicalGradient(card.center(), ang)
            cg.setColorAt(0.0, with_alpha(pal.accent, al(235 * glow)))
            cg.setColorAt(0.22, with_alpha(pal.secondary, al(215 * glow)))
            cg.setColorAt(0.5, with_alpha(pal.accent, al(30 * glow)))
            cg.setColorAt(0.78, with_alpha(pal.secondary, al(215 * glow)))
            cg.setColorAt(1.0, with_alpha(pal.accent, al(235 * glow)))
            p.setPen(QPen(QBrush(cg), bw + 0.6))
            p.drawPath(path)
        elif style != "frosted":
            p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.4), al(110)), bw))
            p.drawPath(path)
        p.setPen(QPen(with_alpha(white, int(clamp(28 * ba, 0, 255))), 1.0))
        p.drawRoundedRect(card.adjusted(1.5, 1.5, -1.5, -1.5), rad - 1.5, rad - 1.5)

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

    def __init__(self, accent, secondary, text=None, bg=None):
        self.accent = QColor(accent)
        self.secondary = QColor(secondary)
        h = self.accent.hsvHueF()
        if h < 0:
            h = 0.0
        if bg is not None:
            self.bg = QColor(bg)
            self.surface = mix(mix(self.bg, QColor(255, 255, 255), 0.07), self.accent, 0.1)
        else:
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


def apply_qss(widget, pal, family=None):
    q = build_qss(pal, family)
    if getattr(widget, "applied_qss", None) != q:
        widget.applied_qss = q
        widget.setStyleSheet(q)


def build_qss(pal, family=None):
    def rgba(c, a):
        return f"rgba({c.red()},{c.green()},{c.blue()},{a})"

    bg2 = mix(pal.bg, pal.surface, 0.45)
    line = mix(pal.surface, pal.accent, 0.22)
    rep = {
        "@BG@": pal.bg.name(),
        "@BG2@": bg2.name(),
        "@BG2A@": rgba(bg2, 190),
        "@SFA@": rgba(pal.surface, 215),
        "@SF@": pal.surface.name(),
        "@LINE@": line.name(),
        "@ACC@": pal.accent.name(),
        "@SEC@": pal.secondary.name(),
        "@TX@": pal.text.name(),
        "@DIM@": mix(pal.text, pal.bg, 0.42).name(),
        "@ACCA@": rgba(pal.accent, 60),
        "@ACCA2@": rgba(pal.accent, 90),
        "@FAM@": str(family or DEFAULT_FAMILY).replace('"', ""),
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
        app_id = ""
        try:
            app_id = str(session.source_app_user_model_id or "")
        except Exception:
            app_id = ""
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
            "app": app_id,
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
        self.meter = None
        self.available = False
        self.app = ""
        self.per_app = True
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
            try:
                from pycaw.pycaw import IAudioMeterInformation

                raw_dev = getattr(dev, "_dev", dev)
                mraw = raw_dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self.meter = cast(mraw, POINTER(IAudioMeterInformation))
            except Exception:
                self.meter = None
        except Exception:
            self.iface = None
            self.available = False

    def peak(self):
        if self.meter is None:
            return None
        try:
            return float(self.meter.GetPeakValue())
        except Exception:
            return None

    def targets(self):
        app = (self.app or "").lower()
        if not app or not self.per_app:
            return []
        keys = set()
        for part in app.split("!"):
            part = part.strip()
            if part.endswith(".exe"):
                part = part[:-4]
            if part:
                keys.add(part)
        out = []
        try:
            from pycaw.pycaw import AudioUtilities

            for sess in AudioUtilities.GetAllSessions():
                pr = getattr(sess, "Process", None)
                if pr is None:
                    continue
                try:
                    name = pr.name().lower()
                except Exception:
                    continue
                if name.endswith(".exe"):
                    name = name[:-4]
                if name and any(name == k or name in k or k in name for k in keys):
                    out.append(sess.SimpleAudioVolume)
        except Exception:
            return []
        return out

    def get(self):
        if not self.available:
            return None
        t = self.targets()
        if t:
            try:
                return max(float(x.GetMasterVolume()) for x in t), all(bool(x.GetMute()) for x in t)
            except Exception:
                pass
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
        t = self.targets()
        if t:
            try:
                for x in t:
                    x.SetMasterVolume(float(clamp(v, 0.0, 1.0)), None)
                    if v > 0:
                        x.SetMute(0, None)
                return
            except Exception:
                pass
        try:
            self.iface.SetMasterVolumeLevelScalar(float(clamp(v, 0.0, 1.0)), None)
            if v > 0:
                self.iface.SetMute(0, None)
        except Exception:
            self.connect()

    def set_mute(self, m):
        if not self.available:
            return
        t = self.targets()
        if t:
            try:
                for x in t:
                    x.SetMute(1 if m else 0, None)
                return
            except Exception:
                pass
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
        self.app = ""
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
            a, s = shape_colors(self.cover_pal.accent, self.cover_pal.secondary, self.cfg["adaptive_mode"])
            return Palette(a, s, None, None)
        bg = self.cfg["bg_color"] if self.cfg["custom_bg"] else None
        return Palette(self.cfg["accent"], self.cfg["secondary"], self.cfg["text"], bg)

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
        self.app = d.get("app", "") or ""
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
    timg = TEXT_IMG["img"]
    if timg is not None:
        tex = cover_fit(timg, max(1, int(w * dpr)), max(1, int(h * dpr)), 0)
        tex.setDevicePixelRatio(dpr)
        p.setBrush(QBrush(tex))
    elif fill2 is not None:
        g = QLinearGradient(float(pad), 0.0, float(max(pad + 1, w - pad)), 0.0)
        g.setColorAt(0.0, fill)
        g.setColorAt(1.0, fill2)
        p.setBrush(QBrush(g))
    else:
        p.setBrush(fill)
    p.drawPath(path)
    if scan:
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        c = QColor(0, 0, 0, scan[0])
        yy = 0
        while yy < h:
            p.fillRect(QRectF(0, yy, w, 1), c)
            yy += scan[1]
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
        TEXT_IMG["sig"],
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


class Hud(QWidget, CardPaint):
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
        self.card_init()
        self.applied_scale = self.scale
        self.last = time.monotonic()
        self.drag = None
        self.resize_from = None
        self.dirty = True
        self.ct_applied = None
        self.lock_timer = QTimer(self)
        self.lock_timer.setInterval(6)
        self.lock_timer.setTimerType(Qt.TimerType.PreciseTimer)
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
        self.apply_size_limits(True)
        self.restore_pos()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
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

    @property
    def scale(self):
        return clamp(self.cfg["hud_scale"] / 100.0, 0.6, 1.8)

    def lp(self, pos):
        s = self.scale
        return QPointF(pos.x() / s, pos.y() / s)

    def apply_blur(self):
        s = self.scale
        m = self.MARGIN * s
        self.blur_card(QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m), s)

    def apply_size_limits(self, snap):
        s = self.scale
        mw = int(440 * s)
        if self.compact:
            ch = int(self.COMPACT_H * s)
            self.setMinimumSize(mw, ch)
            self.setMaximumSize(16777215, ch)
            if snap:
                self.resize(self.width(), ch)
        else:
            mh = int(400 * s)
            self.setMaximumSize(16777215, 16777215)
            self.setMinimumSize(mw, mh)
            if snap:
                self.resize(self.width(), max(mh, int(self.cfg["hud_h"])))

    def apply_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        self.top_applied = bool(self.cfg["always_on_top"])
        if self.top_applied:
            flags |= Qt.WindowType.WindowStaysOnTopHint
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
        self.timer.setInterval(int(1000 / eff_fps(self.cfg)))

    def refresh(self):
        if self.top_applied != bool(self.cfg["always_on_top"]):
            self.apply_flags()
        self.cache.clear()
        self.cover_sig = None
        self.bd_sig = None
        self.img_sig = None
        compact = self.cfg["mode"] == "both"
        mode_changed = compact != self.compact
        self.compact = compact
        s = self.scale
        k = s / self.applied_scale
        self.applied_scale = s
        self.apply_size_limits(False)
        if abs(k - 1.0) > 1e-6:
            self.resize(int(self.width() * k), int(self.height() * k))
        if mode_changed:
            self.apply_size_limits(True)
        self.apply_blur()
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
        self.apply_blur()

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
        if self.isVisible():
            self.apply_blur()
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
                want = self.hit_at(self.lp(QPointF(self.mapFromGlobal(QCursor.pos())))) is None
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
        s = self.scale
        return not self.cfg["click_through"] and pos.x() > self.width() / s - 30 and pos.y() > self.height() / s - 30

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
        pos = self.lp(e.position())
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
        pos = self.lp(e.position())
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
        pos = self.lp(e.position())
        if self.seeking:
            self.seeking = False
            self.state.seek(self.seek_frac * self.state.dur)
        if self.vol_drag:
            self.vol_drag = False
        if self.pressed is not None:
            r = self.rects.get(self.pressed)
            if r is not None and r.adjusted(-8, -8, 8, 8).contains(pos):
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
        sign = 1 if (e.angleDelta().y() or e.angleDelta().x()) > 0 else -1
        mod = e.modifiers()
        if mod & Qt.KeyboardModifier.ControlModifier:
            self.ctl.bump("hud_scale", 5 * sign, 60, 180)
        elif mod & Qt.KeyboardModifier.ShiftModifier:
            self.ctl.bump("opacity", 5 * sign, 30, 100)
        else:
            self.ctl.change_volume(0.03 * sign)
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
            ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, 0, time.monotonic(), i)
            tr = QTransform()
            tr.translate(area.center().x() + ox, area.center().y() + oy)
            tr.rotate(rx, Qt.Axis.XAxis)
            tr.rotate(rz)
            tr.scale(sc * sx, sc)
            p.save()
            p.setTransform(tr, True)
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
        s = self.scale
        dpr = self.devicePixelRatioF() * s
        pal = st.palette
        now = time.monotonic()
        ui = bool(cfg["ui_anim"])
        uf = cfg["ui_font"] / 100.0
        ap = ease(self.appear)
        op = cfg["opacity"] / 100.0
        m = self.MARGIN
        card = QRectF(m, m, self.width() / s - 2 * m, self.height() / s - 2 * m)
        self.hits = []
        p.scale(s, s)
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
        ft = th.font(21 * uf, QFont.Weight.Bold)
        fm = QFontMetrics(ft)
        p.setFont(ft)
        p.setPen(with_alpha(pal.text, int(255 * ta)))
        p.drawText(
            QPointF(tx + (1.0 - ta) * 18.0, cy + fm.ascent()),
            fm.elidedText(title, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 2
        fa = th.font(15 * uf, QFont.Weight.Medium)
        fm = QFontMetrics(fa)
        p.setFont(fa)
        p.setPen(with_alpha(pal.text, int(215 * ta2)))
        p.drawText(
            QPointF(tx + (1.0 - ta2) * 18.0, cy + fm.ascent()),
            fm.elidedText(artist, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 1
        if album and cfg["show_album"]:
            fb = th.font(12 * uf, QFont.Weight.Normal)
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
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.set_fps()
        self.state.track_changed.connect(self.on_track)
        self.state.lyrics_changed.connect(self.on_track)

    def on_track(self):
        RAND_SALT[0] = random.randrange(1 << 30)
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

    def set_fps(self):
        self.timer.setInterval(int(1000 / eff_fps(self.cfg)))

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
        m = hud.MARGIN * hud.scale
        gap = float(self.cfg["card_gap"])
        r = QRectF(
            hud.x() + m - self.org.x(),
            hud.y() + m - self.org.y(),
            hud.width() - 2 * m,
            hud.height() - 2 * m,
        )
        return r.adjusted(-gap, -gap, gap, gap)

    def block_rects(self):
        if self.wall or self.cfg["lyrics_over_ui"]:
            return []
        rects = []
        card = self.card_rect()
        if card is not None:
            rects.append(card)
        clock = self.ctl.clock
        if clock.isVisible():
            gap = float(self.cfg["card_gap"])
            rects.append(
                QRectF(
                    clock.x() - self.org.x(),
                    clock.y() - self.org.y(),
                    clock.width(),
                    clock.height(),
                ).adjusted(-gap, -gap, gap, gap)
            )
        return rects

    def fit_all(self, rects, left, topy, bw, bh, side, mo, ghost_pad, W, H):
        if not rects:
            return left, topy
        for _ in range(len(rects) * 2 + 1):
            moved = False
            for r in rects:
                res = self.fit(left, topy, bw, bh, side, mo, ghost_pad, r, W, H)
                if res is None:
                    return None
                if res != (left, topy):
                    left, topy = res
                    moved = True
            if not moved:
                return left, topy
        return None

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
        self.paint_toast(p, W, H, pal)
        lines = st.active_lines()
        if not lines:
            return
        ly = st.lyrics
        base_px = cfg["font_size"] * 1.6 * cfg["holo_scale"] / 100.0
        glow = cfg["glow"] / 100.0
        scan = (int(cfg["scan_strength"] * 2.55), int(cfg["scan_gap"])) if cfg["scanlines"] else False
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
        ga = cfg["glitch_amount"] / 100.0
        fl = cfg["flicker"] / 100.0
        ghost_pad = 3.0 + 31.0 * ga if glitch_on else 3.0
        rects = self.block_rects()
        card = rects[0] if rects else None
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
                placed = self.fit_all(rects, left, topy, bw, bh, side, mo, ghost_pad, W, H)
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
            ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, side, t, i)
            base_tilt = (14.0 if side < 0 else (-14.0 if side > 0 else 0.0)) if tilt_on else 0.0
            rot = base_tilt * (1.6 - 0.6 * enter)
            tr = QTransform()
            tr.translate(left + bw / 2.0 + ox, topy + bh / 2.0 + oy)
            tr.rotate(rot, Qt.Axis.YAxis)
            tr.rotate(rx, Qt.Axis.XAxis)
            tr.rotate(rz)
            tr.scale(sc * sx, sc)
            p.setTransform(tr)
            gx = 3.0
            flick = 1.0 - fl * 0.05 * (1.0 - math.sin(t * 37.0))
            if glitch_on:
                gx += 16.0 * ga * (1.0 - enter)
                if glitching:
                    gx += random.uniform(6, 14) * ga
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


class Welcome(QWidget, CardPaint):
    SPAN = 5.2
    H = 190

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.t0 = 0.0
        self.first = False
        self.below = False
        self.name, self.pc = desktop_names()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def anchor(self):
        hud = self.ctl.hud
        screen = QGuiApplication.primaryScreen()
        if hud.isVisible():
            m = hud.MARGIN * hud.scale
            gx = hud.x() + m
            gy = hud.y() + m
            gw = hud.width() - 2 * m
            gh = hud.height() - 2 * m
            screen = QGuiApplication.screenAt(hud.frameGeometry().center()) or screen
            g = screen.availableGeometry()
            y = int(gy) - 8 - self.H + 14
            self.below = y < g.top()
            if self.below:
                y = int(gy + gh) + 8 - 14
            return QRect(int(gx) - 14, y, int(gw) + 28, self.H)
        g = screen.availableGeometry()
        self.below = False
        return QRect(g.x() + (g.width() - 560) // 2, g.y() + int(g.height() * 0.16), 560, self.H)

    def place(self):
        geo = self.anchor()
        if geo != self.geometry():
            self.setGeometry(geo)
            self.blur_card(QRectF(14, 14, geo.width() - 28, geo.height() - 28))

    def play(self, first):
        self.first = first
        self.t0 = time.monotonic()
        self.setGeometry(self.anchor())
        self.show()
        self.blur_card(QRectF(14, 14, self.width() - 28, self.height() - 28))
        self.timer.start()

    def tick(self):
        if time.monotonic() - self.t0 >= self.SPAN:
            self.timer.stop()
            self.hide()
            return
        self.place()
        self.update()

    def paintEvent(self, e):
        age = time.monotonic() - self.t0
        out = ease(clamp((age - (self.SPAN - 0.9)) / 0.9, 0.0, 1.0))
        a_in = ease(age / 0.7)
        a = a_in * (1.0 - out)
        if a <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHints(AA)
        th = self.theme
        pal = self.state.pal_target
        white = QColor(255, 255, 255)
        card = QRectF(14, 14, self.width() - 28, self.height() - 28)
        d = -1.0 if self.below else 1.0
        p.translate(0.0, d * ((1.0 - a_in) * 18.0 - out * 10.0))
        p.setOpacity(a)
        self.paint_card(p, card, pal)
        rad = float(self.cfg["card_radius"])
        clip = QPainterPath()
        clip.addRoundedRect(card, rad, rad)
        p.save()
        p.setClipPath(clip)
        if 0.35 < age < 1.85:
            sx = card.left() - 120.0 + (card.width() + 240.0) * ease((age - 0.35) / 1.5)
            sg = QLinearGradient(sx - 90.0, card.top(), sx + 90.0, card.top() + 40.0)
            sg.setColorAt(0.0, with_alpha(white, 0))
            sg.setColorAt(0.5, with_alpha(white, 38))
            sg.setColorAt(1.0, with_alpha(white, 0))
            p.fillPath(clip, QBrush(sg))
        bar = QRectF(card.left() + 24.0, card.bottom() - 14.0, card.width() - 48.0, 2.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(pal.text, 40))
        p.drawRoundedRect(bar, 1.0, 1.0)
        left = bar.width() * clamp(1.0 - age / self.SPAN, 0.0, 1.0)
        bg = QLinearGradient(bar.left(), 0.0, bar.right(), 0.0)
        bg.setColorAt(0, pal.accent)
        bg.setColorAt(1, pal.secondary)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), left, bar.height()), 1.0, 1.0)
        p.restore()
        ac = QRectF(card.left() + 30.0, card.center().y() - 34.0, 68.0, 68.0)
        pop = ease_back(age / 0.8)
        p.save()
        p.translate(ac.center())
        p.scale(pop, pop)
        p.translate(-ac.center().x(), -ac.center().y())
        cg = QConicalGradient(ac.center(), (age * 110.0) % 360.0)
        cg.setColorAt(0.0, pal.accent)
        cg.setColorAt(0.5, pal.secondary)
        cg.setColorAt(1.0, pal.accent)
        p.setPen(QPen(QBrush(cg), 3.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ac)
        inner = ac.adjusted(7, 7, -7, -7)
        fg = QLinearGradient(inner.topLeft(), inner.bottomRight())
        fg.setColorAt(0, pal.accent)
        fg.setColorAt(1, pal.secondary)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fg))
        p.drawEllipse(inner)
        p.setFont(th.font(28, QFont.Weight.Bold))
        p.setPen(pal.bg)
        p.drawText(inner, Qt.AlignmentFlag.AlignCenter, (self.name[:1] or "?").upper())
        p.restore()
        x0 = ac.right() + 24.0
        tw = card.right() - 26.0 - x0
        left_mid = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        y = card.center().y() - 52.0

        def rv(delay):
            return ease((age - delay) / 0.5)

        f = th.font(12, QFont.Weight.DemiBold, 5.0)
        fm = QFontMetrics(f)
        r = rv(0.2)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(pal.accent)
        p.drawText(QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()), left_mid, "WELCOME" if self.first else "WELCOME BACK")
        y += fm.height() + 4.0
        f = th.font(34, QFont.Weight.Bold)
        fm = QFontMetrics(f)
        r = rv(0.35)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(pal.text)
        p.drawText(
            QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()),
            left_mid,
            fm.elidedText(self.name, Qt.TextElideMode.ElideRight, int(tw)),
        )
        y += fm.height() + 5.0
        lw = min(tw, 150.0) * ease((age - 0.5) / 0.8)
        lg = QLinearGradient(x0, 0.0, x0 + lw + 1.0, 0.0)
        lg.setColorAt(0, pal.accent)
        lg.setColorAt(1, pal.secondary)
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(lg))
        p.drawRoundedRect(QRectF(x0, y, lw, 3.0), 1.5, 1.5)
        y += 13.0
        f = th.font(13, QFont.Weight.Medium)
        fm = QFontMetrics(f)
        r = rv(0.65)
        hour = datetime.now().hour
        greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
        info = "  \u00b7  ".join(x for x in (greet, self.pc, datetime.now().strftime("%A, %d %B")) if x)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 175))
        p.drawText(
            QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()),
            left_mid,
            fm.elidedText(info, Qt.TextElideMode.ElideRight, int(tw)),
        )

class Clock(QWidget, CardPaint):
    MARGIN = 10

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.img_key = "clock_bg_image"
        self.sig = None
        self.dirty = True
        self.drag = None
        self.sc = 1.0
        self.apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.fit()
        self.restore_pos()

    def parts(self):
        c = self.cfg
        now = datetime.now()
        if c["clock_24h"]:
            main = now.strftime("%H:%M")
            suffix = ""
        else:
            main = now.strftime("%I:%M").lstrip("0")
            suffix = now.strftime(" %p")
        secs = now.strftime(":%S") if c["clock_seconds"] else ""
        date = now.strftime("%A, %d %B %Y") if c["clock_date"] else ""
        return main, secs, suffix, date

    def fonts(self):
        s = self.sc
        th = self.theme
        return (
            th.font(40 * s, QFont.Weight.DemiBold),
            th.font(20 * s, QFont.Weight.Medium),
            th.font(13 * s, QFont.Weight.Medium, 0.6),
        )

    def fit(self):
        self.sc = self.cfg["clock_scale"] / 100.0
        main, secs, suffix, date = self.parts()
        fm, fs, fd = (QFontMetrics(f) for f in self.fonts())
        tw = (
            fm.horizontalAdvance("00:00")
            + (fs.horizontalAdvance(":00") if secs else 0)
            + (fs.horizontalAdvance(" AM") if suffix else 0)
        )
        dw = fd.horizontalAdvance(date) if date else 0
        w = int(max(tw, dw) + 2 * (self.MARGIN + 18 * self.sc))
        h = int(fm.height() + (fd.height() + 4 * self.sc if date else 0) + 2 * (self.MARGIN + 12 * self.sc))
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)

    def apply_blur(self):
        m = self.MARGIN
        self.blur_card(QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m))

    def apply_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        self.top_applied = bool(self.cfg["always_on_top"])
        if self.top_applied:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was = self.isVisible()
        self.setWindowFlags(flags)
        if was:
            self.show()

    def refresh(self):
        if self.top_applied != bool(self.cfg["always_on_top"]):
            self.apply_flags()
        self.bd_sig = None
        self.img_sig = None
        self.fit()
        self.apply_blur()
        self.dirty = True
        self.update()

    def tick(self):
        parts = self.parts()
        if self.sig is None or parts[2:] != self.sig[2:]:
            self.fit()
        if parts != self.sig or self.dirty:
            self.sig = parts
            self.dirty = False
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start()
        self.tick()
        self.apply_blur()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_blur()

    def save_pos(self):
        self.cfg["clock_x"] = self.x()
        self.cfg["clock_y"] = self.y()
        self.cfg.save()

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.top() + 24)
        self.save_pos()

    def restore_pos(self):
        x, y = self.cfg["clock_x"], self.cfg["clock_y"]
        if x is not None and y is not None and any(
            s.geometry().contains(QPoint(int(x) + 20, int(y) + 20)) for s in QGuiApplication.screens()
        ):
            self.move(int(x), int(y))
        else:
            self.reset_pos()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self.ctl.menu.exec(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.drag = None
            self.save_pos()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setOpacity(self.cfg["clock_opacity"] / 100.0)
        self.paint_card(p, card, pal)
        main, secs, suffix, date = self.parts()
        fmain, fsmall, fdate = self.fonts()
        fm = QFontMetrics(fmain)
        fs = QFontMetrics(fsmall)
        wm = fm.horizontalAdvance(main)
        ws = fs.horizontalAdvance(secs)
        wx = fs.horizontalAdvance(suffix)
        x = card.center().x() - (wm + ws + wx) / 2.0
        y = card.top() + 12 * self.sc + fm.ascent()
        p.setFont(fmain)
        p.setPen(pal.text)
        p.drawText(QPointF(x, y), main)
        p.setFont(fsmall)
        p.setPen(pal.accent)
        p.drawText(QPointF(x + wm, y), secs)
        p.setPen(with_alpha(pal.text, 170))
        p.drawText(QPointF(x + wm + ws, y), suffix)
        if date:
            fd = QFontMetrics(fdate)
            p.setFont(fdate)
            p.setPen(with_alpha(pal.text, 150))
            p.drawText(
                QRectF(card.left(), y + fm.descent() + 4 * self.sc, card.width(), fd.height()),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                date,
            )


SECTION_OPEN = {}


class SecHead(QPushButton):
    def __init__(self, state, text):
        super().__init__(text.upper())
        self.state = state
        self.setObjectName("sechead")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        col = pal.accent if self.isChecked() else mix(pal.text, pal.bg, 0.45)
        p.setPen(QPen(col, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cx = self.width() - 12.0
        cy = self.height() / 2.0 + 2.0
        if self.isChecked():
            p.drawPolyline(QPolygonF([QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2)]))
        else:
            p.drawPolyline(QPolygonF([QPointF(cx - 2, cy - 4), QPointF(cx + 2, cy), QPointF(cx - 2, cy + 4)]))
        p.end()


class PageLay:
    def __init__(self, panel, root):
        self.panel = panel
        self.root = root
        self.cur = None
        self.count = 0

    def begin(self, text):
        head = SecHead(self.panel.state, text)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 4, 0, 10)
        bl.setSpacing(2)
        key = text
        want = SECTION_OPEN.get(key, self.count == 0)
        self.count += 1
        head.setChecked(want)
        body.setVisible(want)

        def toggled(v):
            SECTION_OPEN[key] = bool(v)
            body.setVisible(bool(v))

        head.toggled.connect(toggled)
        self.root.addWidget(head)
        self.root.addWidget(body)
        self.cur = bl

    def addWidget(self, *a, **k):
        (self.cur if self.cur is not None else self.root).addWidget(*a, **k)

    def addLayout(self, *a, **k):
        (self.cur if self.cur is not None else self.root).addLayout(*a, **k)

    def addSpacing(self, n):
        (self.cur if self.cur is not None else self.root).addSpacing(n)

    def addStretch(self, n=0):
        self.root.addStretch(n)


class Switch(QCheckBox):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.k = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 24)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.valueChanged.connect(self.set_k)
        self.toggled.connect(self.on_toggle)

    def set_k(self, v):
        self.k = float(v)
        self.update()

    def on_toggle(self, on):
        target = 1.0 if on else 0.0
        self.anim.stop()
        if self.isVisible() and self.state.cfg["menu_anim"]:
            self.anim.setStartValue(self.k)
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            self.set_k(target)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        k = clamp(self.k, 0.0, 1.0)
        enabled = self.isEnabled()
        track = mix(mix(pal.surface, pal.text, 0.2), pal.accent, k)
        if not enabled:
            track.setAlpha(80)
        r = QRectF(1, 3, 40, 18)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, track)
        g.setColorAt(1, mix(track, pal.secondary, 0.55 * k))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 9, 9)
        kx = 10.0 + 22.0 * self.k
        if k > 0.01 and enabled:
            p.setBrush(with_alpha(pal.accent, int(70 * k)))
            p.drawEllipse(QPointF(kx, 12), 10.0, 10.0)
        p.setBrush(mix(pal.text, pal.bg, k) if enabled else pal.text)
        p.drawEllipse(QPointF(kx, 12), 7.0, 7.0)


class NavList(QListWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.sel_y = 0.0
        self.hover_row = -1
        self.hv = {}
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.step)

    def showEvent(self, e):
        it = self.currentItem()
        if it is not None:
            self.sel_y = float(self.visualItemRect(it).y())
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def mouseMoveEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        self.hover_row = self.row(it) if it is not None else -1
        super().mouseMoveEvent(e)

    def viewportEvent(self, e):
        if e.type() == QEvent.Type.Leave:
            self.hover_row = -1
        return super().viewportEvent(e)

    def step(self):
        changed = False
        it = self.currentItem()
        if it is not None:
            ty = float(self.visualItemRect(it).y())
            d = ty - self.sel_y
            if abs(d) > 0.3:
                self.sel_y += d * 0.28
                changed = True
            elif d:
                self.sel_y = ty
                changed = True
        for r in range(self.count()):
            target = 1.0 if r == self.hover_row else 0.0
            cur = self.hv.get(r, 0.0)
            if abs(target - cur) > 0.01:
                self.hv[r] = cur + (target - cur) * 0.25
                changed = True
            elif cur != target:
                self.hv[r] = target
                changed = True
        if changed:
            self.viewport().update()

    def paintEvent(self, e):
        if self.count():
            pal = self.state.pal_target
            p = QPainter(self.viewport())
            p.setRenderHints(AA)
            p.setPen(Qt.PenStyle.NoPen)
            w = float(self.viewport().width())
            for r, v in self.hv.items():
                if v > 0.01 and r != self.currentRow():
                    rect = QRectF(self.visualItemRect(self.item(r)))
                    p.setBrush(with_alpha(pal.text, int(24 * v)))
                    p.drawRoundedRect(QRectF(4, rect.top() + 2, w - 8, rect.height() - 4), 9, 9)
            if self.currentItem() is not None:
                h = float(self.visualItemRect(self.item(0)).height())
                rect = QRectF(4, self.sel_y + 2, w - 8, h - 4)
                g = QLinearGradient(rect.topLeft(), rect.topRight())
                g.setColorAt(0, with_alpha(pal.accent, 105))
                g.setColorAt(1, with_alpha(pal.secondary, 22))
                p.setBrush(QBrush(g))
                p.drawRoundedRect(rect, 9, 9)
                p.setBrush(pal.accent)
                p.drawRoundedRect(QRectF(rect.left() + 5, rect.top() + rect.height() * 0.25, 3.0, rect.height() * 0.5), 1.5, 1.5)
            p.end()
        super().paintEvent(e)


class GlassMenu(QMenu, MenuPaint):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.cfg = ctl.cfg
        self.state = ctl.state
        self.menu_init()
        self.setObjectName("glass")
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.setDuration(180)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, e):
        if self.cfg["menu_anim"]:
            self.fade.stop()
            self.fade.start()
        else:
            self.setWindowOpacity(1.0)
        super().showEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        self.paint_menu(p, QRectF(self.rect()).adjusted(1, 1, -1, -1), 12.0, self.state.pal_target)
        p.end()
        super().paintEvent(e)

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


class Preview(QWidget, CardPaint):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.cache = LineCache(32)
        self.thumb = None
        self.thumb_sig = None
        self.setFixedHeight(108)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)

    def refresh(self):
        self.cache.clear()
        self.thumb_sig = None
        self.bd_sig = None
        self.img_sig = None
        self.update()

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        cfg = self.cfg
        st = self.state
        pal = st.pal_target
        W = float(self.width())
        H = float(self.height())
        now = time.monotonic()
        dpr = self.devicePixelRatioF()
        wall = QLinearGradient(0.0, 0.0, W, H)
        wall.setColorAt(0, mix(pal.bg, pal.accent, 0.35))
        wall.setColorAt(1, mix(pal.bg, pal.secondary, 0.35))
        p.fillRect(QRectF(0, 0, W, H), QBrush(wall))
        card = QRectF(14, 12, W - 28, H - 24)
        op = cfg["opacity"] / 100.0
        p.setOpacity(op)
        self.paint_card(p, card, pal)
        cs = 64.0
        sig = (st.cover_id, pal.accent.rgba(), st.cover is None)
        if sig != self.thumb_sig:
            self.thumb = cover_thumb(st, 64)
            self.thumb_sig = sig
        cr = QRectF(card.left() + 16, card.center().y() - cs / 2.0, cs, cs)
        p.drawPixmap(cr.topLeft(), self.thumb)
        x0 = cr.right() + 16.0
        x1 = card.right() - 16.0
        th = self.theme
        f = th.font(15, QFont.Weight.Bold)
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(pal.text)
        title = st.title if st.active else "Song title"
        p.drawText(
            QPointF(x0, card.top() + 14 + fm.ascent()),
            fm.elidedText(title, Qt.TextElideMode.ElideRight, int(x1 - x0)),
        )
        f = th.font(12, QFont.Weight.Medium)
        fm2 = QFontMetrics(f)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 170))
        artist = st.artist if st.active else "Artist name"
        p.drawText(
            QPointF(x0, card.top() + 14 + fm.height() + fm2.ascent()),
            fm2.elidedText(artist, Qt.TextElideMode.ElideRight, int(x1 - x0)),
        )
        phase = now % 3.8
        enter = ease(phase / 0.6)
        eo = clamp((phase - 3.1) / 0.7, 0.0, 1.0)
        alpha = enter * (1.0 - ease(eo))
        prog = clamp((phase - 0.35) / 2.4, 0.0, 1.0)
        size = clamp(cfg["font_size"] * 0.75, 14.0, 30.0)
        fill, fill2, gcol = lyric_colors(cfg, pal)
        sty = lyric_style(cfg)
        glow = cfg["glow"] / 100.0 * 0.6
        karaoke = bool(cfg["karaoke"])
        text = "Feel the rhythm tonight"
        maxw = x1 - x0
        bright = cached_line(self.cache, th, text, size, fill, gcol, glow, maxw, dpr, False, "c", sty, fill2)
        dim = (
            cached_line(self.cache, th, text, size, fill, gcol, 0.0, maxw, dpr, False, "c", sty, fill2)
            if karaoke
            else None
        )
        ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, 0, now, 0)
        tr = QTransform()
        tr.translate((x0 + x1) / 2.0 + ox * 0.6, card.bottom() - 30.0 + oy * 0.6)
        tr.rotate(rx, Qt.Axis.XAxis)
        tr.rotate(rz)
        tr.scale(sc * sx, sc)
        p.save()
        p.setTransform(tr, True)
        draw_karaoke(p, dim, bright, prog, alpha * op * cfg["lyric_opacity"] / 100.0, karaoke, 1.0, cfg["dim_level"] / 100.0)
        p.restore()


class Panel(QDialog, MenuPaint):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.state = ctl.state
        self.switches = []
        self.manual = []
        self.menu_init()
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(40)
        self.anim_timer.timeout.connect(self.tick_anim)

    def tick_anim(self):
        if self.cfg["menu_anim"]:
            self.update()

    def fade_in(self):
        if not self.cfg["menu_anim"]:
            return
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(300)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def showEvent(self, e):
        dark_titlebar(self, self.state.pal_target)
        self.anim_timer.start()
        self.fade_in()
        super().showEvent(e)

    def hideEvent(self, e):
        self.anim_timer.stop()
        super().hideEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        self.paint_menu(p, QRectF(self.rect()), 0.0, self.state.pal_target)

    def sec(self, lay, text):
        if isinstance(lay, PageLay):
            lay.begin(text)
            return
        l = QLabel(text.upper())
        l.setObjectName("section")
        lay.addWidget(l)

    def row(self, lay, label, widget, hint=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 3, 0, 3)
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


class TitleBar(QWidget):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.cfg = panel.cfg
        self.page = ""
        self.hover = None
        self.pressed = None
        self.levels = [0.05] * 40
        self.t0 = time.monotonic()
        self.setMouseTracking(True)
        self.setFixedHeight(int(self.cfg["bar_height"]))
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)

    def sync(self):
        h = int(self.cfg["bar_height"])
        if self.height() != h:
            self.setFixedHeight(h)
        self.update()

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def tick(self):
        if not self.cfg["bar_eq"]:
            return
        st = self.panel.state
        now = time.monotonic() - self.t0
        base = 0.0
        if st.playing:
            pk = self.panel.ctl.volume.peak()
            base = min(1.0, pk * 2.2) if pk is not None else 0.7
        for i in range(40):
            wob = 0.5 + 0.5 * math.sin(now * (2.1 + i * 0.13) + i * 0.9) * math.sin(now * 1.7 + i * 0.37)
            target = 0.06 + 0.94 * base * (0.25 + 0.75 * abs(wob)) if st.playing else 0.05
            self.levels[i] += (target - self.levels[i]) * 0.35
        self.update()

    def set_page(self, name):
        self.page = name
        self.update()

    def btn_rects(self):
        w = float(self.width())
        h = float(self.height())
        y = (h - 28) / 2.0
        if self.cfg["bar_btn_pos"] == "left":
            return {"close": QRectF(10, y, 34, 28), "min": QRectF(48, y, 34, 28)}
        return {"close": QRectF(w - 44, y, 34, 28), "min": QRectF(w - 82, y, 34, 28)}

    def hit(self, pos):
        for name, r in self.btn_rects().items():
            if r.contains(QPointF(pos)):
                return name
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        name = self.hit(e.position())
        if name:
            self.pressed = name
            return
        wh = self.window().windowHandle()
        if wh is not None:
            wh.startSystemMove()

    def mouseMoveEvent(self, e):
        name = self.hit(e.position())
        if name != self.hover:
            self.hover = name
            self.setCursor(Qt.CursorShape.PointingHandCursor if name else Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e):
        name = self.pressed
        self.pressed = None
        if name and self.hit(e.position()) == name:
            if name == "close":
                self.window().close()
            else:
                self.window().showMinimized()

    def leaveEvent(self, e):
        if self.hover is not None:
            self.hover = None
            self.update()
        super().leaveEvent(e)

    def paint_eq(self, p, pal, x0, x1, h):
        n = int(clamp(int(self.cfg["bar_eq_bars"]), 6, 40))
        width = x1 - x0
        if width < 50:
            return
        mode = self.cfg["bar_eq_color"]
        if mode == "accent":
            brush = QBrush(pal.accent)
        elif mode == "text":
            brush = QBrush(mix(pal.text, pal.bg, 0.35))
        else:
            g = QLinearGradient(x0, 0, x1, 0)
            g.setColorAt(0, pal.accent)
            g.setColorAt(1, pal.secondary)
            brush = QBrush(g)
        cy = h / 2.0
        amp = h * 0.34
        step = width / n
        if self.cfg["bar_eq_style"] == "wave":
            top = QPainterPath()
            pts = [QPointF(x0 + step * (i + 0.5), cy - max(0.04, self.levels[i]) * amp) for i in range(n)]
            top.moveTo(pts[0])
            for k in range(1, n):
                mid = QPointF((pts[k - 1].x() + pts[k].x()) / 2.0, (pts[k - 1].y() + pts[k].y()) / 2.0)
                top.quadTo(pts[k - 1], mid)
            top.lineTo(pts[-1])
            for k in range(n - 1, -1, -1):
                top.lineTo(QPointF(pts[k].x(), 2 * cy - pts[k].y()))
            top.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(brush)
            p.setOpacity(0.55)
            p.drawPath(top)
            p.setOpacity(1.0)
            return
        bw = max(2.0, step * 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        for i in range(n):
            bh = max(3.0, self.levels[i] * amp * 2.0)
            p.drawRoundedRect(QRectF(x0 + step * i + (step - bw) / 2.0, cy - bh / 2.0, bw, bh), bw / 2.0, bw / 2.0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.panel.state.pal_target
        th = self.panel.ctl.theme
        cfg = self.cfg
        w = float(self.width())
        h = float(self.height())
        bottom = cfg["bar_pos"] == "bottom"
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0, with_alpha(pal.accent, 46))
        g.setColorAt(0.55, with_alpha(pal.secondary, 14))
        g.setColorAt(1, with_alpha(pal.bg, 0))
        p.fillRect(QRectF(0, 0, w, h), QBrush(g))
        lg = QLinearGradient(0, 0, w, 0)
        lg.setColorAt(0, with_alpha(pal.accent, 200))
        lg.setColorAt(1, with_alpha(pal.secondary, 20))
        p.setPen(QPen(QBrush(lg), 1.0))
        ly = 0.5 if bottom else h - 0.5
        p.drawLine(QPointF(0, ly), QPointF(w, ly))
        btn_left = cfg["bar_btn_pos"] == "left"
        left_edge = 92.0 if btn_left else 16.0
        right_edge = w - 16.0 if btn_left else w - 92.0
        f = th.font(14, QFont.Weight.Bold, 1.5)
        f2 = th.font(13, QFont.Weight.Medium)
        fm = QFontMetrics(f)
        fm2 = QFontMetrics(f2)
        brand = "LYRICS HUD"
        show_brand = bool(cfg["bar_brand"])
        show_page = bool(cfg["bar_page"]) and bool(self.page)
        gw = 24.0
        if show_brand:
            gw += 10.0 + fm.horizontalAdvance(brand)
        pillw = 0.0
        if show_page:
            pillw = fm2.horizontalAdvance(self.page) + 20.0
            gw += 12.0 + fm2.horizontalAdvance("/") + 10.0 + pillw - 10.0
        if cfg["bar_align"] == "center":
            gx = left_edge + max(0.0, (right_edge - left_edge - gw) / 2.0)
        else:
            gx = left_edge
        logo = QRectF(gx, (h - 24) / 2.0, 24, 24)
        lgg = QLinearGradient(logo.topLeft(), logo.bottomRight())
        lgg.setColorAt(0, pal.accent)
        lgg.setColorAt(1, pal.secondary)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(lgg))
        p.drawRoundedRect(logo, 8, 8)
        p.setBrush(pal.bg)
        for k, bh in enumerate((7.0, 13.0, 9.0)):
            p.drawRoundedRect(QRectF(logo.left() + 6.5 + k * 4.5, logo.center().y() - bh / 2.0, 2.4, bh), 1.2, 1.2)
        x = gx + 34.0
        if show_brand:
            p.setFont(f)
            p.setPen(pal.text)
            p.drawText(QPointF(x, h / 2.0 + (fm.ascent() - fm.descent()) / 2.0), brand)
            x += fm.horizontalAdvance(brand) + 12.0
        if show_page:
            p.setFont(f2)
            by = h / 2.0 + (fm2.ascent() - fm2.descent()) / 2.0
            if show_brand:
                p.setPen(mix(pal.text, pal.bg, 0.55))
                p.drawText(QPointF(x, by), "/")
                x += fm2.horizontalAdvance("/") + 10.0
            pill = QRectF(x - 10, h / 2.0 - 12, pillw, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(pal.accent, 50))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(pal.text)
            p.drawText(QPointF(x, by), self.page)
            x += fm2.horizontalAdvance(self.page) + 10.0
        if cfg["bar_eq"]:
            self.paint_eq(p, pal, x + 22.0, right_edge - 6.0, h)
        for name, r in self.btn_rects().items():
            hot = self.hover == name
            if hot:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(232, 64, 80, 230) if name == "close" else with_alpha(pal.text, 34))
                p.drawRoundedRect(r, 9, 9)
            col = QColor(255, 255, 255) if (hot and name == "close") else pal.text
            p.setPen(QPen(col, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            c = r.center()
            if name == "close":
                p.drawLine(QPointF(c.x() - 4.5, c.y() - 4.5), QPointF(c.x() + 4.5, c.y() + 4.5))
                p.drawLine(QPointF(c.x() - 4.5, c.y() + 4.5), QPointF(c.x() + 4.5, c.y() - 4.5))
            else:
                p.drawLine(QPointF(c.x() - 5, c.y() + 2), QPointF(c.x() + 5, c.y() + 2))
        p.end()


class SettingsDialog(Panel):
    PAGES = (
        "Themes",
        "Colors",
        "Card",
        "Typography",
        "Lyrics",
        "Animations",
        "Overlay",
        "Widgets",
        "Menu",
        "Player",
        "Config",
        "About",
    )

    def __init__(self, ctl, page=0):
        super().__init__(ctl)
        self.pos_buttons = {}
        self.reset_armed = False
        self.setWindowTitle("Lyrics HUD")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, self.cfg["bar_mode"] != "native")
        self.resize(820, 680)
        self.setMinimumSize(700, 500)
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.outer = outer
        self.titlebar = TitleBar(self)
        self.titlebar.setVisible(self.cfg["bar_mode"] == "custom")
        self.bar_pos_applied = "top"
        outer.addWidget(self.titlebar)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addLayout(root, 1)

        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(176)
        self.side_w = side
        side.installEventFilter(self)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 10)
        sl.setSpacing(0)
        credit = QLabel("by CyberSecPwner")
        credit.setObjectName("hint")
        credit.setContentsMargins(18, 10, 18, 4)
        sl.addWidget(credit)
        self.nav = NavList(self.state)
        self.nav.setObjectName("nav")
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for name in self.PAGES:
            self.nav.addItem(name)
        sl.addWidget(self.nav, 1)
        self.np = QWidget()
        self.np.setObjectName("npcard")
        npl = QHBoxLayout(self.np)
        npl.setContentsMargins(8, 8, 8, 8)
        self.np_cover = QLabel()
        self.np_cover.setFixedSize(38, 38)
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
        npw.setContentsMargins(10, 0, 10, 0)
        npw.addWidget(self.np)
        sl.addLayout(npw)
        root.addWidget(side)

        main = QWidget()
        main.setObjectName("main")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.header = QLabel("Themes")
        self.header.setObjectName("title")
        ml.addWidget(self.header)
        self.preview = Preview(ctl)
        pw = QHBoxLayout()
        pw.setContentsMargins(24, 2, 24, 4)
        pw.addWidget(self.preview)
        ml.addLayout(pw)
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 8, 24, 14)
        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.close)
        foot.addStretch(1)
        foot.addWidget(close)
        self.grip = QSizeGrip(self)
        self.grip.setVisible(self.cfg["bar_mode"] != "native")
        foot.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        ml.addLayout(foot)
        root.addWidget(main, 1)

        self.build_themes()
        self.build_colors()
        self.build_card()
        self.build_typography()
        self.build_lyrics()
        self.build_animations()
        self.build_overlay()
        self.build_widgets()
        self.build_menu_page()
        self.build_player()
        self.build_config()
        self.build_about()
        self.nav.currentRowChanged.connect(self.on_nav)
        self.nav.setCurrentRow(clamp(int(page), 0, len(self.PAGES) - 1))
        self.state.track_changed.connect(self.np_update)
        self.state.track_changed.connect(self.song_off_update)
        self.state.offset_changed.connect(self.song_off_update)
        self.state.palette_changed.connect(self.on_palette)
        self.np_update()
        self.sync_manual()
        self.place_bar()

    def eventFilter(self, obj, ev):
        if (
            obj is self.side_w
            and self.cfg["bar_mode"] == "hidden"
            and ev.type() == QEvent.Type.MouseButtonPress
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()
            return True
        return super().eventFilter(obj, ev)

    def place_bar(self):
        pos = self.cfg["bar_pos"]
        if pos != self.bar_pos_applied:
            self.outer.removeWidget(self.titlebar)
            self.outer.insertWidget(0 if pos == "top" else self.outer.count(), self.titlebar)
            self.bar_pos_applied = pos
        self.titlebar.sync()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        pal = self.state.pal_target
        p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.5), 110), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()

    def on_nav(self, i):
        i = max(0, i)
        self.stack.setCurrentIndex(i)
        self.header.setText(self.PAGES[i])
        self.titlebar.set_page(self.PAGES[i])
        self.preview.setVisible(self.PAGES[i] not in ("Config", "About", "Menu"))
        self.animate_in(self.stack.currentWidget())

    def animate_in(self, w):
        if not self.cfg["menu_anim"] or not self.isVisible():
            return
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(360)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        a.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def on_palette(self):
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)
        self.place_bar()
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
        lay.setContentsMargins(24, 0, 24, 16)
        lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        return PageLay(self, lay)

    def sync_manual(self):
        for w in self.manual:
            w.setEnabled(not self.cfg["adaptive"])

    def reopen(self):
        page = self.nav.currentRow()
        self.close()
        QTimer.singleShot(0, lambda: self.ctl.open_settings(page))

    def apply_many(self, values):
        for k, v in values.items():
            self.cfg[k] = list(v) if isinstance(v, list) else v
        self.ctl.refresh()
        self.reopen()

    def apply_theme(self, name):
        values = THEMES.get(name)
        if values is None:
            self.set_val("theme", name)
            return
        self.apply_many(dict(values, theme=name))

    def theme_grid(self):
        box = QWidget()
        gl = QGridLayout(box)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        group = QButtonGroup(box)
        group.setExclusive(True)
        for n, (label, val) in enumerate(THEME_LABELS):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setFixedHeight(54)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(self.cfg["theme"] == val)
            b.clicked.connect(lambda _=False, v=val: self.apply_theme(v))
            group.addButton(b)
            gl.addWidget(b, n // 3, n % 3)
        return box

    def preset_grid(self):
        box = QWidget()
        gl = QGridLayout(box)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        for n, (name, a, s, t) in enumerate(PRESETS):
            b = QPushButton(name)
            b.setFixedSize(112, 40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            fg = "#000" if QColor(a).lightness() > 150 else "#fff"
            b.setStyleSheet(
                f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {a},stop:1 {s});color:{fg};"
                f"border:1px solid rgba(255,255,255,50);border-radius:9px;font-weight:700;font-size:11px;padding:0;}}"
                "QPushButton:hover{border:2px solid #fff;}"
            )
            b.clicked.connect(
                lambda _=False, a=a, s=s, t=t: self.apply_many({"accent": a, "secondary": s, "text": t, "adaptive": False})
            )
            gl.addWidget(b, n // 4, n % 4)
        return box

    def build_themes(self):
        lay = self.new_page()
        self.sec(lay, "Theme")
        lay.addWidget(self.theme_grid())
        hint = QLabel(THEME_HINTS.get(self.cfg["theme"], ""))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(hint)
        self.sec(lay, "Display")
        self.row(
            lay,
            "Display mode",
            self.segmented("mode", (("Player", "hud"), ("Floating lyrics", "holo"), ("Both", "both"))),
            "Player card, fullscreen floating lyrics, or the compact card plus overlay",
        )
        lay.addStretch(1)

    def build_colors(self):
        lay = self.new_page()
        self.sec(lay, "Album art")
        self.row(
            lay,
            "Match album art colors",
            self.switch("adaptive", self.sync_manual),
            "One switch that makes the card, menus, settings, clock and lyrics all use the colors of the current cover",
        )
        self.row(
            lay,
            "Color style",
            self.combo("adaptive_mode", ADAPTIVE_MODES),
            "How the colors taken from the cover are reshaped",
        )
        self.sec(lay, "Presets")
        lay.addWidget(self.preset_grid())
        self.sec(lay, "Custom colors")
        self.row(lay, "Accent", self.color("accent"), "Used when album art colors are off")
        self.row(lay, "Secondary", self.color("secondary"))
        self.row(lay, "Text", self.color("text"))
        self.row(lay, "Custom background", self.switch("custom_bg"), "Replaces the generated dark background of the card")
        self.row(lay, "Background color", self.color("bg_color"))
        lay.addStretch(1)

    def build_card(self):
        lay = self.new_page()
        self.sec(lay, "Size")
        size = QComboBox()
        size.setFixedWidth(200)
        for label, val in CARD_SIZE_ITEMS:
            size.addItem(label, val)
        size.setCurrentIndex(max(0, size.findData(self.cfg["card_size"])))
        size.currentIndexChanged.connect(lambda _: self.ctl.set_card_size(size.currentData()))
        self.row(lay, "Card size", size, "Drag the bottom right corner for any size in between")
        self.row(lay, "HUD scale", self.slider("hud_scale", 60, 180, "%"), "Scales everything on the card. Ctrl and mouse wheel works too")
        self.row(lay, "Card text size", self.slider("ui_font", 80, 140, "%"))
        self.sec(lay, "Glass")
        self.row(lay, "Overall opacity", self.slider("opacity", 30, 100, "%"), "Fades the whole card, content included. Shift and mouse wheel works too")
        self.row(lay, "Glass opacity", self.slider("glass", 10, 100, "%"), "Lower values let more of the desktop show through the card")
        self.row(lay, "Background blur", self.switch("blur"), "Blurs whatever is behind the glass, needs Windows 10 or newer")
        self.row(lay, "Card style", self.combo("card_style", CARD_STYLES))
        self.row(lay, "Corner roundness", self.slider("card_radius", 8, 32, " px"))
        self.row(lay, "Cover tint", self.slider("backdrop", 0, 100, "%"), "How strongly the album art colors the card background")
        self.row(lay, "Frost strength", self.slider("frost", 0, 100, "%"), "Grain, top light and the gliding sheen of the Frosted glass style")
        self.sec(lay, "Borders and glow")
        self.row(lay, "Border strength", self.slider("border_alpha", 0, 200, "%"))
        self.row(lay, "Border thickness", self.slider("border_width", 1, 4, " px"))
        self.row(lay, "Animated border glow", self.slider("card_glow", 0, 100, "%"), "Light that travels around the card edge while music plays")
        self.row(lay, "Soft shadow", self.slider("card_shadow", 0, 100, "%"))
        self.sec(lay, "Background image")
        self.row(lay, "Image", self.file_box("bg_image", "Choose background image", IMG_FILTER), ".png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Image opacity", self.slider("bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Image blur", self.slider("bg_image_blur", 0, 100, "%"))
        self.sec(lay, "Content")
        self.row(lay, "Equalizer bars", self.switch("show_eq"), "Replaces the status dot with live bars")
        self.row(lay, "Show sync buttons", self.switch("show_sync"), "Quick offset buttons on the card for the current song")
        self.row(lay, "Show cover art", self.switch("show_cover"))
        self.row(lay, "Show album name", self.switch("show_album"))
        self.row(lay, "Show status line", self.switch("show_status"))
        lay.addStretch(1)

    def build_typography(self):
        lay = self.new_page()
        self.sec(lay, "Font")
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
        self.sec(lay, "Lyric text")
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
        self.sec(lay, "Text image")
        self.row(lay, "Image over text", self.switch("text_image_on"), "The letters are filled with your image instead of a color")
        self.row(lay, "Image", self.file_box("text_image", "Choose text image", IMG_FILTER), "GIFs use their first frame")
        self.sec(lay, "Lyric style")
        self.row(
            lay,
            "Text fill",
            self.combo("lyric_fill", LYRIC_FILL_ITEMS),
            "Gradients fade across each line. Fixed color fills switch to the album art colors while Match album art colors is on",
        )
        self.row(lay, "Custom lyric color", self.color("lyric_color"), "Used by the Custom colors fill")
        self.row(lay, "Custom lyric color 2", self.color("lyric_color2"), "The line fades from the first color into this one")
        self.row(lay, "Glow", self.slider("glow", 0, 100, "%"))
        self.row(
            lay,
            "Glow color",
            self.combo("glow_color", [("Accent", "accent"), ("Secondary", "secondary"), ("Text", "text")]),
        )
        self.row(lay, "Lyric opacity", self.slider("lyric_opacity", 10, 100, "%"))
        self.row(lay, "Outline", self.slider("lyric_outline", 0, 6, " px"), "Dark edge that keeps text readable on bright backgrounds")
        self.row(lay, "Shadow", self.slider("lyric_shadow", 0, 100, "%"))
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
        off = QSpinBox()
        off.setRange(-5000, 5000)
        off.setSingleStep(50)
        off.setSuffix(" ms")
        off.setFixedWidth(120)
        off.setValue(int(self.cfg["offset_ms"]))
        off.valueChanged.connect(lambda v: self.set_val("offset_ms", v, False))
        self.row(lay, "Sync offset", off, "Positive shows lyrics earlier, negative later")
        self.sec(lay, "Cache")
        self.cache_info = QLabel()
        self.cache_info.setObjectName("hint")
        clear_btn = QPushButton("Clear lyrics cache")
        clear_btn.clicked.connect(self.clear_cache)
        self.row(lay, "Lyrics cache", clear_btn, "Deletes every saved lyric file so lyrics are downloaded fresh")
        lay.addWidget(self.cache_info)
        self.cache_update()
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

    def build_animations(self):
        lay = self.new_page()
        self.sec(lay, "Lyric animation")
        self.row(lay, "Line entrance", self.combo("enter_style", ENTER_ITEMS), "How each lyric line arrives")
        self.row(lay, "Line exit", self.combo("exit_style", EXIT_ITEMS), "How each lyric line leaves")
        self.row(lay, "Idle motion", self.combo("idle_anim", IDLE_ITEMS), "Gentle movement while a line is on screen")
        self.row(lay, "Motion", self.slider("motion", 0, 200, "%"), "How far lines slide, drift and zoom. 0 is a plain fade")
        self.row(lay, "Fade time", self.slider("fade_ms", 150, 1200, " ms"))
        self.row(lay, "Line hold", self.slider("hold", 50, 200, "%"), "How long a line stays up before fading, relative to the estimate")
        self.row(
            lay,
            "Lyrics only while sung",
            self.switch("karaoke"),
            "Karaoke fill: the line lights up word by word as it is sung. Lines always fade away once they end",
        )
        self.row(lay, "Unsung brightness", self.slider("dim_level", 10, 80, "%"), "How bright the part of the line that has not been sung yet stays")
        self.sec(lay, "Effects")
        self.row(lay, "3D tilt", self.switch("tilt"), "Lines swing in with a perspective tilt toward the screen center")
        self.row(lay, "Scanlines", self.switch("scanlines"))
        self.row(lay, "Scanline strength", self.slider("scan_strength", 5, 100, "%"))
        self.row(lay, "Scanline spacing", self.slider("scan_gap", 2, 8, " px"))
        self.row(lay, "Glitch and chroma ghost", self.switch("glitch"))
        self.row(lay, "Glitch intensity", self.slider("glitch_amount", 20, 250, "%"))
        self.row(lay, "Chroma ghost strength", self.slider("ghost", 0, 200, "%"))
        self.row(lay, "Light flicker", self.slider("flicker", 0, 300, "%"))
        self.sec(lay, "Interface")
        self.row(lay, "Interface animations", self.switch("ui_anim"), "Hover effects, entrance animation and track change transitions")
        self.row(
            lay,
            "Animation rate",
            self.combo(
                "fps",
                [("24 fps", 24), ("30 fps", 30), ("45 fps", 45), ("60 fps", 60), ("90 fps", 90), ("120 fps", 120), ("144 fps", 144)],
            ),
            "Higher values look smoother and use more CPU and GPU",
        )
        self.row(
            lay,
            "Optimization",
            self.combo("optimize", OPTIMIZE_ITEMS),
            "Balanced caps animation at 45 fps. Performance caps it at 30 fps and turns off the animated menu glow",
        )
        lay.addStretch(1)

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
        self.row(lay, "Always on top", self.switch("always_on_top"), "Keeps the player card and the clock above other windows")
        self.row(lay, "Hide in fullscreen apps", self.switch("autohide_fullscreen"), "Hides the card, clock and lyrics while a game or video is fullscreen and shows them again afterwards")
        self.row(lay, "Lyrics over card and widgets", self.switch("lyrics_over_ui"), "On lets lyrics appear on top of the card and the clock. Off moves them to another free spot")
        self.row(lay, "Distance from card", self.slider("card_gap", 0, 80, " px"), "When lyrics stay clear, they keep at least this much space from the card and widgets")
        self.sec(lay, "Toast")
        self.row(lay, "Now playing toast", self.switch("show_toast"), "Shows the title and artist at the top of the screen when a song starts")
        self.row(lay, "Toast duration", self.slider("toast_secs", 2, 12, " s"))
        lay.addStretch(1)

    def build_widgets(self):
        lay = self.new_page()
        self.sec(lay, "Welcome screen")
        self.row(lay, "Show on startup", self.switch("show_welcome"), "Greets you by name when the app starts")
        play = QPushButton("Preview")
        play.clicked.connect(lambda: self.ctl.welcome.play(False))
        self.row(lay, "Preview welcome", play, "The welcome card is docked to the player card and follows it")
        self.sec(lay, "Launch audio")
        self.row(lay, "Play on launch", self.switch("launch_audio_on"), "Plays your own sound every time the app starts")
        self.row(lay, "Audio file", self.file_box("launch_audio", "Choose launch audio", AUDIO_FILTER), ".mp3, .wav, .ogg, .flac, .m4a or .wma")
        self.row(lay, "Launch volume", self.slider("launch_audio_volume", 0, 100, "%"))
        test = QPushButton("Play")
        test.clicked.connect(lambda: self.ctl.play_launch(True))
        self.row(lay, "Test sound", test)
        self.sec(lay, "Live clock")
        self.row(lay, "Show clock", self.switch("show_clock"), "A draggable glass clock that follows your theme")
        self.row(lay, "24 hour time", self.switch("clock_24h"))
        self.row(lay, "Show seconds", self.switch("clock_seconds"))
        self.row(lay, "Show date", self.switch("clock_date"))
        self.row(lay, "Clock size", self.slider("clock_scale", 60, 200, "%"))
        self.row(lay, "Clock opacity", self.slider("clock_opacity", 30, 100, "%"))
        self.row(lay, "Clock background image", self.file_box("clock_bg_image", "Choose clock background", IMG_FILTER), "Separate from the player card background. .png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Clock image opacity", self.slider("clock_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Clock image blur", self.slider("clock_bg_image_blur", 0, 100, "%"))
        reset = QPushButton("Reset clock position")
        reset.clicked.connect(self.ctl.reset_clock)
        self.row(lay, "Clock position", reset)
        lay.addStretch(1)

    def build_menu_page(self):
        lay = self.new_page()
        self.sec(lay, "Wallpaper")
        self.row(
            lay,
            "Image",
            self.file_box("menu_image", "Choose menu wallpaper", IMG_FILTER),
            "Shown behind this window, quick customize and the tray menu",
        )
        self.row(lay, "Wallpaper opacity", self.slider("menu_image_opacity", 0, 100, "%"))
        self.row(lay, "Wallpaper blur", self.slider("menu_blur", 0, 100, "%"))
        self.row(lay, "Wallpaper dimming", self.slider("menu_dim", 0, 100, "%"), "Darkens the wallpaper so text stays readable")
        self.sec(lay, "Animation")
        self.row(
            lay,
            "Animated menus",
            self.switch("menu_anim"),
            "Fade-ins, page transitions, sliding switches, the gliding sidebar and the drifting glow",
        )
        self.sec(lay, "Title bar")
        mode = self.combo("bar_mode", [("Custom", "custom"), ("Windows", "native"), ("Hidden", "hidden")])
        mode.currentIndexChanged.connect(lambda _: self.reopen())
        self.row(lay, "Style", mode, "Custom is the themed bar. Windows uses the system title bar. Hidden removes it and lets you drag the window by the sidebar")
        self.row(lay, "Position", self.combo("bar_pos", [("Top", "top"), ("Bottom", "bottom")]))
        self.row(lay, "Alignment", self.combo("bar_align", [("Left", "left"), ("Center", "center")]))
        self.row(lay, "Window buttons", self.combo("bar_btn_pos", [("Right", "right"), ("Left", "left")]))
        self.row(lay, "Height", self.slider("bar_height", 36, 64, " px"))
        self.row(lay, "Show name", self.switch("bar_brand"))
        self.row(lay, "Show page", self.switch("bar_page"))
        self.sec(lay, "Equalizer")
        self.row(lay, "Equalizer waves", self.switch("bar_eq"), "Animated bars in the title bar that move with your music")
        self.row(lay, "Style", self.combo("bar_eq_style", [("Bars", "bars"), ("Wave", "wave")]))
        self.row(lay, "Color", self.combo("bar_eq_color", [("Accent to secondary", "gradient"), ("Accent", "accent"), ("Text", "text")]))
        self.row(lay, "Bars", self.slider("bar_eq_bars", 6, 40))
        lay.addStretch(1)

    def build_player(self):
        lay = self.new_page()
        self.sec(lay, "Controls")
        self.row(lay, "Show volume bar", self.switch("show_volume"), "Scroll over the card to change it too")
        self.row(lay, "Volume of playing app only", self.switch("app_volume"), "The volume bar changes only the app that plays the song. Uses system volume if that app is not found")
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

    def build_config(self):
        lay = self.new_page()
        self.cfg_info = QLabel()
        self.cfg_info.setObjectName("hint")
        self.cfg_info.setWordWrap(True)
        lay.addWidget(self.cfg_info)
        self.sec(lay, "Profiles")
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Profile name")
        self.profile_name.setFixedWidth(170)
        save = QPushButton("Save")
        save.clicked.connect(self.save_profile)
        sbox = QWidget()
        sbl = QHBoxLayout(sbox)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.addWidget(self.profile_name)
        sbl.addWidget(save)
        self.row(lay, "Save current settings", sbox, "Stores every look and lyric setting under a name")
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(170)
        load = QPushButton("Load")
        delete = QPushButton("Delete")
        load.clicked.connect(self.load_profile)
        delete.clicked.connect(self.delete_profile)
        lbox = QWidget()
        lbl = QHBoxLayout(lbox)
        lbl.setContentsMargins(0, 0, 0, 0)
        lbl.addWidget(self.profile_combo)
        lbl.addWidget(load)
        lbl.addWidget(delete)
        self.row(lay, "Saved profiles", lbox, "Window and clock positions are not part of a profile")
        self.fill_profiles()
        self.sec(lay, "Share code")
        self.code_out = QLineEdit()
        self.code_out.setReadOnly(True)
        self.code_out.setFixedWidth(260)
        gen = QPushButton("Generate")
        copy = QPushButton("Copy")
        qr = QPushButton("QR code")
        gen.clicked.connect(self.make_code)
        copy.clicked.connect(self.copy_code)
        qr.clicked.connect(self.show_qr)
        code_box = QWidget()
        cbl = QHBoxLayout(code_box)
        cbl.setContentsMargins(0, 0, 0, 0)
        cbl.addWidget(self.code_out)
        cbl.addWidget(gen)
        cbl.addWidget(copy)
        cbl.addWidget(qr)
        self.row(lay, "Your code", code_box, "Send this code to a friend. Image, font and audio files are not included")
        self.code_in = QLineEdit()
        self.code_in.setPlaceholderText("Paste a code here")
        self.code_in.setFixedWidth(260)
        use = QPushButton("Apply")
        use.clicked.connect(self.use_code)
        in_box = QWidget()
        ibl = QHBoxLayout(in_box)
        ibl.setContentsMargins(0, 0, 0, 0)
        ibl.addWidget(self.code_in)
        ibl.addWidget(use)
        self.row(lay, "Enter a code", in_box, "Applies the settings from a code someone shared with you")
        self.sec(lay, "Backup")
        export = QPushButton("Export")
        imp = QPushButton("Import")
        folder = QPushButton("Open folder")
        export.clicked.connect(self.export_cfg)
        imp.clicked.connect(self.import_cfg)
        folder.clicked.connect(self.open_folder)
        bbox = QWidget()
        bbl = QHBoxLayout(bbox)
        bbl.setContentsMargins(0, 0, 0, 0)
        bbl.addWidget(export)
        bbl.addWidget(imp)
        bbl.addWidget(folder)
        self.row(lay, "Settings file", bbox, "Export to share or back up, import to restore, or open the folder that holds everything")
        self.sec(lay, "Reset")
        self.reset_btn = QPushButton("Reset all settings to default")
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.disarm_reset)
        self.reset_btn.clicked.connect(self.arm_reset)
        self.row(lay, "Defaults", self.reset_btn, "Restores every setting. Window positions are kept")
        lay.addStretch(1)

    def build_about(self):
        lay = self.new_page()
        self.sec(lay, "How it works")
        for t in (
            "Reads the Windows media session, so Spotify, YouTube Music in a browser and other players work with no client ID.",
            "Synced lyrics come from LRCLIB and are cached on disk.",
            "Click the progress bar to seek. Scroll over the card for volume, hold Ctrl to scale the card or Shift to change its opacity. Right-click the card for the quick menu.",
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

    def cache_update(self):
        files = list(CACHE_DIR.glob("*.json"))
        size = 0
        for f in files:
            try:
                size += f.stat().st_size
            except Exception:
                pass
        self.cache_info.setText(f"{len(files)} cached songs, {size / 1024:.1f} KB")

    def clear_cache(self):
        count, size = clear_lyrics_cache()
        self.cache_info.setText(f"Cleared {count} cached songs, freed {size / 1024:.1f} KB")
        if self.state.title:
            self.state.request_lyrics()

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

    def file_box(self, key, title, filt):
        edit = QLineEdit(self.cfg[key])
        edit.setReadOnly(True)
        edit.setPlaceholderText("None")
        edit.setFixedWidth(170)
        browse = QPushButton("Browse")
        clear = QPushButton("Clear")
        browse.clicked.connect(lambda: self.pick_file(key, edit, title, filt))
        clear.clicked.connect(lambda: self.clear_file(key, edit))
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(edit)
        bl.addWidget(browse)
        bl.addWidget(clear)
        return box

    def pick_file(self, key, edit, title, filt):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if path:
            edit.setText(path)
            self.set_val(key, path)

    def clear_file(self, key, edit):
        edit.setText("")
        self.set_val(key, "")

    def fill_profiles(self):
        self.profile_combo.clear()
        for n in list_profiles():
            self.profile_combo.addItem(n, n)

    def save_profile(self):
        path = profile_path(self.profile_name.text())
        if path is None:
            self.cfg_info.setText("Type a profile name first")
            return
        try:
            self.cfg.write_to(path)
        except Exception as e:
            self.cfg_info.setText("Could not save: " + str(e))
            return
        self.cfg_info.setText("Saved profile " + path.stem)
        self.fill_profiles()

    def import_from(self, path):
        try:
            self.cfg.read_from(path)
        except Exception as e:
            self.cfg_info.setText("Could not load: " + str(e))
            return
        self.ctl.refresh()
        self.reopen()

    def load_profile(self):
        name = self.profile_combo.currentData()
        if name:
            self.import_from(profile_path(name))

    def delete_profile(self):
        name = self.profile_combo.currentData()
        if not name:
            return
        try:
            os.remove(str(profile_path(name)))
        except OSError as e:
            self.cfg_info.setText("Could not delete: " + str(e))
            return
        self.cfg_info.setText("Deleted profile " + name)
        self.fill_profiles()

    def make_code(self):
        self.code_out.setText(self.cfg.share_code())
        self.cfg_info.setText("Code generated")

    def copy_code(self):
        if not self.code_out.text():
            self.make_code()
        QApplication.clipboard().setText(self.code_out.text())
        self.cfg_info.setText("Code copied")

    def use_code(self):
        try:
            self.cfg.apply_code(self.code_in.text())
        except Exception:
            self.cfg_info.setText("That code is not valid")
            return
        self.ctl.refresh()
        self.cfg_info.setText("Code applied")
        self.reopen()

    def show_qr(self):
        if not self.code_out.text():
            self.make_code()
        try:
            import qrcode

            q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_L)
            q.add_data(self.code_out.text())
            q.make(fit=True)
            m = q.get_matrix()
        except Exception:
            self.cfg_info.setText("QR codes need the qrcode package, restart the app to install it")
            return
        n = len(m)
        cell = max(4, 420 // n)
        img = QImage(n * cell, n * cell, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        qp = QPainter(img)
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(0, 0, 0))
        for y, rowv in enumerate(m):
            for x, v in enumerate(rowv):
                if v:
                    qp.drawRect(x * cell, y * cell, cell, cell)
        qp.end()
        dlg = QDialog(self)
        dlg.setWindowTitle("Share QR code")
        lay = QVBoxLayout(dlg)
        lab = QLabel()
        lab.setPixmap(QPixmap.fromImage(img))
        lay.addWidget(lab)
        dlg.exec()

    def export_cfg(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export settings", str(APP_DIR / "lyrics_hud_settings.json"), "JSON (*.json)")
        if not path:
            return
        try:
            self.cfg.write_to(path)
        except Exception as e:
            self.cfg_info.setText("Could not export: " + str(e))
            return
        self.cfg_info.setText("Exported to " + path)

    def import_cfg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import settings", str(APP_DIR), "JSON (*.json)")
        if path:
            self.import_from(path)

    def open_folder(self):
        try:
            os.startfile(str(APP_DIR))
        except OSError as e:
            self.cfg_info.setText("Could not open the folder: " + str(e))

    def arm_reset(self):
        if self.reset_armed:
            self.on_reset()
            return
        self.reset_armed = True
        self.reset_btn.setText("Click again to confirm")
        self.reset_timer.start(3000)

    def disarm_reset(self):
        self.reset_armed = False
        self.reset_btn.setText("Reset all settings to default")

    def on_reset(self):
        self.cfg.reset()
        self.ctl.refresh()
        self.reopen()

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


class QuickPanel(Panel):
    def __init__(self, ctl):
        super().__init__(ctl)
        self.setWindowTitle("Quick customize")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedWidth(500)
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 12, 24, 20)
        lay.setSpacing(2)
        self.sec(lay, "Quick customize")
        self.row(lay, "Match album art colors", self.switch("adaptive"))
        self.row(lay, "HUD scale", self.slider("hud_scale", 60, 180, "%"))
        self.row(lay, "Overall opacity", self.slider("opacity", 30, 100, "%"))
        self.row(lay, "Glass opacity", self.slider("glass", 10, 100, "%"))
        self.row(lay, "Soft shadow", self.slider("card_shadow", 0, 100, "%"))
        self.row(lay, "Lyric size", self.slider("font_size", 14, 72, " px"))
        self.row(lay, "Glow", self.slider("glow", 0, 100, "%"))
        self.row(lay, "Line entrance", self.combo("enter_style", ENTER_ITEMS))
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.clicked.connect(self.close)
        lay.addSpacing(10)
        lay.addWidget(done, 0, Qt.AlignmentFlag.AlignRight)
        self.state.palette_changed.connect(self.on_palette)

    def on_palette(self):
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)
        dark_titlebar(self, self.state.pal_target)


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
        set_text_image(self.cfg)
        self.theme = Theme(self.cfg)
        self.state = State(self.cfg)
        self.volume = VolumeControl()
        self.vol_level = 0.5
        self.vol_muted = False
        self.hud = Hud(self)
        self.holo = Holo(self)
        self.clock = Clock(self)
        self.welcome = Welcome(self)
        self.settings = None
        self.quick = None
        self.player = None
        self.audio_out = None
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
        self.fs_hidden = False
        self.fs_timer = QTimer()
        self.fs_timer.timeout.connect(self.poll_fullscreen)
        self.fs_timer.start(1000)
        self.apply_mode()
        self.apply_hotkeys()
        first = not self.cfg["welcomed"]
        self.cfg["welcomed"] = True
        self.cfg.save()
        self.play_launch()
        if self.cfg["show_welcome"]:
            self.welcome.play(first)
        app.aboutToQuit.connect(self.shutdown)

    def build_menu(self):
        m = GlassMenu(self)
        m.addAction("Play / pause", self.state.toggle_play)
        m.addAction("Next track", self.state.skip_next)
        m.addAction("Previous track", self.state.skip_prev)
        m.addSeparator()
        m.addAction("Show / hide", self.toggle_visible)
        sub = GlassMenu(self, m)
        sub.setTitle("Display mode")
        m.addMenu(sub)
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
        self.act_adaptive = QAction("Match album art colors", m)
        self.act_adaptive.setCheckable(True)
        self.act_adaptive.triggered.connect(self.toggle_adaptive)
        m.addAction(self.act_adaptive)
        m.addSeparator()
        m.addAction("Lyrics earlier (+100 ms)", lambda: self.nudge(100))
        m.addAction("Lyrics later (-100 ms)", lambda: self.nudge(-100))
        m.addAction("Reset sync offset", lambda: self.nudge(None))
        m.addAction("Sync: current line starts now", lambda: self.snap(0))
        m.addAction("Sync: next line starts now", lambda: self.snap(1))
        m.addSeparator()
        m.addAction("Settings", lambda: self.open_settings())
        m.addAction("Quick customize", self.open_quick)
        m.addAction("Reset card position", self.reset_hud)
        m.addSeparator()
        m.addAction("Quit", self.app.quit)
        m.aboutToShow.connect(self.sync_menu)
        return m

    def on_palette(self):
        pal = self.state.pal_target
        apply_qss(self.menu, pal, self.theme.family)
        self.tray.setIcon(make_icon(pal))
        self.hud.dirty = True
        self.holo.dirty = True
        self.clock.dirty = True

    def sync_menu(self):
        self.act_lock.setChecked(bool(self.cfg["click_through"]))
        self.act_adaptive.setChecked(bool(self.cfg["adaptive"]))
        for val, a in self.mode_actions.items():
            a.setChecked(self.cfg["mode"] == val)

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        self.cfg["visible"] = not self.cfg["visible"]
        self.apply_mode()
        self.cfg.save()

    def poll_fullscreen(self):
        if not self.cfg["autohide_fullscreen"]:
            if self.fs_hidden:
                self.fs_hidden = False
                self.apply_mode()
            return
        full = fullscreen_app_active()
        if full and not self.fs_hidden:
            self.fs_hidden = True
            for w in (self.hud, self.holo, self.clock):
                w.hide()
        elif not full and self.fs_hidden:
            self.fs_hidden = False
            self.apply_mode()

    def hide_all(self):
        self.cfg["visible"] = False
        self.apply_mode()
        self.cfg.save()

    def toggle_lock(self):
        self.cfg["click_through"] = not self.cfg["click_through"]
        self.refresh()

    def toggle_adaptive(self):
        self.cfg["adaptive"] = not self.cfg["adaptive"]
        self.refresh()
        if self.settings is not None and self.settings.isVisible():
            self.settings.reopen()

    def play_launch(self, force=False):
        path = self.cfg["launch_audio"]
        if not (force or self.cfg["launch_audio_on"]) or not path or not os.path.isfile(path):
            return
        if self.player is None:
            self.audio_out = QAudioOutput()
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(self.cfg["launch_audio_volume"] / 100.0)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

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

    def reset_clock(self):
        self.clock.reset_pos()

    def bump(self, key, delta, lo, hi):
        self.cfg[key] = int(clamp(self.cfg[key] + delta, lo, hi))
        self.refresh()

    def set_card_size(self, key):
        w, h = CARD_SIZES.get(key, CARD_SIZES["medium"])
        s = self.hud.scale
        self.cfg["card_size"] = key
        self.cfg["hud_w"] = int(w * s)
        self.cfg["hud_h"] = int(h * s)
        self.refresh()
        self.hud.resize(int(w * s), int(h * s))
        self.hud.save_geometry()

    def poll_volume(self):
        self.volume.app = self.state.app
        self.volume.per_app = bool(self.cfg["app_volume"])
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

    def open_settings(self, page=0):
        if self.settings is not None and self.settings.isVisible():
            self.settings.raise_()
            self.settings.activateWindow()
            return
        self.settings = SettingsDialog(self, page)
        self.settings.show()

    def open_quick(self):
        if self.quick is not None and self.quick.isVisible():
            self.quick.raise_()
            self.quick.activateWindow()
            return
        self.quick = QuickPanel(self)
        self.quick.show()

    def apply_mode(self):
        mode = self.cfg["mode"]
        visible = bool(self.cfg["visible"])
        if visible and mode in ("hud", "both"):
            if not self.hud.isVisible():
                self.hud.show()
        else:
            self.hud.hide()
        if visible and self.cfg["show_clock"]:
            if not self.clock.isVisible():
                self.clock.show()
        else:
            self.clock.hide()
        if visible and mode in ("holo", "both"):
            self.holo.place()
            self.holo.attach_wall()
            if not self.holo.isVisible():
                self.holo.show()
        else:
            self.holo.hide()

    def refresh(self):
        set_text_image(self.cfg)
        self.theme.reload()
        self.state.recompute_palette()
        self.hud.refresh()
        self.holo.refresh()
        self.clock.refresh()
        self.apply_mode()
        self.apply_hotkeys()
        if self.audio_out is not None:
            self.audio_out.setVolume(self.cfg["launch_audio_volume"] / 100.0)
        if self.settings is not None and self.settings.isVisible():
            self.settings.preview.refresh()
            self.settings.update()
        self.cfg.save()

    def shutdown(self):
        self.stop_hotkeys()
        if self.player is not None:
            self.player.stop()
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
