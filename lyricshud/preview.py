import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QBrush, QFont, QFontMetrics, QLinearGradient, QTransform
from PyQt6.QtWidgets import QWidget

from lyricshud.effects import line_fx
from lyricshud.fonts import cover_thumb
from lyricshud.painters import CardPaint
from lyricshud.render import LineCache, cached_line, draw_karaoke
from lyricshud.styles import AA
from lyricshud.utils import clamp, ease, lyric_colors, lyric_style, mix, with_alpha


class Preview(QWidget, CardPaint):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.cache = LineCache(32)
        self.thumb = None
        self.thumb_sig = None
        self.setFixedHeight(108)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)

    def refresh(self):
        self.cache.clear()
        self.thumb_sig = None
        self.bd_sig = None
        self.img_sig = None
        self.update()

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        cfg = self.cfg
        st = self.state
        pal = st.pal_target
        W = float(self.width())
        H = float(self.height())
        now = time.monotonic()
        dpr = self.devicePixelRatioF()
        wall = QLinearGradient(0.0, 0.0, W, H)
        wall.setColorAt(0, mix(pal.bg, pal.accent, 0.35))
        wall.setColorAt(1, mix(pal.bg, pal.secondary, 0.35))
        p.fillRect(QRectF(0, 0, W, H), QBrush(wall))
        card = QRectF(14, 12, W - 28, H - 24)
        op = cfg["opacity"] / 100.0
        p.setOpacity(op)
        self.paint_card(p, card, pal)
        cs = 64.0
        sig = (st.cover_id, pal.accent.rgba(), st.cover is None)
        if sig != self.thumb_sig:
            self.thumb = cover_thumb(st, 64)
            self.thumb_sig = sig
        cr = QRectF(card.left() + 16, card.center().y() - cs / 2.0, cs, cs)
        p.drawPixmap(cr.topLeft(), self.thumb)
        x0 = cr.right() + 16.0
        x1 = card.right() - 16.0
        th = self.theme
        f = th.font(15, QFont.Weight.Bold)
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(pal.text)
        title = st.title if st.active else "Song title"
        p.drawText(
            QPointF(x0, card.top() + 14 + fm.ascent()),
            fm.elidedText(title, Qt.TextElideMode.ElideRight, int(x1 - x0)),
        )
        f = th.font(12, QFont.Weight.Medium)
        fm2 = QFontMetrics(f)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 170))
        artist = st.artist if st.active else "Artist name"
        p.drawText(
            QPointF(x0, card.top() + 14 + fm.height() + fm2.ascent()),
            fm2.elidedText(artist, Qt.TextElideMode.ElideRight, int(x1 - x0)),
        )
        phase = now % 3.8
        enter = ease(phase / 0.6)
        eo = clamp((phase - 3.1) / 0.7, 0.0, 1.0)
        alpha = enter * (1.0 - ease(eo))
        prog = clamp((phase - 0.35) / 2.4, 0.0, 1.0)
        size = clamp(cfg["font_size"] * 0.75, 14.0, 30.0)
        fill, fill2, gcol = lyric_colors(cfg, pal)
        sty = lyric_style(cfg)
        glow = cfg["glow"] / 100.0 * 0.6
        karaoke = bool(cfg["karaoke"])
        text = "Feel the rhythm tonight"
        maxw = x1 - x0
        bright = cached_line(self.cache, th, text, size, fill, gcol, glow, maxw, dpr, False, "c", sty, fill2)
        dim = (
            cached_line(self.cache, th, text, size, fill, gcol, 0.0, maxw, dpr, False, "c", sty, fill2)
            if karaoke
            else None
        )
        ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, 0, now, 0, clamp(phase / 3.8, 0.0, 1.0))
        tr = QTransform()
        tr.translate((x0 + x1) / 2.0 + ox * 0.6, card.bottom() - 30.0 + oy * 0.6)
        tr.rotate(rx, Qt.Axis.XAxis)
        tr.rotate(rz)
        tr.scale(sc * sx, sc)
        p.save()
        p.setTransform(tr, True)
        draw_karaoke(p, dim, bright, prog, alpha * op * cfg["lyric_opacity"] / 100.0, karaoke, 1.0, cfg["dim_level"] / 100.0)
        p.restore()
