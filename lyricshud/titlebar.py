import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QLinearGradient
from PyQt6.QtWidgets import QWidget

from lyricshud.eqdraw import draw_eq, eq_step
from lyricshud.styles import AA
from lyricshud.utils import clamp, mix, with_alpha


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
        eq_step(self.levels, time.monotonic() - self.t0, st.playing, self.panel.ctl.volume.peak() if st.playing else None)
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
        if x1 - x0 < 50:
            return
        draw_eq(
            p,
            pal,
            self.levels,
            x0,
            x1,
            0.0,
            h,
            int(clamp(int(self.cfg["bar_eq_bars"]), 6, 40)),
            self.cfg["bar_eq_style"],
            self.cfg["bar_eq_color"],
        )

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
