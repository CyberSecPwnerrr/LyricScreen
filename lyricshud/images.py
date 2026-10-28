import os
import time
import random
from bisect import bisect_right

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage, QMovie

from lyricshud.styles import AA
from lyricshud.utils import clamp


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
    def __init__(self, path, on_frame, lite=False):
        self.img = QImage(path)
        self.frames = []
        self.delays = []
        self.cum = []
        self.total = 0
        self.movie = None
        self.timer = None
        self.t0 = time.monotonic()
        self.last = -1
        self.shown = 0
        self.cb = on_frame
        self.max_side = 480 if lite else 960
        if lite and max(self.img.width(), self.img.height()) > self.max_side:
            self.img = self.img.scaled(
                self.max_side,
                self.max_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        if path.lower().endswith(".gif"):
            self.load_gif(path)
            if len(self.frames) > 1:
                self.timer = QTimer()
                self.timer.setInterval(40 if lite else 33)
                self.timer.timeout.connect(self.poll)
                self.timer.start()
            else:
                self.frames = []
                self.cum = []
                m = QMovie(path)
                if m.isValid() and m.frameCount() != 1:
                    self.movie = m
                    m.frameChanged.connect(lambda _=0: on_frame())
                    m.start()

    def load_gif(self, path):
        try:
            from PIL import Image, ImageSequence

            im = Image.open(path)
            n = min(240, max(1, int(getattr(im, "n_frames", 1) or 1)))
            side = self.max_side
            while side > 160 and n * side * side * 4 > 200000000:
                side = int(side * 0.85)
            for fr in ImageSequence.Iterator(im):
                if len(self.frames) >= 240:
                    break
                d = int(fr.info.get("duration", 100) or 100)
                if d <= 10:
                    d = 100
                rgba = fr.convert("RGBA")
                if max(rgba.size) > side:
                    rgba.thumbnail((side, side))
                w, h = rgba.size
                qi = QImage(rgba.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
                self.frames.append(qi)
                self.delays.append(d)
            acc = 0
            for d in self.delays:
                acc += d
                self.cum.append(acc)
            self.total = acc
        except Exception:
            self.frames = []
            self.delays = []
            self.cum = []
            self.total = 0

    def poll(self):
        n = self.number()
        if n != self.last:
            self.last = n
            self.shown = n
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
            return min(len(self.frames) - 1, bisect_right(self.cum, ms))
        if self.movie is not None:
            return self.movie.currentFrameNumber()
        return 0

    def shown_number(self):
        return self.shown if self.frames else self.number()

    def shown_frame(self):
        if self.frames:
            return self.frames[min(self.shown, len(self.frames) - 1)]
        return self.frame()

    def stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.movie is not None:
            self.movie.stop()
            self.movie = None


TEXT_IMG = {"path": None, "src": None, "sig": 0, "rect": (0.0, 0.0, 1.0, 1.0)}


def set_text_image(cfg, cb=None):
    path = cfg["text_image"] if cfg["text_image_on"] else ""
    rect = tuple(float(v) for v in cfg["text_image_rect"])
    if len(rect) != 4:
        rect = (0.0, 0.0, 1.0, 1.0)
    if path and os.path.isfile(path):
        if TEXT_IMG["path"] != path:
            if TEXT_IMG["src"] is not None:
                TEXT_IMG["src"].stop()
            src = ImageSrc(path, cb or (lambda: None), True)
            TEXT_IMG["src"] = src if (not src.img.isNull() or src.frames) else None
            TEXT_IMG["path"] = path
            TEXT_IMG["sig"] += 1
        if TEXT_IMG["rect"] != rect:
            TEXT_IMG["rect"] = rect
            TEXT_IMG["sig"] += 1
    elif TEXT_IMG["path"] is not None:
        if TEXT_IMG["src"] is not None:
            TEXT_IMG["src"].stop()
        TEXT_IMG["path"] = None
        TEXT_IMG["src"] = None
        TEXT_IMG["sig"] += 1


def draw_cover(p, img, rect, norm=None):
    iw = img.width()
    ih = img.height()
    r = norm or (0.0, 0.0, 1.0, 1.0)
    sx = clamp(float(r[0]), 0.0, 0.99) * iw
    sy = clamp(float(r[1]), 0.0, 0.99) * ih
    sw = max(1.0, min(iw - sx, float(r[2]) * iw))
    sh = max(1.0, min(ih - sy, float(r[3]) * ih))
    k = max(rect.width() / sw, rect.height() / sh)
    vw = rect.width() / k
    vh = rect.height() / k
    p.drawImage(rect, img, QRectF(sx + (sw - vw) / 2.0, sy + (sh - vh) / 2.0, vw, vh))


class TexLine:
    def __init__(self, base, mask, w, h, meta, pad, dpr, scan):
        self.base = base
        self.mask = mask
        self.info = (w, h, meta, pad)
        self.dpr = dpr
        self.scan = scan
        self.fid = None
        self.pm = None

    def __getitem__(self, i):
        if i == 0:
            return self.current()
        return self.info[i - 1]

    def current(self):
        src = TEXT_IMG["src"]
        if src is None:
            return self.base
        fid = src.shown_number()
        if self.pm is not None and fid == self.fid:
            return self.pm
        fr = src.shown_frame()
        if fr is None or fr.isNull():
            return self.base
        w, h = self.info[0], self.info[1]
        pm = QPixmap(self.base.size())
        pm.setDevicePixelRatio(self.dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHints(AA)
        draw_cover(q, fr, QRectF(0.0, 0.0, w, h), TEXT_IMG["rect"])
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        q.drawPixmap(0, 0, self.mask)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOver)
        q.drawPixmap(0, 0, self.base)
        if self.scan:
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            c = QColor(0, 0, 0, self.scan[0])
            yy = 0
            while yy < h:
                q.fillRect(QRectF(0, yy, w, 1), c)
                yy += self.scan[1]
        q.end()
        self.pm = pm
        self.fid = fid
        return pm


def crop_frame(fr, r):
    iw = fr.width()
    ih = fr.height()
    x = int(clamp(r[0], 0.0, 0.99) * iw)
    y = int(clamp(r[1], 0.0, 0.99) * ih)
    w = max(1, min(iw - x, int(r[2] * iw)))
    h = max(1, min(ih - y, int(r[3] * ih)))
    if w == iw and h == ih:
        return fr
    return fr.copy(QRect(x, y, w, h))


def cover_fit(src, w, h, blur):
    smooth = Qt.TransformationMode.SmoothTransformation
    ignore = Qt.AspectRatioMode.IgnoreAspectRatio
    sc = src.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
    sc = sc.copy((sc.width() - w) // 2, (sc.height() - h) // 2, w, h)
    if blur > 0:
        k = 1.0 - 0.97 * blur / 100.0
        sc = sc.scaled(max(2, int(w * k)), max(2, int(h * k)), ignore, smooth).scaled(w, h, ignore, smooth)
    return QPixmap.fromImage(sc)
