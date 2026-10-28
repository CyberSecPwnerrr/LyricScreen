from collections import OrderedDict

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QPixmap,
    QLinearGradient,
)

from lyricshud.images import TEXT_IMG, TexLine
from lyricshud.styles import AA
from lyricshud.utils import WEIGHTS, clamp


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


def render_line(text, font, fill, glowc, glow, maxw, dpr, scan, align, sty=None, fill2=None, textured=False):
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
    if textured:
        p.end()
        mask = QPixmap(pm.size())
        mask.setDevicePixelRatio(dpr)
        mask.fill(Qt.GlobalColor.transparent)
        q = QPainter(mask)
        q.setRenderHints(AA)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(255, 255, 255))
        q.drawPath(path)
        q.end()
        return TexLine(pm, mask, float(w), float(h), meta, float(pad), dpr, scan)
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
        c = QColor(0, 0, 0, scan[0])
        yy = 0
        while yy < h:
            p.fillRect(QRectF(0, yy, w, 1), c)
            yy += scan[1]
    p.end()
    return pm, float(w), float(h), meta, float(pad)


def cached_line(cache, theme, text, px, fill, glowc, glow, maxw, dpr, scan, align, sty=None, fill2=None, textured=True):
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
    tex = bool(textured) and TEXT_IMG["src"] is not None
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
        TEXT_IMG["sig"] if tex else 0,
    )
    return cache.get(
        key,
        lambda: render_line(text, theme.font(px, weight, spacing), fill, glowc, glow, maxw, dpr, scan, align, sty, fill2, tex),
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
