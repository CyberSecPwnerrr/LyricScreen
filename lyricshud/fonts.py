import os
import json
import re
import threading
from urllib import request as urlrequest
from urllib import parse as urlparse

from PyQt6.QtCore import Qt, QObject, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QBrush, QFont, QPixmap, QLinearGradient
from PyQt6.QtWidgets import QComboBox

from lyricshud.paths import FONT_DIR, FONT_EXTS, GF_CSS, GF_META, UA
from lyricshud.styles import AA
from lyricshud.utils import with_alpha


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
