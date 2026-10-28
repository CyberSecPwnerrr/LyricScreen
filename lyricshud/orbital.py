import time
import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QFont,
    QPixmap,
    QLinearGradient,
    QRadialGradient,
    QIcon,
    QGuiApplication,
    QCursor,
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

from lyricshud.fonts import dark_titlebar
from lyricshud.panel import Panel
from lyricshud.styles import AA
from lyricshud.theme import apply_qss
from lyricshud.themes import ENTER_ITEMS
from lyricshud.utils import clamp, mix, with_alpha


ORBIT_GLYPHS = {"settings": "⚙", "quick": "✦", "mode": "▣", "hide": "◌", "lock": "◎"}


def orbit_icon(p, kind, c, s, col, th, playing):
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    x = c.x()
    y = c.y()
    if kind == "play":
        if playing:
            p.drawRoundedRect(QRectF(x - s * 0.55, y - s * 0.7, s * 0.38, s * 1.4), 2, 2)
            p.drawRoundedRect(QRectF(x + s * 0.17, y - s * 0.7, s * 0.38, s * 1.4), 2, 2)
        else:
            path = QPainterPath()
            path.moveTo(x - s * 0.45, y - s * 0.75)
            path.lineTo(x + s * 0.75, y)
            path.lineTo(x - s * 0.45, y + s * 0.75)
            path.closeSubpath()
            p.drawPath(path)
    elif kind == "next" or kind == "prev":
        d = 1.0 if kind == "next" else -1.0
        path = QPainterPath()
        path.moveTo(x - d * s * 0.65, y - s * 0.65)
        path.lineTo(x + d * s * 0.35, y)
        path.lineTo(x - d * s * 0.65, y + s * 0.65)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRoundedRect(QRectF(x + d * s * 0.45 - s * 0.12, y - s * 0.65, s * 0.24, s * 1.3), 1.5, 1.5)
    else:
        p.setFont(th.font(s * 1.6, QFont.Weight.Bold))
        p.setPen(col)
        p.drawText(QRectF(x - s * 1.3, y - s * 1.3, s * 2.6, s * 2.6), Qt.AlignmentFlag.AlignCenter, ORBIT_GLYPHS.get(kind, "•"))
    p.restore()


class OrbitalMenu(QWidget):
    SIZE = 360

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.state = ctl.state
        self.items = []
        self.hover = -1
        self.t0 = 0.0
        self.sc = 1.0
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def build(self):
        st = self.state
        ctl = self.ctl
        self.items = [
            ("play", "Pause" if st.playing else "Play", st.toggle_play),
            ("next", "Next track", st.skip_next),
            ("mode", "Display mode", ctl.cycle_mode),
            ("settings", "Settings", ctl.open_settings),
            ("quick", "Quick customize", ctl.open_quick),
            ("hide", "Show / hide", ctl.toggle_visible),
            ("lock", "Unlock card" if self.cfg["click_through"] else "Lock card", ctl.toggle_lock),
            ("prev", "Previous track", st.skip_prev),
        ]

    def pop(self):
        pos = QCursor.pos()
        self.build()
        self.sc = clamp(int(self.cfg["orbit_scale"]), 60, 160) / 100.0
        s = int(self.SIZE * self.sc)
        self.setFixedSize(s, s)
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        self.move(
            int(clamp(pos.x() - s / 2, g.left(), max(g.left(), g.right() - s))),
            int(clamp(pos.y() - s / 2, g.top(), max(g.top(), g.bottom() - s))),
        )
        self.hover = -1
        self.t0 = time.monotonic()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.cfg["menu_anim"]:
            self.timer.start()

    def grow(self):
        if not self.cfg["menu_anim"]:
            return 1.0
        return 1.0 - (1.0 - clamp((time.monotonic() - self.t0) / 0.3, 0.0, 1.0)) ** 3

    def tick(self):
        self.update()
        if self.grow() >= 1.0:
            self.timer.stop()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def spot(self, k, radius):
        a = -math.pi / 2.0 + math.tau * k / max(1, len(self.items))
        c = self.width() / 2.0
        return QPointF(c + math.cos(a) * radius, c + math.sin(a) * radius)

    def hit(self, pos):
        r = 118.0 * self.sc
        for k in range(len(self.items)):
            c = self.spot(k, r)
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= 34.0 * self.sc:
                return k
        mid = self.width() / 2.0
        if math.hypot(pos.x() - mid, pos.y() - mid) <= 50.0 * self.sc:
            return -2
        return -1

    def mouseMoveEvent(self, e):
        h = self.hit(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def mousePressEvent(self, e):
        h = self.hit(e.position()) if e.button() == Qt.MouseButton.LeftButton else -1
        self.close()
        if h >= 0:
            QTimer.singleShot(0, self.items[h][2])
        elif h == -2:
            QTimer.singleShot(0, self.state.toggle_play)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        st = self.state
        pal = st.pal_target
        th = self.ctl.theme
        g = self.grow()
        sc = self.sc
        c = QPointF(self.width() / 2.0, self.height() / 2.0)
        ring = 118.0 * sc * (0.45 + 0.55 * g)
        p.setOpacity(g)
        out = ring + 64.0 * sc
        disc = QRadialGradient(c, out)
        disc.setColorAt(0.0, with_alpha(mix(pal.bg, pal.surface, 0.5), 238))
        disc.setColorAt(0.78, with_alpha(pal.bg, 205))
        disc.setColorAt(1.0, with_alpha(pal.bg, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(disc))
        p.drawEllipse(c, out, out)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(pal.accent, 80), 1.5))
        p.drawEllipse(c, ring, ring)
        n = len(self.items)
        for k, (kind, label, cb) in enumerate(self.items):
            pt = self.spot(k, ring)
            hv = k == self.hover
            rad = (30.0 + (5.0 if hv else 0.0)) * sc * (0.6 + 0.4 * g)
            if hv:
                grad = QLinearGradient(pt.x() - rad, pt.y() - rad, pt.x() + rad, pt.y() + rad)
                grad.setColorAt(0.0, pal.accent)
                grad.setColorAt(1.0, pal.secondary)
                p.setBrush(QBrush(grad))
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(with_alpha(pal.surface, 228))
                p.setPen(QPen(with_alpha(pal.accent, 120), 1.2))
            p.drawEllipse(pt, rad, rad)
            orbit_icon(p, kind, pt, rad * 0.5, pal.bg if hv else pal.text, th, st.playing)
        hub = 50.0 * sc * (0.5 + 0.5 * g)
        if self.hover == -2:
            hg = QLinearGradient(c.x() - hub, c.y() - hub, c.x() + hub, c.y() + hub)
            hg.setColorAt(0.0, pal.accent)
            hg.setColorAt(1.0, pal.secondary)
            p.setBrush(QBrush(hg))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(with_alpha(pal.surface, 235))
            p.setPen(QPen(with_alpha(pal.accent, 150), 1.5))
        p.drawEllipse(c, hub, hub)
        if 0 <= self.hover < n:
            text = self.items[self.hover][1]
        elif self.hover == -2:
            text = "Pause" if st.playing else "Play"
        else:
            text = st.title if st.active and st.title else "Lyrics"
        p.setFont(th.font(max(9.0, 11.0 * sc), QFont.Weight.Bold))
        p.setPen(pal.bg if self.hover == -2 else pal.text)
        box = QRectF(c.x() - hub * 0.82, c.y() - hub * 0.62, hub * 1.64, hub * 1.24)
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), text)
        p.end()


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
