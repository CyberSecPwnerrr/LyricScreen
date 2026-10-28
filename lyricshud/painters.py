import os
import time
import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QPixmap,
    QLinearGradient,
    QRadialGradient,
    QConicalGradient,
)

from lyricshud.images import ImageSrc, cover_fit, grain
from lyricshud.utils import clamp, mix, with_alpha
from lyricshud.winutil import set_blur


class MenuPaint:
    def menu_init(self):
        self.mw_pm = None
        self.mw_sig = None
        self.mw_src = None
        self.mw_path = None

    def menu_wall(self, w, h):
        path = self.cfg["menu_image"]
        if not path or not os.path.isfile(path):
            if self.mw_src is not None:
                self.mw_src.stop()
                self.mw_src = None
                self.mw_path = None
                self.mw_sig = None
                self.mw_pm = None
            return None
        blur = int(self.cfg["menu_blur"])
        if self.mw_path != path:
            if self.mw_src is not None:
                self.mw_src.stop()
            self.mw_src = ImageSrc(path, self.update)
            self.mw_path = path
        sig = (path, w, h, blur, self.mw_src.number())
        if sig != self.mw_sig:
            self.mw_sig = sig
            self.mw_pm = None
            fr = self.mw_src.frame()
            if not fr.isNull():
                self.mw_pm = cover_fit(fr, w, h, blur)
        return self.mw_pm

    def paint_menu(self, p, rect, rad, pal):
        cfg = self.cfg
        path = QPainterPath()
        path.addRoundedRect(rect, rad, rad)
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, with_alpha(mix(pal.bg, pal.surface, 0.25), 244 if rad > 0 else 255))
        wall = self.menu_wall(max(2, int(rect.width())), max(2, int(rect.height())))
        if wall is not None:
            p.setOpacity(cfg["menu_image_opacity"] / 100.0)
            p.drawPixmap(rect.toRect(), wall)
            p.setOpacity(1.0)
            p.fillRect(rect, QColor(0, 0, 0, int(2.2 * cfg["menu_dim"])))
        if cfg["menu_anim"] and cfg["optimize"] != "performance":
            t = time.monotonic()
            span = max(rect.width(), rect.height()) * 0.55
            for k, col in enumerate((pal.accent, pal.secondary)):
                cx = rect.center().x() + math.sin(t * 0.3 + k * 2.6) * rect.width() * 0.38
                cy = rect.center().y() + math.cos(t * 0.23 + k * 1.9) * rect.height() * 0.34
                rg = QRadialGradient(cx, cy, span)
                rg.setColorAt(0, with_alpha(col, 30))
                rg.setColorAt(1, with_alpha(col, 0))
                p.fillRect(rect, QBrush(rg))
        p.restore()
        if rad > 0:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.5), 90), 1.0))
            p.drawPath(path)


class CardPaint:
    def card_init(self):
        self.bd_pm = None
        self.bd_sig = None
        self.img_pm = None
        self.img_sig = None
        self.img_src = None
        self.img_path = None
        self.img_key = "bg_image"

    def blur_card(self, card, s=1.0):
        if self.isVisible():
            set_blur(self, bool(self.cfg["blur"]) and self.cfg["glass"] < 100, card, self.cfg["card_radius"] * s)

    def backdrop(self, card):
        img = self.state.cover
        if img is None:
            return None
        sig = (self.state.cover_id, int(card.width()), int(card.height()))
        if sig != self.bd_sig:
            tiny = img.scaled(
                8, 8, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            big = tiny.scaled(
                max(2, int(card.width() / 3)),
                max(2, int(card.height() / 3)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.bd_pm = QPixmap.fromImage(big)
            self.bd_sig = sig
        return self.bd_pm

    def image_backdrop(self, card):
        path = self.cfg[self.img_key]
        if not path or not os.path.isfile(path):
            if self.img_src is not None:
                self.img_src.stop()
                self.img_src = None
                self.img_path = None
                self.img_sig = None
                self.img_pm = None
            return None
        w = max(2, int(card.width()))
        h = max(2, int(card.height()))
        blur = int(self.cfg[self.img_key + "_blur"])
        if self.img_path != path:
            if self.img_src is not None:
                self.img_src.stop()
            self.img_src = ImageSrc(path, self.update)
            self.img_path = path
        sig = (path, w, h, blur, self.img_src.number())
        if sig != self.img_sig:
            self.img_sig = sig
            self.img_pm = None
            fr = self.img_src.frame()
            if not fr.isNull():
                self.img_pm = cover_fit(fr, w, h, blur)
        return self.img_pm

    def paint_card(self, p, card, pal):
        cfg = self.cfg
        rad = float(cfg["card_radius"])
        glass = cfg["glass"] / 100.0
        style = cfg["card_style"]
        ba = cfg["border_alpha"] / 100.0
        fr = cfg["frost"] / 100.0
        white = QColor(255, 255, 255)
        path = QPainterPath()
        path.addRoundedRect(card, rad, rad)
        sh = cfg["card_shadow"] / 100.0
        if sh > 0.01:
            outer = QPainterPath()
            outer.addRect(card.adjusted(-40, -40, 40, 40))
            p.save()
            p.setClipPath(outer.subtracted(path))
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(6, 0, -1):
                g = k * 1.8
                p.setBrush(QColor(0, 0, 0, int(clamp(sh * 22, 0, 255))))
                p.drawRoundedRect(card.adjusted(-g, -g + 4, g, g + 4), rad + g, rad + g)
            p.restore()
        if style == "flat":
            p.fillPath(path, with_alpha(pal.bg.lighter(110), int(255 * glass)))
        elif style == "frosted":
            base = mix(pal.bg, white, 0.2)
            g = QLinearGradient(card.topLeft(), card.bottomRight())
            g.setColorAt(0, with_alpha(mix(base, white, 0.3 * fr), int(205 * glass)))
            g.setColorAt(1, with_alpha(base, int(150 * glass)))
            p.fillPath(path, QBrush(g))
        elif style == "aurora":
            p.fillPath(path, with_alpha(pal.bg.darker(130), int(245 * glass)))
            t = time.monotonic()
            third = QColor.fromHsvF((max(0.0, pal.accent.hsvHueF()) + 0.33) % 1.0, 0.7, 1.0)
            span = max(card.width(), card.height()) * 0.6
            for k, col in enumerate((pal.accent, pal.secondary, third)):
                cx = card.center().x() + math.sin(t * 0.35 + k * 2.1) * card.width() * 0.35
                cy = card.center().y() + math.cos(t * 0.28 + k * 1.7) * card.height() * 0.3
                rg = QRadialGradient(cx, cy, span)
                rg.setColorAt(0, with_alpha(col, int(120 * glass)))
                rg.setColorAt(1, with_alpha(col, 0))
                p.fillPath(path, QBrush(rg))
        else:
            g = QLinearGradient(card.topLeft(), card.bottomRight())
            g.setColorAt(0, with_alpha(pal.bg.lighter(125), int(240 * glass)))
            g.setColorAt(1, with_alpha(pal.bg.darker(150), int(245 * glass)))
            p.fillPath(path, QBrush(g))
        bd = self.backdrop(card)
        if bd is not None and cfg["backdrop"] > 0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(p.opacity() * cfg["backdrop"] / 100.0)
            p.drawPixmap(card.toRect(), bd)
            p.restore()
        im = self.image_backdrop(card)
        if im is not None:
            p.save()
            p.setClipPath(path)
            p.setOpacity(p.opacity() * cfg[self.img_key + "_opacity"] / 100.0)
            p.drawPixmap(card.toRect(), im)
            p.restore()
        k = {"flat": 0.0, "frosted": 0.18, "aurora": 0.45}.get(style, 1.0)
        if im is not None:
            k *= 0.55
        if k > 0:
            shade = QLinearGradient(card.topLeft(), card.bottomLeft())
            shade.setColorAt(0, with_alpha(pal.bg, int(40 * k)))
            shade.setColorAt(0.55, with_alpha(pal.bg, int(150 * k)))
            shade.setColorAt(1, with_alpha(pal.bg.darker(160), int(215 * k)))
            p.fillPath(path, QBrush(shade))
        if style == "frosted" and fr > 0.01:
            p.save()
            p.setClipPath(path)
            top = QLinearGradient(card.topLeft(), QPointF(card.left(), card.top() + card.height() * 0.45))
            top.setColorAt(0, with_alpha(white, int(70 * fr)))
            top.setColorAt(1, with_alpha(white, 0))
            p.fillPath(path, QBrush(top))
            phase = (time.monotonic() * 0.07) % 1.8 - 0.4 if self.state.playing else 0.3
            sx = card.left() + card.width() * phase
            sheen = QLinearGradient(
                sx - card.width() * 0.2, card.top(), sx + card.width() * 0.2, card.top() + card.height() * 0.35
            )
            sheen.setColorAt(0.0, with_alpha(white, 0))
            sheen.setColorAt(0.5, with_alpha(white, int(34 * fr)))
            sheen.setColorAt(1.0, with_alpha(white, 0))
            p.fillPath(path, QBrush(sheen))
            p.setOpacity(p.opacity() * 0.07 * fr)
            p.fillPath(path, QBrush(grain()))
            p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        glow = cfg["card_glow"] / 100.0
        bw = float(cfg["border_width"])

        def al(v):
            return int(clamp(v * ba, 0, 255))

        if style == "frosted":
            edge = QLinearGradient(card.topLeft(), card.bottomRight())
            edge.setColorAt(0.0, with_alpha(white, al(200)))
            edge.setColorAt(0.5, with_alpha(white, al(55)))
            edge.setColorAt(1.0, with_alpha(white, al(110)))
            p.setPen(QPen(QBrush(edge), bw + 0.4))
            p.drawPath(path)
        if glow > 0.01:
            p.setPen(QPen(with_alpha(pal.accent, int(20 * glow)), 6))
            p.drawPath(path)
            ang = (time.monotonic() * 45.0) % 360.0 if self.state.playing else 40.0
            cg = QConicalGradient(card.center(), ang)
            cg.setColorAt(0.0, with_alpha(pal.accent, al(235 * glow)))
            cg.setColorAt(0.22, with_alpha(pal.secondary, al(215 * glow)))
            cg.setColorAt(0.5, with_alpha(pal.accent, al(30 * glow)))
            cg.setColorAt(0.78, with_alpha(pal.secondary, al(215 * glow)))
            cg.setColorAt(1.0, with_alpha(pal.accent, al(235 * glow)))
            p.setPen(QPen(QBrush(cg), bw + 0.6))
            p.drawPath(path)
        elif style != "frosted":
            p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.4), al(110)), bw))
            p.drawPath(path)
        p.setPen(QPen(with_alpha(white, int(clamp(28 * ba, 0, 255))), 1.0))
        p.drawRoundedRect(card.adjusted(1.5, 1.5, -1.5, -1.5), rad - 1.5, rad - 1.5)
