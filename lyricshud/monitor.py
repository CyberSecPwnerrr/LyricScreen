import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QBrush,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QGuiApplication,
)
from PyQt6.QtWidgets import QWidget

from lyricshud.painters import CardPaint
from lyricshud.styles import AA
from lyricshud.sysstats import SysStats
from lyricshud.utils import PERF, clamp, with_alpha


class Monitor(QWidget, CardPaint):
    MARGIN = 10

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.img_key = "monitor_bg_image"
        self.stats = SysStats()
        self.cpu_hist = [0.0] * 60
        self.cpu = 0.0
        self.ram = (0.0, 1.0, 0.0)
        self.fps = 0.0
        self.procs = []
        self.last_t = time.monotonic()
        self.last_paints = PERF["paints"]
        self.drag = None
        self.sc = 1.0
        self.apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.fit()
        self.restore_pos()

    def plan(self):
        c = self.cfg
        out = []
        if c["monitor_cpu"]:
            out.append(("cpu", 66.0))
        if c["monitor_ram"]:
            out.append(("ram", 38.0))
        if c["monitor_fps"]:
            out.append(("fps", 24.0))
        if c["monitor_render"]:
            out.append(("render", 24.0))
        if c["monitor_procs"]:
            out.append(("procs", 30.0 + 5 * 19.0))
        return out

    def fit(self):
        self.sc = self.cfg["monitor_scale"] / 100.0
        sc = self.sc
        M = self.MARGIN
        w = int(2 * M + 270 * sc)
        h = int(2 * M + (16 + 22 + sum(x[1] for x in self.plan())) * sc + 6 * sc)
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)
        self.timer.setInterval(int(self.cfg["monitor_interval"]))

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

    def tick(self):
        now = time.monotonic()
        dt = max(0.001, now - self.last_t)
        n = max(1, int(self.ctl.hud.isVisible()) + int(self.ctl.holo.isVisible()))
        self.fps = (PERF["paints"] - self.last_paints) / dt / n
        self.last_t = now
        self.last_paints = PERF["paints"]
        c = self.cfg
        if c["monitor_cpu"]:
            self.cpu = self.stats.cpu()
            self.cpu_hist.append(self.cpu)
            del self.cpu_hist[0]
        if c["monitor_ram"]:
            self.ram = self.stats.ram()
        if c["monitor_procs"]:
            self.procs = self.stats.procs(5)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.last_t = time.monotonic()
        self.last_paints = PERF["paints"]
        self.timer.start()
        self.tick()
        self.apply_blur()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.apply_blur()

    def save_pos(self):
        self.cfg["monitor_x"] = self.x()
        self.cfg["monitor_y"] = self.y()
        self.cfg.save()

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.top() + 200)
        self.save_pos()

    def restore_pos(self):
        x, y = self.cfg["monitor_x"], self.cfg["monitor_y"]
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

    def bar(self, p, pal, x0, x1, y, frac, h):
        track = QRectF(x0, y, x1 - x0, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(pal.text, 38))
        p.drawRoundedRect(track, h / 2.0, h / 2.0)
        fw = max(h, track.width() * clamp(frac, 0.0, 1.0))
        g = QLinearGradient(x0, 0, x1, 0)
        g.setColorAt(0, pal.accent)
        g.setColorAt(1, pal.secondary)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(x0, y, fw, h), h / 2.0, h / 2.0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        th = self.theme
        sc = self.sc
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setOpacity(self.cfg["monitor_opacity"] / 100.0)
        self.paint_card(p, card, pal)
        x0 = card.left() + 16 * sc
        x1 = card.right() - 16 * sc
        y = card.top() + 14 * sc
        ft = th.font(11 * sc, QFont.Weight.DemiBold, 3.0)
        p.setFont(ft)
        p.setPen(pal.accent)
        p.drawText(QPointF(x0, y + QFontMetrics(ft).ascent()), "SYSTEM")
        y += 22 * sc
        fl = th.font(12 * sc, QFont.Weight.Medium)
        fv = th.font(12 * sc, QFont.Weight.DemiBold)
        fml = QFontMetrics(fl)

        def row(label, value, ry):
            p.setFont(fl)
            p.setPen(with_alpha(pal.text, 170))
            p.drawText(QPointF(x0, ry + fml.ascent()), label)
            p.setFont(fv)
            p.setPen(pal.text)
            vw = QFontMetrics(fv).horizontalAdvance(value)
            p.drawText(QPointF(x1 - vw, ry + fml.ascent()), value)

        for kind, hh in self.plan():
            if kind == "cpu":
                row("CPU", f"{self.cpu:.0f}%", y)
                self.bar(p, pal, x0, x1, y + 20 * sc, self.cpu / 100.0, 5 * sc)
                gy0 = y + 32 * sc
                gh = 28 * sc
                path = QPainterPath()
                n = len(self.cpu_hist)
                path.moveTo(x0, gy0 + gh)
                for i, v in enumerate(self.cpu_hist):
                    path.lineTo(x0 + (x1 - x0) * i / (n - 1), gy0 + gh - gh * v / 100.0)
                path.lineTo(x1, gy0 + gh)
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pal.accent, 60))
                p.drawPath(path)
            elif kind == "ram":
                used, total, pct = self.ram
                row("Memory", f"{used / 1073741824.0:.1f} / {total / 1073741824.0:.1f} GB", y)
                self.bar(p, pal, x0, x1, y + 20 * sc, pct / 100.0, 5 * sc)
            elif kind == "fps":
                row("Overlay FPS", f"{self.fps:.0f}", y)
            elif kind == "render":
                row("Render time", f"{PERF['ms']:.1f} ms", y)
            elif kind == "procs":
                p.setFont(th.font(10 * sc, QFont.Weight.DemiBold, 2.0))
                p.setPen(with_alpha(pal.text, 130))
                p.drawText(QPointF(x0, y + 12 * sc), "TOP PROGRAMS")
                fs = th.font(11 * sc, QFont.Weight.Medium)
                fm = QFontMetrics(fs)
                p.setFont(fs)
                yy = y + 30 * sc
                if not self.procs:
                    p.setPen(with_alpha(pal.text, 130))
                    p.drawText(QPointF(x0, yy + fm.ascent()), "Installing psutil, restart the app" if self.stats.ps is None else "Measuring")
                for name, cpu, mem in self.procs:
                    p.setPen(pal.text)
                    right = f"{cpu:.0f}%  {mem / 1048576.0:.0f} MB"
                    rw = fm.horizontalAdvance(right)
                    p.drawText(QPointF(x0, yy + fm.ascent()), fm.elidedText(name, Qt.TextElideMode.ElideRight, int(x1 - x0 - rw - 10)))
                    p.setPen(with_alpha(pal.text, 170))
                    p.drawText(QPointF(x1 - rw, yy + fm.ascent()), right)
                    yy += 19 * sc
            y += hh * sc
