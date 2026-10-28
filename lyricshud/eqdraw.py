import math

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainterPath, QBrush, QLinearGradient

from lyricshud.utils import mix


def eq_step(levels, t, playing, peak):
    base = 0.0
    if playing:
        base = min(1.0, peak * 2.2) if peak is not None else 0.7
    for i in range(len(levels)):
        wob = 0.5 + 0.5 * math.sin(t * (2.1 + i * 0.13) + i * 0.9) * math.sin(t * 1.7 + i * 0.37)
        target = 0.06 + 0.94 * base * (0.25 + 0.75 * abs(wob)) if playing else 0.05
        levels[i] += (target - levels[i]) * 0.35


def draw_eq(p, pal, levels, x0, x1, top, h, n, style, mode):
    width = x1 - x0
    if mode == "accent":
        brush = QBrush(pal.accent)
    elif mode == "text":
        brush = QBrush(mix(pal.text, pal.bg, 0.35))
    else:
        g = QLinearGradient(x0, 0, x1, 0)
        g.setColorAt(0, pal.accent)
        g.setColorAt(1, pal.secondary)
        brush = QBrush(g)
    cy = top + h / 2.0
    amp = h * 0.34
    step = width / n
    if style == "wave":
        path = QPainterPath()
        pts = [QPointF(x0 + step * (i + 0.5), cy - max(0.04, levels[i]) * amp) for i in range(n)]
        path.moveTo(pts[0])
        for k in range(1, n):
            mid = QPointF((pts[k - 1].x() + pts[k].x()) / 2.0, (pts[k - 1].y() + pts[k].y()) / 2.0)
            path.quadTo(pts[k - 1], mid)
        path.lineTo(pts[-1])
        for k in range(n - 1, -1, -1):
            path.lineTo(QPointF(pts[k].x(), 2 * cy - pts[k].y()))
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        p.setOpacity(p.opacity() * 0.55)
        p.drawPath(path)
        p.setOpacity(p.opacity() / 0.55)
        return
    bw = max(2.0, step * 0.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(brush)
    for i in range(n):
        bh = max(3.0, levels[i] * amp * 2.0)
        p.drawRoundedRect(QRectF(x0 + step * i + (step - bw) / 2.0, cy - bh / 2.0, bw, bh), bw / 2.0, bw / 2.0)
