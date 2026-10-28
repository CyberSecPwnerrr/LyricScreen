import time
import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QPixmap,
    QLinearGradient,
    QRadialGradient,
    QTransform,
    QGuiApplication,
    QCursor,
)
from PyQt6.QtWidgets import QWidget

from lyricshud.desktop import set_click_through
from lyricshud.effects import line_fx
from lyricshud.icons import (
    icon_next,
    icon_pause,
    icon_play,
    icon_prev,
    icon_repeat,
    icon_shuffle,
    icon_speaker,
)
from lyricshud.painters import CardPaint
from lyricshud.render import LineCache, cached_line, draw_karaoke
from lyricshud.styles import AA
from lyricshud.utils import (
    clamp,
    ease,
    eff_fps,
    fmt_time,
    lyric_colors,
    lyric_style,
    mix,
    timed,
    tune_timer,
    with_alpha,
)


class Hud(QWidget, CardPaint):
    MARGIN = 12
    COMPACT_H = 246

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.cache = LineCache()
        self.cover_pm = None
        self.cover_sig = None
        self.card_init()
        self.applied_scale = self.scale
        self.last = time.monotonic()
        self.drag = None
        self.resize_from = None
        self.dirty = True
        self.ct_applied = None
        self.lock_timer = QTimer(self)
        self.lock_timer.setInterval(16)
        self.lock_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.lock_timer.timeout.connect(self.poll_lock)
        self.hits = []
        self.rects = {}
        self.hover = None
        self.pressed = None
        self.press_rect = None
        self.seeking = False
        self.seek_frac = 0.0
        self.vol_drag = False
        self.hv = {}
        self.appear = 0.0
        self.track_t = time.monotonic()
        self.mouse_x = 0.0
        self.compact = self.cfg["mode"] == "both"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.apply_flags()
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(int(min(self.cfg["hud_w"], g.width() - 48)), int(min(self.cfg["hud_h"], g.height() - 48)))
        self.apply_size_limits(True)
        self.restore_pos()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.set_fps()
        self.state.track_changed.connect(self.on_track)
        self.state.lyrics_changed.connect(self.mark_dirty)
        self.state.offset_changed.connect(self.mark_dirty)

    def mark_dirty(self):
        self.dirty = True

    def on_track(self):
        self.track_t = time.monotonic()
        self.dirty = True

    @property
    def scale(self):
        return clamp(self.cfg["hud_scale"] / 100.0, 0.6, 1.8)

    def lp(self, pos):
        s = self.scale
        return QPointF(pos.x() / s, pos.y() / s)

    def apply_blur(self):
        s = self.scale
        m = self.MARGIN * s
        self.blur_card(QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m), s)

    def apply_size_limits(self, snap):
        s = self.scale
        mw = int(440 * s)
        if self.compact:
            ch = int(self.COMPACT_H * s)
            self.setMinimumSize(mw, ch)
            self.setMaximumSize(16777215, ch)
            if snap:
                self.resize(self.width(), ch)
        else:
            mh = int(400 * s)
            self.setMaximumSize(16777215, 16777215)
            self.setMinimumSize(mw, mh)
            if snap:
                self.resize(self.width(), max(mh, int(self.cfg["hud_h"])))

    def apply_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        self.top_applied = bool(self.cfg["always_on_top"])
        if self.top_applied:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        was = self.isVisible()
        self.setWindowFlags(flags)
        if was:
            self.show()

    def restore_pos(self):
        x, y = self.cfg["hud_x"], self.cfg["hud_y"]
        ok = False
        if x is not None and y is not None:
            for s in QGuiApplication.screens():
                if s.geometry().contains(QPoint(int(x) + 40, int(y) + 40)):
                    ok = True
        if not ok:
            self.reset_pos()
            return
        self.move(int(x), int(y))

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)
        self.save_geometry()

    def save_geometry(self):
        self.cfg["hud_x"] = self.x()
        self.cfg["hud_y"] = self.y()
        self.cfg["hud_w"] = self.width()
        if not self.compact:
            self.cfg["hud_h"] = self.height()
        self.cfg.save()

    def set_fps(self):
        self.base_ms = int(1000 / eff_fps(self.cfg))
        self.timer.setInterval(self.base_ms)

    def release_all(self):
        self.pressed = None
        self.press_rect = None
        self.seeking = False
        self.vol_drag = False
        self.drag = None
        self.resize_from = None

    def refresh(self):
        if self.top_applied != bool(self.cfg["always_on_top"]):
            self.apply_flags()
        self.cache.clear()
        self.cover_sig = None
        self.bd_sig = None
        self.img_sig = None
        compact = self.cfg["mode"] == "both"
        mode_changed = compact != self.compact
        self.compact = compact
        s = self.scale
        k = s / self.applied_scale
        self.applied_scale = s
        self.apply_size_limits(False)
        if abs(k - 1.0) > 1e-6:
            self.resize(int(self.width() * k), int(self.height() * k))
        if mode_changed:
            self.apply_size_limits(True)
        self.apply_blur()
        self.sync_lock()
        self.set_fps()
        self.dirty = True
        self.update()

    def showEvent(self, e):
        self.last = time.monotonic()
        self.appear = 0.0 if self.cfg["ui_anim"] else 1.0
        self.timer.start()
        super().showEvent(e)
        self.sync_lock()
        self.apply_blur()

    def hideEvent(self, e):
        self.timer.stop()
        self.lock_timer.stop()
        super().hideEvent(e)

    def moveEvent(self, e):
        super().moveEvent(e)
        h = getattr(self.ctl, "holo", None)
        if h is not None:
            h.dirty = True

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.isVisible():
            self.apply_blur()
        h = getattr(self.ctl, "holo", None)
        if h is not None:
            h.dirty = True

    def sync_lock(self):
        self.ct_applied = None
        if self.cfg["click_through"]:
            self.drag = None
            self.resize_from = None
            if self.isVisible():
                self.lock_timer.start()
        else:
            self.lock_timer.stop()
            if self.isVisible():
                set_click_through(self, False)
            self.ct_applied = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.dirty = True

    def poll_lock(self):
        if not self.isVisible():
            return
        want = False
        if self.cfg["click_through"]:
            busy = self.seeking or self.vol_drag or self.pressed is not None
            if not busy:
                want = self.hit_at(self.lp(QPointF(self.mapFromGlobal(QCursor.pos())))) is None
        if want != self.ct_applied:
            self.ct_applied = want
            set_click_through(self, want)
            if want and self.hover is not None:
                self.hover = None
                self.dirty = True

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        if (
            self.pressed is not None
            or self.seeking
            or self.vol_drag
            or self.drag is not None
            or self.resize_from is not None
        ) and not (QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self.release_all()
            self.dirty = True
        tune_timer(self)
        busy = self.state.step_palette()
        ui = bool(self.cfg["ui_anim"])
        for name in set(self.hv) | {self.hover}:
            if name is None:
                continue
            target = 1.0 if name == self.hover else 0.0
            cur = self.hv.get(name, 0.0)
            if ui:
                new = cur + (target - cur) * (1.0 - math.exp(-dt * 16.0))
                if abs(target - new) < 0.01:
                    new = target
            else:
                new = target
            if new != cur:
                busy = True
            if new <= 0.0 and target == 0.0:
                self.hv.pop(name, None)
            else:
                self.hv[name] = new
        if self.appear < 1.0:
            self.appear = min(1.0, self.appear + dt * 3.4) if ui else 1.0
            busy = True
        if now - self.track_t < 1.0:
            busy = True
        if self.state.playing or busy or self.dirty or self.seeking or self.vol_drag:
            self.dirty = False
            self.update()

    def add_hit(self, name, rect):
        r = QRectF(rect)
        self.hits.append((r, name))
        self.rects[name] = r

    def hit_at(self, pos):
        for r, name in self.hits:
            if r.contains(pos):
                return name
        return None

    def in_grip(self, pos):
        s = self.scale
        return not self.cfg["click_through"] and pos.x() > self.width() / s - 30 and pos.y() > self.height() / s - 30

    def frac_in(self, name, x):
        r = self.rects.get(name)
        if r is None or r.width() <= 0:
            return 0.0
        return clamp((x - r.left()) / r.width(), 0.0, 1.0)

    def apply_vol(self, x):
        self.ctl.set_volume(self.frac_in("vol", x))
        self.dirty = True

    def activate(self, name):
        st = self.state
        actions = {
            "play": st.toggle_play,
            "prev": st.skip_prev,
            "next": st.skip_next,
            "shuffle": st.toggle_shuffle,
            "repeat": st.cycle_repeat,
            "mute": self.ctl.toggle_mute,
            "gear": lambda: QTimer.singleShot(0, self.ctl.open_settings),
            "mode": self.ctl.cycle_mode,
            "close": self.ctl.hide_all,
            "sync_m": lambda: self.ctl.nudge(-100),
            "sync_p": lambda: self.ctl.nudge(100),
            "sync_r": lambda: self.ctl.nudge(None),
        }
        fn = actions.get(name)
        if fn:
            fn()
        self.dirty = True

    def mousePressEvent(self, e):
        gp = e.globalPosition().toPoint()
        pos = self.lp(e.position())
        if e.button() == Qt.MouseButton.LeftButton:
            if self.in_grip(pos):
                self.resize_from = (gp, self.size())
                return
            name = self.hit_at(pos)
            if name == "seek":
                if self.state.dur > 0 and self.state.can.get("seek", True):
                    self.seeking = True
                    self.seek_frac = self.frac_in("seek", pos.x())
            elif name == "vol":
                self.vol_drag = True
                self.apply_vol(pos.x())
            elif name:
                self.pressed = name
                self.press_rect = QRectF(self.rects.get(name, QRectF()))
            elif not self.cfg["click_through"]:
                self.drag = gp - self.frameGeometry().topLeft()
            self.dirty = True
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.ctl.open_orbital()
        elif e.button() == Qt.MouseButton.RightButton:
            self.ctl.menu.exec(gp)

    def mouseMoveEvent(self, e):
        gp = e.globalPosition().toPoint()
        pos = self.lp(e.position())
        self.mouse_x = pos.x()
        if self.resize_from is not None:
            origin, size = self.resize_from
            d = gp - origin
            self.resize(
                max(self.minimumWidth(), size.width() + d.x()),
                max(self.minimumHeight(), size.height() + d.y()),
            )
        elif self.seeking:
            self.seek_frac = self.frac_in("seek", pos.x())
        elif self.vol_drag:
            self.apply_vol(pos.x())
        elif self.drag is not None:
            self.move(gp - self.drag)
        else:
            name = self.hit_at(pos)
            if name != self.hover:
                self.hover = name
                self.dirty = True
            if self.in_grip(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif name:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e):
        pos = self.lp(e.position())
        if self.seeking:
            self.seeking = False
            self.state.seek(self.seek_frac * self.state.dur)
        if self.vol_drag:
            self.vol_drag = False
        if self.pressed is not None:
            r = self.press_rect if self.press_rect is not None else self.rects.get(self.pressed)
            name = self.pressed
            self.pressed = None
            self.press_rect = None
            if r is not None and r.adjusted(-12, -12, 12, 12).contains(pos):
                self.activate(name)
        if self.drag is not None or self.resize_from is not None:
            self.drag = None
            self.resize_from = None
            self.save_geometry()
        self.dirty = True

    def leaveEvent(self, e):
        if self.hover is not None:
            self.hover = None
            self.dirty = True
        super().leaveEvent(e)

    def wheelEvent(self, e):
        sign = 1 if (e.angleDelta().y() or e.angleDelta().x()) > 0 else -1
        mod = e.modifiers()
        if mod & Qt.KeyboardModifier.ControlModifier:
            self.ctl.bump("hud_scale", 5 * sign, 60, 180)
        elif mod & Qt.KeyboardModifier.ShiftModifier:
            self.ctl.bump("opacity", 5 * sign, 30, 100)
        else:
            self.ctl.change_volume(0.03 * sign)
        self.dirty = True

    def chip_text(self):
        st = self.state
        if not st.active:
            return "Idle"
        parts = []
        if not st.playing:
            parts.append("Paused")
        parts.append({"loading": "Searching lyrics", "found": "Synced lyrics", "none": "No synced lyrics"}.get(st.status, ""))
        return "  ·  ".join(x for x in parts if x)

    def paint_cover(self, p, r, pal, dpr):
        path = QPainterPath()
        path.addRoundedRect(r, 13, 13)
        p.save()
        p.setClipPath(path)
        img = self.state.cover
        if img is not None:
            sig = (self.state.cover_id, int(r.width()), int(dpr * 100))
            if sig != self.cover_sig:
                s = max(1, int(r.width() * dpr))
                sc = img.scaled(
                    s, s, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
                )
                sc = sc.copy((sc.width() - s) // 2, (sc.height() - s) // 2, s, s)
                self.cover_pm = QPixmap.fromImage(sc)
                self.cover_pm.setDevicePixelRatio(dpr)
                self.cover_sig = sig
            p.drawPixmap(r.topLeft(), self.cover_pm)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, with_alpha(pal.accent, 160))
            g.setColorAt(1, with_alpha(pal.secondary, 100))
            p.fillRect(r, QBrush(g))
            p.setFont(QFont("Segoe UI Symbol", 30, QFont.Weight.Bold))
            p.setPen(QColor(255, 255, 255, 200))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "♪")
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(pal.text, 55), 1.0))
        p.drawPath(path)

    def paint_progress(self, p, x0, x1, py, pal):
        st = self.state
        dur = st.dur
        frac = self.seek_frac if self.seeking else (clamp(st.position() / dur, 0.0, 1.0) if dur > 0 else 0.0)
        pos = frac * dur if dur > 0 else st.position()
        hv = 1.0 if self.seeking else self.hv.get("seek", 0.0)
        th = 4.0 + 3.0 * hv
        bar = QRectF(x0, py + 2.0 - th / 2.0, x1 - x0, th)
        hit = QRectF(x0, py - 9, x1 - x0, 24)
        self.add_hit("seek", hit)
        self.rects["seek"] = hit
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(bar, th / 2.0, th / 2.0)
        if frac > 0:
            fill = QRectF(x0, bar.top(), bar.width() * frac, th)
            g = QLinearGradient(fill.left(), 0, fill.right() + 1, 0)
            g.setColorAt(0, pal.accent)
            g.setColorAt(1, pal.secondary)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(fill, th / 2.0, th / 2.0)
            if hv > 0.02:
                p.setBrush(with_alpha(pal.secondary, int(70 * hv)))
                p.drawEllipse(QPointF(fill.right(), py + 2), 5.0 + 5.0 * hv, 5.0 + 5.0 * hv)
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(fill.right(), py + 2), 2.0 + 3.5 * hv, 2.0 + 3.5 * hv)
        if hv > 0.05 and dur > 0:
            mf = self.seek_frac if self.seeking else self.frac_in("seek", self.mouse_x)
            fb = self.theme.font(11, QFont.Weight.DemiBold)
            fmb = QFontMetrics(fb)
            label = fmt_time(mf * dur)
            bw = fmb.horizontalAdvance(label) + 16.0
            bx = clamp(x0 + (x1 - x0) * mf - bw / 2.0, x0 - 6.0, x1 - bw + 6.0)
            br = QRectF(bx, py - 30.0 + (1.0 - hv) * 6.0, bw, 20.0)
            p.setBrush(with_alpha(pal.bg, int(235 * hv)))
            p.setPen(QPen(with_alpha(pal.accent, int(160 * hv)), 1.0))
            p.drawRoundedRect(br, 7, 7)
            p.setFont(fb)
            p.setPen(with_alpha(pal.text, int(240 * hv)))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, label)
        f = self.theme.font(11, QFont.Weight.Medium)
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(with_alpha(pal.text, 140))
        base = py + 15 + fm.ascent()
        p.drawText(QPointF(x0, base), fmt_time(pos))
        right = fmt_time(dur) if dur > 0 else "--:--"
        p.drawText(QPointF(x1 - fm.horizontalAdvance(right), base), right)

    def button(self, p, name, cx, cy, size, draw, pal, enabled=True, active=False, **kw):
        hv = self.hv.get(name, 0.0)
        press = 0.9 if self.pressed == name else 1.0
        if enabled:
            hs = max(size * 1.9, 30.0)
            self.add_hit(name, QRectF(cx - hs / 2.0, cy - hs / 2.0, hs, hs))
            if hv > 0.01:
                rr = size * (0.8 + 0.15 * hv)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pal.text, int(38 * hv)))
                p.drawEllipse(QPointF(cx, cy), rr, rr)
        if not enabled:
            col = with_alpha(pal.text, 70)
        elif active:
            col = QColor(pal.accent)
        else:
            col = with_alpha(mix(pal.text, pal.accent, 0.5 * hv), 215 + int(40 * hv))
        draw(p, cx, cy, size * (1.0 + 0.14 * hv) * press, col, **kw)

    def paint_controls(self, p, x0, x1, cy, pal):
        st = self.state
        cfg = self.cfg
        can = st.can
        vol_on = bool(cfg["show_volume"]) and self.ctl.volume.available
        vw = clamp((x1 - x0) * 0.22, 64, 120)
        right_start = x1 - ((vw + 42) if vol_on else 0)
        mid = (x0 + right_start) / 2.0
        self.button(p, "shuffle", mid - 100, cy, 14, icon_shuffle, pal, can.get("shuffle", True), st.shuffle)
        self.button(p, "prev", mid - 52, cy, 18, icon_prev, pal, can.get("prev", True))
        hp = self.hv.get("play", 0.0)
        glow_r = 36.0 + 6.0 * hp
        r = 23.0 * (1.0 + 0.07 * hp) * (0.94 if self.pressed == "play" else 1.0)
        rg = QRadialGradient(mid, cy, glow_r)
        rg.setColorAt(0, with_alpha(pal.accent, int(60 + 50 * hp)))
        rg.setColorAt(1, with_alpha(pal.accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(mid, cy), glow_r, glow_r)
        g = QLinearGradient(mid - r, cy - r, mid + r, cy + r)
        g.setColorAt(0, pal.accent)
        g.setColorAt(1, pal.secondary)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(mid, cy), r, r)
        if hp > 0.02:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(pal.text, int(190 * hp)), 2))
            p.drawEllipse(QPointF(mid, cy), r + 3, r + 3)
        self.add_hit("play", QRectF(mid - 23, cy - 23, 46, 46))
        (icon_pause if st.playing else icon_play)(
            p, mid + (0 if st.playing else 1.5), cy, 20 * (1.0 + 0.07 * hp), pal.bg
        )
        self.button(p, "next", mid + 52, cy, 18, icon_next, pal, can.get("next", True))
        self.button(p, "repeat", mid + 100, cy, 14, icon_repeat, pal, can.get("repeat", True), st.repeat != 0, mode=st.repeat)
        if vol_on:
            level = 0.0 if self.ctl.vol_muted else self.ctl.vol_level
            self.button(p, "mute", x1 - vw - 18, cy, 14, icon_speaker, pal, True, False, level=level, muted=self.ctl.vol_muted)
            hvv = 1.0 if self.vol_drag else self.hv.get("vol", 0.0)
            vth = 4.0 + 2.0 * hvv
            bar = QRectF(x1 - vw, cy - 2, vw, 4)
            self.add_hit("vol", bar.adjusted(-4, -11, 4, 11))
            self.rects["vol"] = bar
            track = QRectF(bar.left(), cy - vth / 2.0, vw, vth)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(track, vth / 2.0, vth / 2.0)
            fw = bar.width() * level
            if fw > 0:
                vg = QLinearGradient(bar.left(), 0, bar.right(), 0)
                vg.setColorAt(0, pal.accent)
                vg.setColorAt(1, pal.secondary)
                p.setBrush(QBrush(vg))
                p.drawRoundedRect(QRectF(bar.left(), track.top(), fw, vth), vth / 2.0, vth / 2.0)
            if hvv > 0.02:
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(bar.left() + fw, cy), 2.0 + 3.5 * hvv, 2.0 + 3.5 * hvv)

    def paint_lyric_area(self, p, area, dpr, op):
        st = self.state
        lines = st.active_lines()
        if not lines:
            return
        tp = st.pal_target
        ly = st.lyrics
        cfg = self.cfg
        size = float(cfg["font_size"])
        glow = cfg["glow"] / 100.0
        maxw = area.width() - 24
        karaoke = bool(cfg["karaoke"])
        sty = lyric_style(cfg)
        fill, fill2, gcol = lyric_colors(cfg, tp)
        dim_a = cfg["dim_level"] / 100.0
        lop = cfg["lyric_opacity"] / 100.0
        p.save()
        p.setClipRect(area)
        for i, a, prog, age, eo, life in lines:
            text = ly.texts[i]
            bright = cached_line(self.cache, self.theme, text, size, fill, gcol, glow, maxw, dpr, False, "c", sty, fill2)
            dim = (
                cached_line(self.cache, self.theme, text, size, fill, gcol, 0.0, maxw, dpr, False, "c", sty, fill2)
                if karaoke
                else None
            )
            enter = ease(age / 0.5)
            ox, oy, sc, sx, rx, rz = line_fx(cfg, enter, eo, 0, time.monotonic(), i, life)
            tr = QTransform()
            tr.translate(area.center().x() + ox, area.center().y() + oy)
            tr.rotate(rx, Qt.Axis.XAxis)
            tr.rotate(rz)
            tr.scale(sc * sx, sc)
            p.save()
            p.setTransform(tr, True)
            draw_karaoke(p, dim, bright, prog, a * op * lop, karaoke, 1.0, dim_a)
            p.restore()
        p.restore()
        p.setOpacity(op)

    @timed
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        th = self.theme
        st = self.state
        cfg = self.cfg
        s = self.scale
        dpr = self.devicePixelRatioF() * s
        pal = st.palette
        now = time.monotonic()
        ui = bool(cfg["ui_anim"])
        uf = cfg["ui_font"] / 100.0
        ap = ease(self.appear)
        op = cfg["opacity"] / 100.0
        m = self.MARGIN
        card = QRectF(m, m, self.width() / s - 2 * m, self.height() / s - 2 * m)
        self.hits = []
        p.scale(s, s)
        p.translate(0.0, (1.0 - ap) * 14.0)
        p.setOpacity(op * ap)
        self.paint_card(p, card, pal)
        pad = 20.0
        x0 = card.left() + pad
        x1 = card.right() - pad
        top = card.top() + pad
        age = now - self.track_t
        ta = ease(age / 0.55) if ui else 1.0
        ta2 = ease((age - 0.08) / 0.55) if ui else 1.0
        ta3 = ease((age - 0.16) / 0.55) if ui else 1.0
        show_cover = bool(cfg["show_cover"])
        cs = 88.0 if show_cover else 70.0
        if show_cover:
            cr = QRectF(x0, top, cs, cs)
            if ui and st.playing:
                pulse = 0.5 + 0.5 * math.sin(now * 2.4)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(with_alpha(pal.accent, int(30 + 60 * pulse)), 3.0))
                p.drawRoundedRect(cr.adjusted(-1.5, -1.5, 1.5, 1.5), 14, 14)
            p.save()
            c = cr.center()
            sc = 0.9 + 0.1 * ta
            p.translate(c)
            p.scale(sc, sc)
            p.translate(-c.x(), -c.y())
            p.setOpacity(op * ap * ta)
            self.paint_cover(p, cr, pal, dpr)
            p.restore()
        tx = x0 + (cs + 16.0 if show_cover else 0.0)
        tw = max(40.0, x1 - tx - 74.0)
        if st.active:
            title, artist, album = st.title, st.artist, st.album
        else:
            title, artist, album = "Waiting for media", "Play something in Spotify or your browser", ""
        cy = top
        ft = th.font(21 * uf, QFont.Weight.Bold)
        fm = QFontMetrics(ft)
        p.setFont(ft)
        p.setPen(with_alpha(pal.text, int(255 * ta)))
        p.drawText(
            QPointF(tx + (1.0 - ta) * 18.0, cy + fm.ascent()),
            fm.elidedText(title, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 2
        fa = th.font(15 * uf, QFont.Weight.Medium)
        fm = QFontMetrics(fa)
        p.setFont(fa)
        p.setPen(with_alpha(pal.text, int(215 * ta2)))
        p.drawText(
            QPointF(tx + (1.0 - ta2) * 18.0, cy + fm.ascent()),
            fm.elidedText(artist, Qt.TextElideMode.ElideRight, int(tw)),
        )
        cy += fm.height() + 1
        if album and cfg["show_album"]:
            fb = th.font(12 * uf, QFont.Weight.Normal)
            fm = QFontMetrics(fb)
            p.setFont(fb)
            p.setPen(with_alpha(pal.text, int(120 * ta3)))
            p.drawText(
                QPointF(tx + (1.0 - ta3) * 18.0, cy + fm.ascent()),
                fm.elidedText(album, Qt.TextElideMode.ElideRight, int(tw)),
            )
        gx = card.right() - 14
        sym = QFont("Segoe UI Symbol", 10)
        for name, glyph in (("close", "✕"), ("mode", "▣"), ("gear", "⚙")):
            r = QRectF(gx - 22, card.top() + 10, 22, 22)
            self.add_hit(name, r.adjusted(-1, -4, 1, 4))
            hv = self.hv.get(name, 0.0)
            if hv > 0.01:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(with_alpha(pal.text, int(38 * hv)))
                p.drawEllipse(r.adjusted(1, 1, -1, -1))
            p.setFont(sym)
            p.setPen(with_alpha(pal.text, int(110 + 80 * hv)))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, glyph)
            gx -= 24
        sync_on = bool(cfg["show_sync"]) and st.active and st.lyrics is not None
        if cfg["show_status"]:
            fc = th.font(11, QFont.Weight.Medium, 0.6)
            fmc = QFontMetrics(fc)
            base = top + cs - 2
            off = 20.0 if cfg["show_eq"] else 14.0
            p.setPen(Qt.PenStyle.NoPen)
            if cfg["show_eq"]:
                lit = st.playing
                p.setBrush(pal.accent if lit else with_alpha(pal.text, 110))
                for k in range(4):
                    hgt = 3.0 + 8.0 * (0.5 + 0.5 * math.sin(now * (5.0 + k * 1.9) + k * 1.3)) if lit else 3.0
                    p.drawRoundedRect(QRectF(tx + k * 4.0, base - 2.0 - hgt, 2.6, hgt), 1.3, 1.3)
            else:
                p.setBrush(pal.accent if st.playing else with_alpha(pal.text, 110))
                p.drawEllipse(QPointF(tx + 3.5, base - 4.2), 3.0, 3.0)
            p.setFont(fc)
            p.setPen(with_alpha(pal.text, 150))
            avail = x1 - tx - off - ((120.0 if cfg["show_sync_val"] else 50.0) if sync_on else 0.0)
            p.drawText(
                QPointF(tx + off, base),
                fmc.elidedText(self.chip_text(), Qt.TextElideMode.ElideRight, int(max(20.0, avail))),
            )
        if sync_on:
            self.paint_sync(p, x1, top + cs - 6.0, pal)
        py = top + cs + 20.0
        self.paint_progress(p, x0, x1, py, pal)
        cyc = py + 50.0
        self.paint_controls(p, x0, x1, cyc, pal)
        if not self.compact:
            area_top = cyc + 23 + 14
            area = QRectF(x0 - 8, area_top, x1 - x0 + 16, card.bottom() - pad + 4 - area_top)
            if area.height() > 40:
                p.setPen(QPen(with_alpha(pal.text, 26), 1))
                p.drawLine(QPointF(x0, area_top - 6), QPointF(x1, area_top - 6))
                self.paint_lyric_area(p, area, dpr, op * ap)
        if not cfg["click_through"]:
            p.setPen(QPen(with_alpha(pal.text, 70), 1.2))
            gx2 = card.right() - 10
            gy2 = card.bottom() - 10
            for k in (6, 11, 16):
                p.drawLine(QPointF(gx2 - k, gy2), QPointF(gx2, gy2 - k))

    def mini(self, p, name, cx, cy, text, pal):
        hv = self.hv.get(name, 0.0)
        r = QRectF(cx - 10, cy - 10, 20, 20)
        self.add_hit(name, r.adjusted(-4, -4, 4, 4))
        rr = 8.5 + 1.5 * hv
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(pal.text, int(18 + 50 * hv)))
        p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.setFont(self.theme.font(14, QFont.Weight.Bold))
        p.setPen(with_alpha(mix(pal.text, pal.accent, hv), int(150 + 90 * hv)))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def paint_sync(self, p, x1, cy, pal):
        val = self.state.sync_ms()
        self.mini(p, "sync_p", x1 - 10, cy, "+", pal)
        if not self.cfg["show_sync_val"]:
            self.mini(p, "sync_m", x1 - 36, cy, "\u2212", pal)
            return
        self.mini(p, "sync_m", x1 - 102, cy, "\u2212", pal)
        hv = self.hv.get("sync_r", 0.0)
        lr = QRectF(x1 - 92, cy - 10, 68, 20)
        self.add_hit("sync_r", lr)
        label = f"{val:+d} ms" if val else "0 ms"
        col = pal.accent if val else pal.text
        p.setFont(self.theme.font(11, QFont.Weight.DemiBold))
        p.setPen(with_alpha(mix(col, pal.text, hv * 0.4), int((210 if val else 130) + 40 * hv)))
        p.drawText(lr, Qt.AlignmentFlag.AlignCenter, label)
