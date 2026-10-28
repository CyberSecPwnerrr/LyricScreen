import ctypes
from ctypes import wintypes

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPixmap

from lyricshud.styles import AA
from lyricshud.utils import clamp


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
