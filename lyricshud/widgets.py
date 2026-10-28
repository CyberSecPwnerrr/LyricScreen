from PyQt6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QPointF,
    QEvent,
    QPropertyAnimation,
    QVariantAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import QPainter, QPen, QBrush, QLinearGradient, QPolygonF
from PyQt6.QtWidgets import QWidget, QMenu, QVBoxLayout, QPushButton, QCheckBox, QListWidget, QListView

from lyricshud.painters import MenuPaint
from lyricshud.styles import AA
from lyricshud.utils import clamp, mix, with_alpha


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


MENU_STYLES = {"standard": 176, "compact": 140, "minimal": 64, "modern": 176, "fancy": 212}
MENU_STYLE_ITEMS = [
    ("Standard", "standard"),
    ("Compact", "compact"),
    ("Minimal (icons only)", "minimal"),
    ("Modern (top tabs)", "modern"),
    ("Fancy", "fancy"),
]
PAGE_ICONS = {
    "Themes": "◐",
    "Colors": "◉",
    "Card": "▭",
    "Typography": "Ⓣ",
    "Lyrics": "♪",
    "Animations": "✦",
    "Overlay": "◫",
    "Widgets": "▦",
    "Menu": "☰",
    "Player": "▶",
    "Config": "⚙",
    "About": "ⓘ",
}


class NavList(QListWidget):
    def __init__(self, state, style="standard"):
        super().__init__()
        self.state = state
        self.style_name = style
        self.sel = None
        self.hover_row = -1
        self.hv = {}
        self.setMouseTracking(True)
        self.setProperty("mstyle", style)
        if style == "modern":
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListView.ResizeMode.Adjust)
            self.setSpacing(3)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setFixedHeight(84)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.step)

    def fit_height(self):
        if not self.count():
            return
        self.doItemsLayout()
        h = max(self.visualItemRect(self.item(i)).bottom() for i in range(self.count())) + 16
        if h > 30 and h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.style_name == "modern":
            QTimer.singleShot(0, self.fit_height)

    def showEvent(self, e):
        it = self.currentItem()
        if it is not None:
            self.sel = QRectF(self.visualItemRect(it))
        self.timer.start()
        super().showEvent(e)
        if self.style_name == "modern":
            QTimer.singleShot(0, self.fit_height)

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
            t = QRectF(self.visualItemRect(it))
            if self.sel is None:
                self.sel = t
                changed = True
            else:
                s = self.sel
                d = max(abs(t.x() - s.x()), abs(t.y() - s.y()), abs(t.width() - s.width()), abs(t.height() - s.height()))
                if d > 0.3:
                    k = 0.28
                    self.sel = QRectF(
                        s.x() + (t.x() - s.x()) * k,
                        s.y() + (t.y() - s.y()) * k,
                        s.width() + (t.width() - s.width()) * k,
                        s.height() + (t.height() - s.height()) * k,
                    )
                    changed = True
                elif d:
                    self.sel = t
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

    def inset(self, rect):
        if self.style_name == "modern":
            return rect.adjusted(1, 1, -1, -1)
        return rect.adjusted(4, 2, -4, -2)

    def radius(self, rect):
        if self.style_name == "modern":
            return rect.height() / 2.0
        return {"compact": 7.0, "minimal": 12.0, "fancy": 15.0}.get(self.style_name, 9.0)

    def paintEvent(self, e):
        if self.count():
            pal = self.state.pal_target
            p = QPainter(self.viewport())
            p.setRenderHints(AA)
            p.setPen(Qt.PenStyle.NoPen)
            for r, v in self.hv.items():
                if v > 0.01 and r != self.currentRow() and r < self.count():
                    rect = self.inset(QRectF(self.visualItemRect(self.item(r))))
                    p.setBrush(with_alpha(pal.text, int(24 * v)))
                    p.drawRoundedRect(rect, self.radius(rect), self.radius(rect))
            if self.currentItem() is not None and self.sel is not None:
                rect = self.inset(self.sel)
                rad = self.radius(rect)
                if self.style_name == "fancy":
                    p.setBrush(with_alpha(pal.accent, 40))
                    p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), rad + 3, rad + 3)
                g = QLinearGradient(rect.topLeft(), rect.topRight())
                g.setColorAt(0, with_alpha(pal.accent, 150 if self.style_name == "modern" else 105))
                g.setColorAt(1, with_alpha(pal.secondary, 60 if self.style_name == "modern" else 22))
                p.setBrush(QBrush(g))
                p.drawRoundedRect(rect, rad, rad)
                if self.style_name != "modern":
                    p.setBrush(pal.accent)
                    p.drawRoundedRect(
                        QRectF(rect.left() + 5, rect.top() + rect.height() * 0.25, 3.0, rect.height() * 0.5), 1.5, 1.5
                    )
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
