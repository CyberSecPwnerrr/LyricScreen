import os
import time
import subprocess
import ctypes
from ctypes import wintypes

from PyQt6.QtGui import QColor, QFont

from lyricshud.boot import IS_WIN
from lyricshud.defaults import DEFAULTS
from lyricshud.paths import CACHE_DIR


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


PERF = {"paints": 0, "ms": 0.0}


def timed(fn):
    def wrapper(self, e):
        t = time.perf_counter()
        fn(self, e)
        d = (time.perf_counter() - t) * 1000.0
        PERF["paints"] += 1
        PERF["ms"] = PERF["ms"] * 0.9 + d * 0.1 if PERF["ms"] else d
        prev = getattr(self, "paint_ms", 0.0)
        self.paint_ms = prev * 0.8 + d * 0.2 if prev else d

    return wrapper


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def tune_timer(w):
    want = int(clamp(max(w.base_ms, getattr(w, "paint_ms", 0.0) * 2.5), w.base_ms, 120))
    if abs(want - w.timer.interval()) > 3:
        w.timer.setInterval(want)


def open_path(path):
    if IS_WIN:
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
