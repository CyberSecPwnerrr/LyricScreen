import time
import math
import random

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from lyricshud.styles import AA
from lyricshud.utils import clamp, mix, with_alpha


class CreditBadge(QWidget):
    NAME = "CyberSecPwner"

    def __init__(self, panel, compact):
        super().__init__()
        self.panel = panel
        self.compact = compact
        self.t0 = time.monotonic()
        self.mouse = None
        self.sparks = []
        self.ripples = []
        self.pulse = 0.0
        self.setMouseTracking(True)
        self.setFixedHeight(66 if compact else 136)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def showEvent(self, e):
        self.timer.start(66 if self.panel.cfg["optimize"] == "performance" else 33)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def tick(self):
        dt = self.timer.interval() / 1000.0
        for sp in self.sparks:
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            sp[3] += 340.0 * dt
            sp[4] -= dt
        self.sparks = [sp for sp in self.sparks if sp[4] > 0]
        for rp in self.ripples:
            rp[2] += dt
        self.ripples = [rp for rp in self.ripples if rp[2] < 0.9]
        self.pulse *= 0.9
        self.update()

    def mouseMoveEvent(self, e):
        self.mouse = e.position()

    def leaveEvent(self, e):
        self.mouse = None
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position()
        self.ripples.append([pos.x(), pos.y(), 0.0])
        self.pulse = 1.0
        for _ in range(18):
            a = random.random() * math.tau
            v = 90.0 + random.random() * 190.0
            self.sparks.append([pos.x(), pos.y(), math.cos(a) * v, math.sin(a) * v - 70.0, 0.7 + random.random() * 0.5, random.randint(0, 2)])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.panel.state.pal_target
        th = self.panel.ctl.theme
        t = time.monotonic() - self.t0
        w = float(self.width())
        h = float(self.height())
        box = QRectF(6, 4, w - 12, h - 8)
        bg = QLinearGradient(box.topLeft(), box.bottomRight())
        bg.setColorAt(0, with_alpha(pal.accent, 38))
        bg.setColorAt(1, with_alpha(pal.secondary, 22))
        p.setPen(QPen(with_alpha(pal.accent, 90), 1.0))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(box, 14, 14)
        clip = QPainterPath()
        clip.addRoundedRect(box, 14, 14)
        p.save()
        p.setClipPath(clip)
        if self.mouse is not None:
            rg = QRadialGradient(self.mouse, h * 0.9)
            rg.setColorAt(0, with_alpha(pal.accent, 70))
            rg.setColorAt(1, with_alpha(pal.accent, 0))
            p.fillRect(box, QBrush(rg))
        for rp in self.ripples:
            k = rp[2] / 0.9
            p.setPen(QPen(with_alpha(pal.accent, int(200 * (1.0 - k))), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(rp[0], rp[1]), 8 + k * w * 0.5, 8 + k * w * 0.5)
        p.restore()
        small = th.font(9 if self.compact else 11, QFont.Weight.Bold, 5.0)
        fs = QFontMetrics(small)
        label = "MADE BY"
        p.setFont(small)
        p.setPen(with_alpha(pal.text, 170))
        ly = box.top() + (16.0 if self.compact else 30.0)
        p.drawText(QPointF(w / 2.0 - fs.horizontalAdvance(label) / 2.0, ly), label)
        big = th.font(16 if self.compact else 30, QFont.Weight.Bold)
        fb = QFontMetrics(big)
        total = float(sum(fb.horizontalAdvance(ch) for ch in self.NAME))
        x = w / 2.0 - total / 2.0
        base = box.bottom() - (14.0 if self.compact else 34.0)
        sweep = ((t * 0.45) % 1.6 - 0.3) * total + (w / 2.0 - total / 2.0)
        p.setFont(big)
        for i, ch in enumerate(self.NAME):
            adv = float(fb.horizontalAdvance(ch))
            cx = x + adv / 2.0
            wave = math.sin(t * 2.4 + i * 0.55) * (2.0 if self.compact else 4.0)
            near = 0.0
            if self.mouse is not None:
                dx = self.mouse.x() - cx
                near = math.exp(-(dx * dx) / (2.0 * 34.0 * 34.0))
            lift = near * (6.0 if self.compact else 11.0) + self.pulse * math.sin(i * 0.7 + t * 14.0) * 4.0
            sc = 1.0 + near * 0.35 + self.pulse * 0.2
            col = mix(pal.accent, pal.secondary, 0.5 + 0.5 * math.sin(t * 1.6 + i * 0.42))
            shine = math.exp(-((cx - sweep) / 36.0) ** 2)
            col = mix(col, QColor(255, 255, 255), clamp(shine * 0.85 + near * 0.25, 0.0, 1.0))
            p.save()
            p.translate(cx, base + wave - lift)
            p.scale(sc, sc)
            p.setPen(with_alpha(QColor(0, 0, 0), 70))
            p.drawText(QPointF(-adv / 2.0 + 1.2, 1.6), ch)
            p.setPen(col)
            p.drawText(QPointF(-adv / 2.0, 0), ch)
            p.restore()
            x += adv
        for sp in self.sparks:
            a = clamp(sp[4] / 0.9, 0.0, 1.0)
            c = (pal.accent, pal.secondary, QColor(255, 255, 255))[sp[5]]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(c, int(255 * a)))
            p.drawEllipse(QPointF(sp[0], sp[1]), 2.6 * a + 0.6, 2.6 * a + 0.6)
        p.end()
