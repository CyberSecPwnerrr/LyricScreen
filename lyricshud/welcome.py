import os
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QConicalGradient,
    QGuiApplication,
)
from PyQt6.QtWidgets import QWidget

from lyricshud.effects import ease_back
from lyricshud.images import ImageSrc, cover_fit, crop_frame
from lyricshud.painters import CardPaint
from lyricshud.styles import AA
from lyricshud.utils import clamp, ease, with_alpha
from lyricshud.winutil import desktop_names


class Welcome(QWidget, CardPaint):
    SPAN = 5.2

    @property
    def H(self):
        return max(190, self.pic_px() + 76)

    def pic_px(self):
        return int(clamp(int(self.cfg["welcome_pic_size"]), 48, 140))

    def pic_rect(self):
        try:
            r = tuple(float(v) for v in self.cfg["welcome_pic_rect"])
        except (TypeError, ValueError):
            r = ()
        return r if len(r) == 4 else (0.0, 0.0, 1.0, 1.0)

    def free_bg(self):
        if self.img_src is not None:
            self.img_src.stop()
            self.img_src = None
        self.img_path = None
        self.img_sig = None
        self.img_pm = None

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.t0 = 0.0
        self.first = False
        self.below = False
        self.pic_src = None
        self.pic_pm = None
        self.pic_sig = None
        self.name, self.pc = desktop_names()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def anchor(self):
        hud = self.ctl.hud
        screen = QGuiApplication.primaryScreen()
        if hud.isVisible():
            m = hud.MARGIN * hud.scale
            gx = hud.x() + m
            gy = hud.y() + m
            gw = hud.width() - 2 * m
            gh = hud.height() - 2 * m
            screen = QGuiApplication.screenAt(hud.frameGeometry().center()) or screen
            g = screen.availableGeometry()
            y = int(gy) - 8 - self.H + 14
            self.below = y < g.top()
            if self.below:
                y = int(gy + gh) + 8 - 14
            return QRect(int(gx) - 14, y, int(gw) + 28, self.H)
        g = screen.availableGeometry()
        self.below = False
        return QRect(g.x() + (g.width() - 560) // 2, g.y() + int(g.height() * 0.16), 560, self.H)

    def place(self):
        geo = self.anchor()
        if geo != self.geometry():
            self.setGeometry(geo)
            self.blur_card(QRectF(14, 14, geo.width() - 28, geo.height() - 28))

    def play(self, first):
        self.first = first
        self.SPAN = float(self.cfg["welcome_duration"])
        self.load_pic()
        self.t0 = time.monotonic()
        self.setGeometry(self.anchor())
        self.show()
        self.blur_card(QRectF(14, 14, self.width() - 28, self.height() - 28))
        self.timer.start()

    def tick(self):
        if time.monotonic() - self.t0 >= self.SPAN:
            self.timer.stop()
            self.hide()
            self.free_pic()
            self.free_bg()
            return
        self.place()
        self.update()

    def load_pic(self):
        self.free_pic()
        path = self.cfg["welcome_pic"]
        if path and os.path.isfile(path):
            src = ImageSrc(path, lambda: None)
            if not src.img.isNull() or src.frames:
                self.pic_src = src
            else:
                src.stop()

    def free_pic(self):
        self.pic_pm = None
        self.pic_sig = None
        if self.pic_src is not None:
            self.pic_src.stop()
            self.pic_src = None

    def paintEvent(self, e):
        age = time.monotonic() - self.t0
        out = ease(clamp((age - (self.SPAN - 0.9)) / 0.9, 0.0, 1.0))
        a_in = ease(age / 0.7)
        a = a_in * (1.0 - out)
        if a <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHints(AA)
        th = self.theme
        pal = self.state.pal_target
        white = QColor(255, 255, 255)
        nm = self.cfg["welcome_name"].strip() or self.name
        card = QRectF(14, 14, self.width() - 28, self.height() - 28)
        d = -1.0 if self.below else 1.0
        p.translate(0.0, d * ((1.0 - a_in) * 18.0 - out * 10.0))
        p.setOpacity(a)
        self.img_key = "welcome_bg_image" if self.cfg["welcome_bg_image"] else "bg_image"
        self.paint_card(p, card, pal)
        rad = float(self.cfg["card_radius"])
        clip = QPainterPath()
        clip.addRoundedRect(card, rad, rad)
        p.save()
        p.setClipPath(clip)
        if 0.35 < age < 1.85:
            sx = card.left() - 120.0 + (card.width() + 240.0) * ease((age - 0.35) / 1.5)
            sg = QLinearGradient(sx - 90.0, card.top(), sx + 90.0, card.top() + 40.0)
            sg.setColorAt(0.0, with_alpha(white, 0))
            sg.setColorAt(0.5, with_alpha(white, 38))
            sg.setColorAt(1.0, with_alpha(white, 0))
            p.fillPath(clip, QBrush(sg))
        bar = QRectF(card.left() + 24.0, card.bottom() - 14.0, card.width() - 48.0, 2.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(pal.text, 40))
        p.drawRoundedRect(bar, 1.0, 1.0)
        left = bar.width() * clamp(1.0 - age / self.SPAN, 0.0, 1.0)
        bg = QLinearGradient(bar.left(), 0.0, bar.right(), 0.0)
        bg.setColorAt(0, pal.accent)
        bg.setColorAt(1, pal.secondary)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), left, bar.height()), 1.0, 1.0)
        p.restore()
        ps = float(self.pic_px())
        ac = QRectF(card.left() + 30.0, card.center().y() - ps / 2.0, ps, ps)
        pop = ease_back(age / 0.8)
        p.save()
        p.translate(ac.center())
        p.scale(pop, pop)
        p.translate(-ac.center().x(), -ac.center().y())
        cg = QConicalGradient(ac.center(), (age * 110.0) % 360.0)
        cg.setColorAt(0.0, pal.accent)
        cg.setColorAt(0.5, pal.secondary)
        cg.setColorAt(1.0, pal.accent)
        round_shape = self.cfg["welcome_pic_shape"] == "rounded"
        corner = ac.width() * 0.26
        if self.cfg["welcome_ring"]:
            p.setPen(QPen(QBrush(cg), 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if round_shape:
                p.drawRoundedRect(ac, corner, corner)
            else:
                p.drawEllipse(ac)
            inner = ac.adjusted(7, 7, -7, -7)
        else:
            inner = ac.adjusted(2, 2, -2, -2)
        ipath = QPainterPath()
        if round_shape:
            ipath.addRoundedRect(inner, corner * 0.8, corner * 0.8)
        else:
            ipath.addEllipse(inner)
        pic = self.pic_src.frame() if self.pic_src is not None else None
        if pic is not None and not pic.isNull():
            dpr = self.devicePixelRatioF()
            px = max(2, int(inner.width() * dpr))
            rect = self.pic_rect()
            sig = (self.pic_src.number(), px, rect)
            if self.pic_pm is None or sig != self.pic_sig:
                self.pic_pm = cover_fit(crop_frame(pic, rect), px, px, 0)
                self.pic_sig = sig
            p.save()
            p.setClipPath(ipath)
            p.drawPixmap(inner, self.pic_pm, QRectF(self.pic_pm.rect()))
            p.restore()
        else:
            fg = QLinearGradient(inner.topLeft(), inner.bottomRight())
            fg.setColorAt(0, pal.accent)
            fg.setColorAt(1, pal.secondary)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fg))
            p.drawPath(ipath)
            p.setFont(th.font(ps * 0.41, QFont.Weight.Bold))
            p.setPen(pal.bg)
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter, (nm[:1] or "?").upper())
        p.restore()
        x0 = ac.right() + 24.0
        tw = card.right() - 26.0 - x0
        left_mid = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        y = card.center().y() - 52.0

        def rv(delay):
            return ease((age - delay) / 0.5)

        f = th.font(12, QFont.Weight.DemiBold, 5.0)
        fm = QFontMetrics(f)
        r = rv(0.2)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(pal.accent)
        p.drawText(QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()), left_mid, (self.cfg["welcome_title"] if self.first else self.cfg["welcome_title_back"]))
        y += fm.height() + 4.0
        f = th.font(float(self.cfg["welcome_name_size"]), QFont.Weight.Bold)
        fm = QFontMetrics(f)
        r = rv(0.35)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(pal.text)
        p.drawText(
            QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()),
            left_mid,
            fm.elidedText(nm, Qt.TextElideMode.ElideRight, int(tw)),
        )
        y += fm.height() + 5.0
        lw = min(tw, 150.0) * ease((age - 0.5) / 0.8)
        lg = QLinearGradient(x0, 0.0, x0 + lw + 1.0, 0.0)
        lg.setColorAt(0, pal.accent)
        lg.setColorAt(1, pal.secondary)
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(lg))
        p.drawRoundedRect(QRectF(x0, y, lw, 3.0), 1.5, 1.5)
        y += 13.0
        f = th.font(13, QFont.Weight.Medium)
        fm = QFontMetrics(f)
        r = rv(0.65)
        hour = datetime.now().hour
        greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
        sub = self.cfg["welcome_sub"].strip()
        if sub:
            info = sub.replace("{name}", nm).replace("{pc}", self.pc)
        else:
            items = []
            if self.cfg["welcome_greeting"]:
                items.append(greet)
            if self.cfg["welcome_pc"]:
                items.append(self.pc)
            if self.cfg["welcome_date"]:
                items.append(datetime.now().strftime("%A, %d %B"))
            info = "  \u00b7  ".join(x for x in items if x)
        p.setOpacity(a * r)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 175))
        p.drawText(
            QRectF(x0 + (1.0 - r) * 14.0, y, tw, fm.height()),
            left_mid,
            fm.elidedText(info, Qt.TextElideMode.ElideRight, int(tw)),
        )
