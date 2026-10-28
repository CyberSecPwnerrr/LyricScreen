import os
import time
import math
import random

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QPixmap,
    QImage,
    QRadialGradient,
    QTransform,
    QGuiApplication,
)
from PyQt6.QtWidgets import QWidget

from lyricshud.defaults import POS, POS_KEYS
from lyricshud.desktop import (
    build_wallpaper,
    desktop_attach,
    desktop_place,
    wallpaper_path,
    wallpaper_style,
)
from lyricshud.effects import line_fx
from lyricshud.render import LineCache, cached_line, draw_karaoke
from lyricshud.styles import AA, BLEND
from lyricshud.themes import RAND_SALT
from lyricshud.utils import (
    clamp,
    ease,
    eff_fps,
    lyric_colors,
    lyric_style,
    timed,
    tune_timer,
    with_alpha,
)


class Holo(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.cache = LineCache(160)
        self.fade = 0.0
        self.last = time.monotonic()
        self.t0 = self.last
        self.dots = {}
        self.assign = {}
        self.last_pos = None
        self.next_glitch = self.last + 5.0
        self.wall = self.cfg["layer"] == "wall"
        self.attached = False
        self.host = None
        self.org = QPoint(0, 0)
        self.wp_img = None
        self.wp_src = None
        self.wp_next = 0.0
        self.wp_pm = None
        self.wp_sig = None
        self.glitch_until = 0.0
        self.dirty = True
        self.build_window()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.set_fps()
        self.state.track_changed.connect(self.on_track)
        self.state.lyrics_changed.connect(self.on_track)

    def on_track(self):
        RAND_SALT[0] = random.randrange(1 << 30)
        self.assign.clear()
        self.last_pos = None
        self.dirty = True

    def place(self):
        screens = QGuiApplication.screens()
        i = int(clamp(int(self.cfg["holo_screen"]), 0, len(screens) - 1))
        g = screens[i].geometry().adjusted(0, 0, -1, -1)
        self.org = g.topLeft()
        if self.wall and self.attached:
            self.move_native()
        elif self.geometry() != g:
            self.setGeometry(g)

    def set_fps(self):
        self.base_ms = int(1000 / eff_fps(self.cfg))
        self.timer.setInterval(self.base_ms)

    def refresh(self):
        self.apply_layer()
        self.cache.clear()
        self.dots.clear()
        self.wp_pm = None
        self.wp_src = None
        self.wp_next = 0.0
        self.set_fps()
        if self.isVisible():
            self.place()
        self.dirty = True
        self.update()

    def showEvent(self, e):
        self.last = time.monotonic()
        self.timer.start()
        super().showEvent(e)
        if self.wall:
            QTimer.singleShot(0, self.attach_wall)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        tune_timer(self)
        st = self.state
        animate = st.step_palette()
        if self.wall and self.attached and self.wall_poll(now):
            animate = True
        tf = 1.0 if st.active else 0.0
        if self.fade != tf:
            df = tf - self.fade
            if abs(df) > 0.005:
                self.fade += df * (1 - math.exp(-dt * 3.5))
            else:
                self.fade = tf
            animate = True
        if now > self.next_glitch:
            self.glitch_until = now + 0.14
            self.next_glitch = now + random.uniform(4.0, 10.0)
        if self.fade > 0.01 and st.playing and st.lyrics is not None and st.active_lines():
            animate = True
        if now - st.track_started < float(self.cfg["toast_secs"]) and st.active and self.cfg["show_toast"]:
            animate = True
        if animate or self.dirty:
            self.dirty = False
            self.update()

    def dot(self, color):
        key = color.rgba()
        d = self.dots.get(key)
        if d is None:
            d = QPixmap(48, 48)
            d.fill(Qt.GlobalColor.transparent)
            q = QPainter(d)
            q.setRenderHints(AA)
            g = QRadialGradient(24, 24, 24)
            g.setColorAt(0, with_alpha(color, 255))
            g.setColorAt(0.25, with_alpha(color, 70))
            g.setColorAt(1, with_alpha(color, 0))
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QBrush(g))
            q.drawEllipse(0, 0, 48, 48)
            q.end()
            self.dots[key] = d
        return d

    def paint_toast(self, p, W, H, pal):
        st = self.state
        if not st.active or not self.cfg["show_toast"]:
            return
        age = time.monotonic() - st.track_started
        span = max(2.0, float(self.cfg["toast_secs"]))
        if age > span:
            return
        a = ease(age / 0.6) * (1.0 - ease((age - (span - 1.2)) / 1.1))
        if a <= 0.01:
            return
        f = self.theme.font(15, QFont.Weight.DemiBold, 4.0)
        fm = QFontMetrics(f)
        label = fm.elidedText(f"{st.title}  //  {st.artist}".upper(), Qt.TextElideMode.ElideRight, int(W * 0.6))
        ty = H * 0.075 + (1.0 - ease(age / 0.6)) * -14
        p.setFont(f)
        p.setPen(pal.accent.lighter(130))
        p.setOpacity(a * 0.95)
        p.drawText(QPointF((W - fm.horizontalAdvance(label)) / 2.0, ty), label)
        bw = 320.0
        bx = (W - bw) / 2.0
        p.setPen(QPen(with_alpha(pal.accent, 70), 2))
        p.setOpacity(a)
        p.drawLine(QPointF(bx, ty + 14), QPointF(bx + bw, ty + 14))
        if st.dur > 0:
            frac = clamp(st.position() / st.dur, 0.0, 1.0)
            p.setPen(QPen(pal.accent, 2))
            p.drawLine(QPointF(bx, ty + 14), QPointF(bx + bw * frac, ty + 14))

    def pos_for(self, i, current):
        mode = self.cfg["placement"]
        if mode in POS:
            return mode
        got = self.assign.get(i)
        if got:
            return got
        pool = [k for k in self.cfg["positions"] if k in POS] or list(POS_KEYS)
        used = {self.assign.get(j) for j in current if j != i}
        cands = [k for k in pool if k not in used and k != self.last_pos]
        if not cands:
            cands = [k for k in pool if k != self.last_pos] or pool
        k = random.choice(cands)
        self.assign[i] = k
        self.last_pos = k
        return k

    def card_rect(self):
        hud = self.ctl.hud
        if self.wall or not hud.isVisible():
            return None
        m = hud.MARGIN * hud.scale
        gap = float(self.cfg["card_gap"])
        r = QRectF(
            hud.x() + m - self.org.x(),
            hud.y() + m - self.org.y(),
            hud.width() - 2 * m,
            hud.height() - 2 * m,
        )
        return r.adjusted(-gap, -gap, gap, gap)

    def block_rects(self):
        if self.wall or self.cfg["lyrics_over_ui"]:
            return []
        rects = []
        card = self.card_rect()
        if card is not None:
            rects.append(card)
        gap = float(self.cfg["card_gap"])
        for widget in (self.ctl.clock, self.ctl.monitor, self.ctl.stats, self.ctl.equalizer):
            if widget.isVisible():
                rects.append(
                    QRectF(
                        widget.x() - self.org.x(),
                        widget.y() - self.org.y(),
                        widget.width(),
                        widget.height(),
                    ).adjusted(-gap, -gap, gap, gap)
                )
        return rects

    def fit_all(self, rects, left, topy, bw, bh, side, mo, ghost_pad, W, H):
        if not rects:
            return left, topy
        for _ in range(len(rects) * 2 + 1):
            moved = False
            for r in rects:
                res = self.fit(left, topy, bw, bh, side, mo, ghost_pad, r, W, H)
                if res is None:
                    return None
                if res != (left, topy):
                    left, topy = res
                    moved = True
            if not moved:
                return left, topy
        return None

    def fit(self, left, topy, bw, bh, side, mo, ghost_pad, card, W, H):
        if card is None:
            return left, topy
        il = 4.0 + bw * 0.02 + ghost_pad + (60.0 * mo if side < 0 else 0.0)
        ir = 4.0 + bw * 0.02 + (60.0 * mo if side > 0 else 0.0)
        it = 8.0 + bh * 0.02 + 20.0 * mo
        ib = 8.0 + bh * 0.02 + (30.0 * mo if side == 0 else 0.0)

        def clear(l, t):
            return (
                l + bw + ir <= card.left()
                or l - il >= card.right()
                or t + bh + ib <= card.top()
                or t - it >= card.bottom()
            )

        if clear(left, topy):
            return left, topy
        xmin, xmax = 8.0, max(8.0, W - bw - 8.0)
        ymin, ymax = 16.0, max(16.0, H - bh - 16.0)
        opts = []
        for nl in (card.left() - ir - bw, card.right() + il):
            if xmin <= nl <= xmax:
                opts.append((abs(nl - left), nl, topy))
        for nt in (card.top() - ib - bh, card.bottom() + it):
            if ymin <= nt <= ymax:
                opts.append((abs(nt - topy), left, nt))
        if not opts:
            return None
        opts.sort(key=lambda o: o[0])
        return opts[0][1], opts[0][2]

    @timed
    def paintEvent(self, e):
        if self.fade < 0.01 and not self.wall:
            return
        p = QPainter(self)
        p.setRenderHints(AA)
        st = self.state
        cfg = self.cfg
        th = self.theme
        W = self.width()
        H = self.height()
        dpr = self.devicePixelRatioF()
        now = time.monotonic()
        t = now - self.t0
        pal = st.pal_target
        fade = self.fade
        if self.wall:
            self.paint_wall(p, W, H, dpr)
        if fade < 0.01:
            return
        self.paint_toast(p, W, H, pal)
        lines = st.active_lines()
        if not lines:
            return
        ly = st.lyrics
        base_px = cfg["font_size"] * 1.6 * cfg["holo_scale"] / 100.0
        glow = cfg["glow"] / 100.0
        scan = (int(cfg["scan_strength"] * 2.55), int(cfg["scan_gap"])) if cfg["scanlines"] else False
        karaoke = bool(cfg["karaoke"])
        glitch_on = bool(cfg["glitch"])
        tilt_on = bool(cfg["tilt"])
        fi = max(0.15, cfg["fade_ms"] / 1000.0 * 0.65)
        glitching = glitch_on and now < self.glitch_until
        current = [x[0] for x in lines]
        sty = lyric_style(cfg)
        sty_g = sty[:4] + (0, 0) + sty[6:]
        fill, fill2, gcol = lyric_colors(cfg, pal)
        dim_a = cfg["dim_level"] / 100.0
        mo = cfg["motion"] / 100.0
        lop = cfg["lyric_opacity"] / 100.0
        wf = cfg["holo_width"] / 100.0
        gs = cfg["ghost"] / 100.0
        ga = cfg["glitch_amount"] / 100.0
        fl = cfg["flicker"] / 100.0
        ghost_pad = 3.0 + 31.0 * ga if glitch_on else 3.0
        rects = self.block_rects()
        card = rects[0] if rects else None
        for i, a, prog, age, eo, life in lines:
            key = self.pos_for(i, current)
            ax, ay, align = POS[key]
            side = -1 if align == "l" else (1 if align == "r" else 0)
            maxw = W * (min(0.9, wf * 1.39) if align == "c" else wf)
            text = ly.texts[i]
            placed = None
            for attempt in (0, 1):
                bright = cached_line(self.cache, th, text, base_px, fill, gcol, glow, maxw, dpr, scan, align, sty, fill2)
                dim = (
                    cached_line(self.cache, th, text, base_px, fill, gcol, 0.0, maxw, dpr, scan, align, sty, fill2)
                    if karaoke
                    else None
                )
                ghost = cached_line(
                    self.cache, th, text, base_px, pal.secondary, pal.secondary, 0.2, maxw, dpr, False, align, sty_g, None, False
                )
                bw, bh = bright[1], bright[2]
                if align == "l":
                    left = ax * W
                elif align == "r":
                    left = ax * W - bw
                else:
                    left = ax * W - bw / 2.0
                topy = ay * H - bh / 2.0
                left = clamp(left, 8, max(8, W - bw - 8))
                topy = clamp(topy, 16, max(16, H - bh - 16))
                placed = self.fit_all(rects, left, topy, bw, bh, side, mo, ghost_pad, W, H)
                if placed is not None or card is None or attempt == 1:
                    break
                room = max(card.left(), W - card.right()) - 8.0 - (64.0 * mo + 40.0)
                if room < 160 or room >= maxw:
                    break
                maxw = room
            if placed is None:
                continue
            left, topy = placed
            enter = ease(age / fi)
            nx = ny = 0.0
            if eo > 0.0 and cfg["exit_style"] in ("next", "random"):
                n = i + 1
                while n < len(ly.texts) and not ly.texts[n]:
                    n += 1
                if n < len(ly.texts):
                    ax2, ay2, al2 = POS[self.pos_for(n, current + [n])]
                    tx = ax2 * W + (bw / 2.0 if al2 == "l" else (-bw / 2.0 if al2 == "r" else 0.0))
                    ty = ay2 * H
                    nx = clamp((tx - (left + bw / 2.0)) * 0.5, -260.0, 260.0)
                    ny = clamp((ty - (topy + bh / 2.0)) * 0.5, -260.0, 260.0)
            ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, side, t, i, life, nx, ny)
            base_tilt = (14.0 if side < 0 else (-14.0 if side > 0 else 0.0)) if tilt_on else 0.0
            rot = base_tilt * (1.6 - 0.6 * enter)
            tr = QTransform()
            tr.translate(left + bw / 2.0 + ox, topy + bh / 2.0 + oy)
            tr.rotate(rot, Qt.Axis.YAxis)
            tr.rotate(rx, Qt.Axis.XAxis)
            tr.rotate(rz)
            tr.scale(sc * sx, sc)
            p.setTransform(tr)
            gx = 3.0
            flick = 1.0 - fl * 0.05 * (1.0 - math.sin(t * 37.0))
            if glitch_on:
                gx += 16.0 * ga * (1.0 - enter)
                if glitching:
                    gx += random.uniform(6, 14) * ga
                    flick *= random.uniform(0.65, 1.0)
            if gs > 0.01:
                p.setOpacity(clamp(a * 0.4 * fade * gs * lop, 0.0, 1.0))
                p.drawPixmap(QPointF(-ghost[1] / 2.0 - gx, -ghost[2] / 2.0 + 1), ghost[0])
            draw_karaoke(p, dim, bright, prog, a * fade * lop, karaoke, flick, dim_a)
            p.resetTransform()
        p.setOpacity(1.0)

    def build_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if not self.wall:
            flags |= Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self.wall)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, self.wall)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not self.wall)

    def apply_layer(self):
        want = self.cfg["layer"] == "wall"
        if want == self.wall:
            return
        self.wall = want
        self.attached = False
        self.host = None
        self.wp_pm = None
        self.build_window()
        self.dirty = True

    def native_rect(self):
        screens = QGuiApplication.screens()
        s = screens[int(clamp(int(self.cfg["holo_screen"]), 0, len(screens) - 1))]
        g = s.geometry()
        d = s.devicePixelRatio()
        return g.x(), g.y(), int(round(g.width() * d)), int(round(g.height() * d))

    def attach_wall(self):
        if not self.wall:
            return
        if not self.attached:
            host = desktop_attach(int(self.winId()))
            if not host:
                self.cfg["layer"] = "top"
                self.cfg.save()
                self.ctl.refresh()
                self.ctl.tray.showMessage(
                    "Lyrics HUD", "The wallpaper layer is not available on this system, using the top layer instead."
                )
                return
            self.host = host
            self.attached = True
        self.move_native()

    def move_native(self):
        x, y, w, h = self.native_rect()
        desktop_place(int(self.winId()), self.host, x, y, w, h)
        self.dirty = True
        self.update()

    def wall_poll(self, now):
        if now < self.wp_next:
            return False
        self.wp_next = now + 3.0
        path = wallpaper_path()
        try:
            stamp = os.stat(path).st_mtime_ns if path else 0
        except OSError:
            stamp = 0
        src = (path, stamp, wallpaper_style())
        if src == self.wp_src:
            return False
        self.wp_src = src
        img = QImage(path) if path else QImage()
        self.wp_img = None if img.isNull() else img
        self.wp_pm = None
        return True

    def paint_wall(self, p, W, H, dpr):
        if self.wp_src is None:
            self.wall_poll(time.monotonic())
        style = self.wp_src[2] if self.wp_src else (10, 0, (0, 0, 0))
        sig = (self.wp_src, W, H, int(dpr * 100), self.org.x(), self.org.y())
        if self.wp_pm is None or self.wp_sig != sig:
            virt = QGuiApplication.primaryScreen().virtualGeometry()
            self.wp_pm = build_wallpaper(self.wp_img, style, W, H, dpr, self.org, virt)
            self.wp_sig = sig
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawPixmap(0, 0, self.wp_pm)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        dim = int(self.cfg["wall_dim"] * 2.55)
        if dim > 0:
            p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, dim))
        p.setCompositionMode(BLEND.get(self.cfg["wall_blend"], BLEND["normal"]))
