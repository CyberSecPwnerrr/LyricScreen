import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import QPainter, QFont, QFontMetrics, QGuiApplication
from PyQt6.QtWidgets import QWidget

from lyricshud.eqdraw import draw_eq, eq_step
from lyricshud.painters import CardPaint
from lyricshud.styles import AA
from lyricshud.system import fmt_uptime
from lyricshud.utils import clamp, with_alpha


class FloatWidget(QWidget, CardPaint):
    MARGIN = 10
    PREFIX = ""

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.img_key = self.PREFIX + "_bg_image"
        self.drag = None
        self.sc = 1.0
        self.apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def interval(self):
        return 1000

    def corner(self, g):
        return g.left() + 24, g.top() + 24

    def apply_blur(self):
        m = self.MARGIN
        self.blur_card(QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m))

    def apply_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        self.top_applied = bool(self.cfg["always_on_top"])
        if self.top_applied:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was = self.isVisible()
        self.setWindowFlags(flags)
        if was:
            self.show()

    def refresh(self):
        if self.top_applied != bool(self.cfg["always_on_top"]):
            self.apply_flags()
        self.bd_sig = None
        self.img_sig = None
        self.fit()
        self.apply_blur()
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start(self.interval())
        self.tick()
        self.apply_blur()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_blur()

    def save_pos(self):
        self.cfg[self.PREFIX + "_x"] = self.x()
        self.cfg[self.PREFIX + "_y"] = self.y()
        self.cfg.save()

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        x, y = self.corner(g)
        self.move(int(x), int(y))
        self.save_pos()

    def restore_pos(self):
        x, y = self.cfg[self.PREFIX + "_x"], self.cfg[self.PREFIX + "_y"]
        if x is not None and y is not None and any(
            s.geometry().contains(QPoint(int(x) + 20, int(y) + 20)) for s in QGuiApplication.screens()
        ):
            self.move(int(x), int(y))
        else:
            self.reset_pos()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self.ctl.menu.exec(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.drag = None
            self.save_pos()


class Equalizer(FloatWidget):
    PREFIX = "eq"

    def __init__(self, ctl):
        super().__init__(ctl)
        self.levels = [0.05] * 40
        self.t0 = time.monotonic()
        self.fit()
        self.restore_pos()

    def interval(self):
        return 50 if self.cfg["optimize"] == "performance" else 33

    def corner(self, g):
        return g.left() + 24, g.bottom() - self.height() - 24

    def fit(self):
        self.sc = self.cfg["eq_scale"] / 100.0
        M = self.MARGIN
        w = int(2 * M + 260 * self.sc)
        h = int(2 * M + 96 * self.sc)
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)
        self.timer.setInterval(self.interval())

    def tick(self):
        st = self.state
        eq_step(self.levels, time.monotonic() - self.t0, st.playing, self.ctl.volume.peak() if st.playing else None)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        sc = self.sc
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setOpacity(self.cfg["eq_opacity"] / 100.0)
        self.paint_card(p, card, pal)
        pad = 16.0 * sc
        draw_eq(
            p,
            pal,
            self.levels,
            card.left() + pad,
            card.right() - pad,
            card.top() + 10.0 * sc,
            card.height() - 20.0 * sc,
            int(clamp(int(self.cfg["eq_bars"]), 6, 40)),
            self.cfg["eq_style"],
            self.cfg["eq_color"],
        )
        p.end()


class Stats(FloatWidget):
    PREFIX = "stats"

    def __init__(self, ctl):
        super().__init__(ctl)
        self.fit()
        self.restore_pos()

    def rows(self):
        c = self.cfg
        st = self.state
        out = []
        if c["stats_songs"]:
            if c["stats_scope"] == "total":
                out.append(("Songs played (all time)", str(st.songs_total)))
            else:
                out.append(("Songs played", str(st.songs)))
        if c["stats_uptime"]:
            out.append(("App running for", fmt_uptime(time.monotonic() - st.started)))
        return out

    def fit(self):
        self.sc = self.cfg["stats_scale"] / 100.0
        sc = self.sc
        M = self.MARGIN
        w = int(2 * M + 250 * sc)
        h = int(2 * M + (16 + 22 + max(1, len(self.rows())) * 24 + 6) * sc)
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)
        self.timer.setInterval(self.interval())

    def tick(self):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        th = self.theme
        sc = self.sc
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setOpacity(self.cfg["stats_opacity"] / 100.0)
        self.paint_card(p, card, pal)
        x0 = card.left() + 16 * sc
        x1 = card.right() - 16 * sc
        y = card.top() + 14 * sc
        ft = th.font(11 * sc, QFont.Weight.DemiBold, 3.0)
        p.setFont(ft)
        p.setPen(pal.accent)
        p.drawText(QPointF(x0, y + QFontMetrics(ft).ascent()), "STATS")
        y += 22 * sc
        fl = th.font(12 * sc, QFont.Weight.Medium)
        fv = th.font(12 * sc, QFont.Weight.DemiBold)
        fml = QFontMetrics(fl)
        rows = self.rows()
        if not rows:
            p.setFont(fl)
            p.setPen(with_alpha(pal.text, 130))
            p.drawText(QPointF(x0, y + fml.ascent()), "Nothing selected")
        for label, value in rows:
            p.setFont(fl)
            p.setPen(with_alpha(pal.text, 170))
            p.drawText(QPointF(x0, y + fml.ascent()), label)
            p.setFont(fv)
            p.setPen(pal.text)
            vw = QFontMetrics(fv).horizontalAdvance(value)
            p.drawText(QPointF(x1 - vw, y + fml.ascent()), value)
            y += 24 * sc
        p.end()
