import math
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import QPainter, QPen, QBrush, QFont, QFontMetrics, QLinearGradient, QGuiApplication
from PyQt6.QtWidgets import QWidget

from lyricshud.painters import CardPaint
from lyricshud.styles import AA
from lyricshud.utils import with_alpha


CLOCK_MODES = [("Digital", "digital"), ("Minimal", "minimal"), ("Stacked", "stacked"), ("Date focus", "dateline"), ("Analog", "analog")]
CLOCK_DATE_FMTS = {"long": "%A, %d %B %Y", "short": "%a %d %b", "numeric": "%d.%m.%Y", "weekday": "%A"}


class Clock(QWidget, CardPaint):
    MARGIN = 10

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.theme = ctl.theme
        self.state = ctl.state
        self.card_init()
        self.img_key = "clock_bg_image"
        self.sig = None
        self.fkey = None
        self.dirty = True
        self.drag = None
        self.sc = 1.0
        self.apply_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.fit()
        self.restore_pos()

    def parts(self):
        c = self.cfg
        now = datetime.now() + timedelta(hours=float(c["clock_tz"]))
        mode = c["clock_mode"]
        if c["clock_24h"]:
            hh = now.strftime("%H")
            suffix = ""
        else:
            hh = now.strftime("%I").lstrip("0") or "12"
            suffix = now.strftime(" %p")
        if mode == "dateline":
            date = now.strftime("%d %b").upper()
            wd = now.strftime("%A").upper()
        else:
            date = now.strftime(CLOCK_DATE_FMTS.get(c["clock_date_fmt"], CLOCK_DATE_FMTS["long"])) if c["clock_date"] else ""
            wd = ""
        stamp = ""
        if mode == "analog":
            stamp = now.strftime("%H%M%S") + (str(now.microsecond // 100000) if c["clock_smooth"] else "0")
        return {
            "hh": hh,
            "mm": now.strftime("%M"),
            "secs": now.strftime(":%S") if (c["clock_seconds"] and mode != "analog") else "",
            "suffix": suffix,
            "date": date,
            "wd": wd,
            "label": c["clock_label"].strip(),
            "stamp": stamp,
            "blink": 1 if (c["clock_blink"] and now.second % 2) else 0,
        }

    def layout(self):
        c = self.cfg
        sc = self.sc
        d = self.parts()
        mode = c["clock_mode"]
        th = self.theme
        items = []
        state = {"y": 0.0, "w": 0.0}
        gap = 4.0 * sc

        def add(kind, h, w, **kw):
            items.append(dict(kind=kind, y=state["y"], h=h, **kw))
            state["y"] += h + gap
            state["w"] = max(state["w"], w)

        def fb(size, weight, spacing=0.0):
            return th.font(size * sc, weight, spacing)

        def run_items(size, hh_mm_only=False):
            fmain = fb(size, QFont.Weight.DemiBold)
            fsmall = fb(size * 0.5, QFont.Weight.Medium)
            runs = [(d["hh"], fmain, "main", "00"), (":", fmain, "colon", ":"), (d["mm"], fmain, "main", "00")]
            if d["secs"]:
                runs.append((d["secs"], fsmall, "sec", ":00"))
            if d["suffix"]:
                runs.append((d["suffix"], fsmall, "dim", " AM"))
            width = sum(QFontMetrics(f).horizontalAdvance(ref) for t, f, k, ref in runs)
            add("runs", QFontMetrics(fmain).height(), width, runs=runs)

        def text_item(text, font, alpha, kind="text"):
            fm = QFontMetrics(font)
            add(kind, fm.height(), fm.horizontalAdvance(text), font=font, text=text, alpha=alpha)

        if d["label"]:
            text_item(d["label"].upper(), fb(11, QFont.Weight.DemiBold, 3.0), 255, "label")
        if mode in ("digital", "minimal"):
            run_items(40 if mode == "digital" else 58)
            if mode == "digital" and d["date"]:
                text_item(d["date"], fb(13, QFont.Weight.Medium, 0.6), 150)
        elif mode == "stacked":
            fmain = fb(54, QFont.Weight.DemiBold)
            fm = QFontMetrics(fmain)
            add("big", int(fm.height() * 0.86), fm.horizontalAdvance("00"), font=fmain, text=d["hh"], clr=True)
            add("big", int(fm.height() * 0.86), fm.horizontalAdvance("00"), font=fmain, text=d["mm"], clr=False)
            extra = (d["secs"][1:] if d["secs"] else "") + d["suffix"].strip()
            if extra:
                text_item(extra, fb(14, QFont.Weight.Medium, 1.5), 170)
            if d["date"]:
                text_item(d["date"], fb(13, QFont.Weight.Medium, 0.6), 150)
        elif mode == "dateline":
            text_item(d["date"], fb(46, QFont.Weight.Bold), 255, "big_date")
            text_item(d["wd"], fb(13, QFont.Weight.DemiBold, 4.0), 170)
            run_items(24)
        else:
            size = int(150 * sc)
            add("analog", size, size)
            if d["date"]:
                text_item(d["date"], fb(13, QFont.Weight.Medium, 0.6), 150)
        pad_x = 18 * sc
        pad_y = 12 * sc
        M = self.MARGIN
        w = int(state["w"] + 2 * (M + pad_x))
        h = int(state["y"] - gap + 2 * (M + pad_y))
        return items, w, h, d

    def fit(self):
        self.sc = self.cfg["clock_scale"] / 100.0
        items, w, h, d = self.layout()
        self.timer.setInterval(100 if (self.cfg["clock_mode"] == "analog" and self.cfg["clock_smooth"]) else 250)
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)

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
        self.fkey = None
        self.fit()
        self.apply_blur()
        self.dirty = True
        self.update()

    def tick(self):
        d = self.parts()
        key = (bool(d["secs"]), d["suffix"], d["date"], d["label"])
        if key != self.fkey:
            self.fkey = key
            self.fit()
        sig = tuple(d.values())
        if sig != self.sig or self.dirty:
            self.sig = sig
            self.dirty = False
            self.update()

    def showEvent(self, e):
        super().showEvent(e)
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
        self.cfg["clock_x"] = self.x()
        self.cfg["clock_y"] = self.y()
        self.cfg.save()

    def reset_pos(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.width() - 24, g.top() + 24)
        self.save_pos()

    def restore_pos(self):
        x, y = self.cfg["clock_x"], self.cfg["clock_y"]
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

    def time_pen(self, pal, x0, x1):
        mode = self.cfg["clock_color"]
        if mode == "accent":
            return QPen(pal.accent, 1)
        if mode == "gradient":
            g = QLinearGradient(x0, 0, max(x0 + 1, x1), 0)
            g.setColorAt(0, pal.accent)
            g.setColorAt(1, pal.secondary)
            return QPen(QBrush(g), 1)
        return QPen(pal.text, 1)

    def draw_runs(self, p, pal, runs, cx, top, blink):
        widths = [QFontMetrics(f).horizontalAdvance(ref) for t, f, k, ref in runs]
        total = float(sum(widths))
        x = cx - total / 2.0
        base = top + QFontMetrics(runs[0][1]).ascent()
        main_pen = self.time_pen(pal, x, x + total)
        op = p.opacity()
        for (text, font, kind, ref), cell in zip(runs, widths):
            fm = QFontMetrics(font)
            p.setFont(font)
            if kind in ("main", "colon"):
                p.setPen(main_pen)
            elif kind == "sec":
                p.setPen(pal.accent)
            else:
                p.setPen(with_alpha(pal.text, 170))
            if kind == "colon" and blink:
                p.setOpacity(op * 0.15)
            p.drawText(QPointF(x + (cell - fm.horizontalAdvance(text)) / 2.0, base), text)
            p.setOpacity(op)
            x += cell

    def draw_analog(self, p, pal, r, d):
        c = self.cfg
        center = r.center()
        rad = r.width() / 2.0 - 2.0
        st = d["stamp"]
        hh = int(st[0:2])
        mm = int(st[2:4])
        ss = int(st[4:6])
        frac = int(st[6]) / 10.0 if len(st) > 6 else 0.0
        p.setPen(QPen(with_alpha(pal.text, 80), 1.6))
        p.setBrush(with_alpha(pal.bg, 70))
        p.drawEllipse(center, rad, rad)

        def pt(angle, length):
            a = math.radians(angle)
            return QPointF(center.x() + length * math.sin(a), center.y() - length * math.cos(a))

        if c["clock_face_ticks"]:
            for i in range(60):
                big = i % 5 == 0
                p.setPen(QPen(with_alpha(pal.text, 190 if big else 80), 2.0 * self.sc if big else 1.0))
                p.drawLine(pt(i * 6, rad * (0.88 if big else 0.93)), pt(i * 6, rad * 0.98))
        if c["clock_face_nums"]:
            f = self.theme.font(max(8.0, rad * 0.17), QFont.Weight.DemiBold)
            fm = QFontMetrics(f)
            p.setFont(f)
            p.setPen(with_alpha(pal.text, 200))
            for n in range(1, 13):
                q = pt(n * 30, rad * 0.72)
                tw = fm.horizontalAdvance(str(n))
                p.drawText(QPointF(q.x() - tw / 2.0, q.y() + (fm.ascent() - fm.descent()) / 2.0), str(n))
        mode = c["clock_color"]
        hour_col, min_col, sec_col = pal.text, pal.text, pal.accent
        if mode == "accent":
            hour_col, min_col, sec_col = pal.accent, pal.accent, pal.secondary
        elif mode == "gradient":
            hour_col, min_col, sec_col = pal.accent, pal.secondary, pal.text
        ha = ((hh % 12) + mm / 60.0) * 30.0
        ma = (mm + ss / 60.0) * 6.0
        sa = (ss + frac) * 6.0
        for angle, length, width, col in ((ha, 0.5, 4.5, hour_col), (ma, 0.76, 3.2, min_col), (sa, 0.88, 1.6, sec_col)):
            p.setPen(QPen(col, width * self.sc, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(pt(angle + 180.0, rad * 0.12), pt(angle, rad * length))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.accent)
        p.drawEllipse(center, 4.0 * self.sc, 4.0 * self.sc)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        pal = self.state.pal_target
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setOpacity(self.cfg["clock_opacity"] / 100.0)
        self.paint_card(p, card, pal)
        items, w, h, d = self.layout()
        top0 = card.top() + 12 * self.sc
        cx = card.center().x()
        for it in items:
            y = top0 + it["y"]
            kind = it["kind"]
            if kind == "runs":
                self.draw_runs(p, pal, it["runs"], cx, y, d["blink"])
            elif kind == "analog":
                size = it["h"]
                self.draw_analog(p, pal, QRectF(cx - size / 2.0, y, size, size), d)
            elif kind == "label":
                p.setFont(it["font"])
                p.setPen(pal.accent)
                p.drawText(QRectF(card.left(), y, card.width(), it["h"]), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, it["text"])
            elif kind in ("big", "big_date"):
                p.setFont(it["font"])
                fm = QFontMetrics(it["font"])
                p.setPen(self.time_pen(pal, cx - 40, cx + 40) if kind == "big" else pal.text)
                if kind == "big" and it.get("clr") is False and self.cfg["clock_color"] == "text":
                    p.setPen(with_alpha(pal.text, 190))
                p.drawText(QPointF(cx - fm.horizontalAdvance(it["text"]) / 2.0, y + fm.ascent() * 0.86), it["text"])
            else:
                p.setFont(it["font"])
                p.setPen(with_alpha(pal.text, it["alpha"]))
                p.drawText(QRectF(card.left(), y, card.width(), it["h"]), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, it["text"])
