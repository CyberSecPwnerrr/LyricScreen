from PyQt6.QtCore import Qt, QRect, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetrics,
    QPixmap,
    QImage,
)
from PyQt6.QtWidgets import QWidget, QDialog, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QSlider

from lyricshud.images import cover_fit, crop_frame
from lyricshud.styles import AA
from lyricshud.theme import apply_qss
from lyricshud.utils import clamp, with_alpha


class TextAreaDialog(QDialog):
    MAXW = 560
    MAXH = 330

    class Canvas(QWidget):
        def __init__(self, dlg, pm):
            super().__init__()
            self.dlg = dlg
            self.pm = pm
            self.mode = None
            self.anchor = QPointF()
            self.grab = QPointF()
            self.setFixedSize(pm.width(), pm.height())
            self.setCursor(Qt.CursorShape.CrossCursor)

        def px(self):
            s = self.dlg.sel
            return QRectF(s[0] * self.width(), s[1] * self.height(), s[2] * self.width(), s[3] * self.height())

        def norm(self, r):
            r = r.normalized()
            x = clamp(r.left() / self.width(), 0.0, 1.0)
            y = clamp(r.top() / self.height(), 0.0, 1.0)
            w = clamp(r.width() / self.width(), 0.0, 1.0 - x)
            h = clamp(r.height() / self.height(), 0.0, 1.0 - y)
            self.dlg.sel = [x, y, w, h]
            self.dlg.sample.update()
            self.update()

        def mousePressEvent(self, e):
            if e.button() != Qt.MouseButton.LeftButton:
                return
            pos = e.position()
            r = self.px()
            full = self.dlg.sel[2] > 0.98 and self.dlg.sel[3] > 0.98
            if not full and r.contains(pos):
                self.mode = "move"
                self.grab = pos - r.topLeft()
            else:
                self.mode = "draw"
                self.anchor = pos

        def mouseMoveEvent(self, e):
            if self.mode is None:
                return
            pos = QPointF(clamp(e.position().x(), 0, self.width()), clamp(e.position().y(), 0, self.height()))
            if self.mode == "draw":
                self.norm(QRectF(self.anchor, pos))
            else:
                r = self.px()
                tl = pos - self.grab
                x = clamp(tl.x(), 0, self.width() - r.width())
                y = clamp(tl.y(), 0, self.height() - r.height())
                self.norm(QRectF(x, y, r.width(), r.height()))

        def mouseReleaseEvent(self, e):
            if self.mode == "draw":
                s = self.dlg.sel
                if s[2] < 0.03 or s[3] < 0.03:
                    self.dlg.sel = [0.0, 0.0, 1.0, 1.0]
                    self.dlg.sample.update()
                    self.update()
            self.mode = None

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHints(AA)
            pal = self.dlg.panel.state.pal_target
            p.drawPixmap(0, 0, self.pm)
            r = self.px()
            shade = QPainterPath()
            shade.addRect(QRectF(self.rect()))
            hole = QPainterPath()
            hole.addRect(r)
            p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 150))
            p.setPen(QPen(pal.accent, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.accent)
            for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
            p.end()

    class Sample(QWidget):
        def __init__(self, dlg):
            super().__init__()
            self.dlg = dlg
            self.setFixedHeight(96)

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHints(AA)
            pal = self.dlg.panel.state.pal_target
            p.fillRect(self.rect(), with_alpha(pal.bg, 255))
            img = self.dlg.img
            s = self.dlg.sel
            iw = img.width()
            ih = img.height()
            x = int(s[0] * iw)
            y = int(s[1] * ih)
            w = max(1, min(iw - x, int(s[2] * iw)))
            h = max(1, min(ih - y, int(s[3] * ih)))
            crop = img.copy(QRect(x, y, w, h))
            tex = cover_fit(crop, self.width(), self.height(), 0)
            font = self.dlg.panel.ctl.theme.font(44, QFont.Weight.Bold)
            path = QPainterPath()
            fm = QFontMetrics(font)
            text = "Your lyrics"
            path.addText(self.width() / 2.0 - fm.horizontalAdvance(text) / 2.0, self.height() / 2.0 + fm.ascent() / 2.6, font, text)
            p.fillPath(path, QBrush(tex))
            p.end()

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle("Text image area")
        apply_qss(self, panel.state.pal_target, panel.ctl.theme.family)
        self.img = QImage(panel.cfg["text_image"])
        self.sel = [float(v) for v in panel.cfg["text_image_rect"]]
        if len(self.sel) != 4:
            self.sel = [0.0, 0.0, 1.0, 1.0]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        hint = QLabel("Drag on the image to choose the area that fills your text. Drag inside the box to move it.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        if self.img.isNull():
            self.img = QImage(8, 8, QImage.Format.Format_RGB32)
            self.img.fill(QColor(80, 80, 80))
        scaled = self.img.scaled(self.MAXW, self.MAXH, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.sample = TextAreaDialog.Sample(self)
        self.canvas = TextAreaDialog.Canvas(self, QPixmap.fromImage(scaled))
        lay.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.sample)
        row = QHBoxLayout()
        full = QPushButton("Full image")
        full.clicked.connect(self.reset_sel)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply")
        ok.setObjectName("primary")
        ok.clicked.connect(self.apply_sel)
        for b in (full, cancel, ok):
            b.setAutoDefault(False)
        row.addWidget(full)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def reset_sel(self):
        self.sel = [0.0, 0.0, 1.0, 1.0]
        self.sample.update()
        self.canvas.update()

    def apply_sel(self):
        self.panel.cfg["text_image_rect"] = [round(float(v), 4) for v in self.sel]
        self.panel.ctl.refresh()
        self.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            e.accept()
            return
        super().keyPressEvent(e)


class PicCropDialog(QDialog):
    MAXW = 560
    MAXH = 340
    MINS = 24.0

    class Canvas(QWidget):
        def __init__(self, dlg, pm):
            super().__init__()
            self.dlg = dlg
            self.pm = pm
            self.mode = None
            self.anchor = QPointF()
            self.grab = QPointF()
            self.box = QRectF()
            self.setFixedSize(pm.width(), pm.height())
            self.setCursor(Qt.CursorShape.CrossCursor)

        def corner_hit(self, pos):
            b = self.box
            for pt, opp in (
                (b.topLeft(), b.bottomRight()),
                (b.topRight(), b.bottomLeft()),
                (b.bottomLeft(), b.topRight()),
                (b.bottomRight(), b.topLeft()),
            ):
                if abs(pos.x() - pt.x()) <= 12 and abs(pos.y() - pt.y()) <= 12:
                    return QPointF(opp)
            return None

        def place(self, side, cx, cy):
            side = clamp(side, self.dlg.MINS, float(min(self.width(), self.height())))
            x = clamp(cx - side / 2.0, 0.0, self.width() - side)
            y = clamp(cy - side / 2.0, 0.0, self.height() - side)
            self.box = QRectF(x, y, side, side)
            self.dlg.changed()
            self.update()

        def move_to(self, pos):
            x = clamp(pos.x() - self.grab.x(), 0.0, self.width() - self.box.width())
            y = clamp(pos.y() - self.grab.y(), 0.0, self.height() - self.box.height())
            self.box = QRectF(x, y, self.box.width(), self.box.height())
            self.dlg.changed()
            self.update()

        def mousePressEvent(self, e):
            if e.button() != Qt.MouseButton.LeftButton:
                return
            pos = e.position()
            opp = self.corner_hit(pos)
            if opp is not None:
                self.mode = "size"
                self.anchor = opp
                return
            self.mode = "move"
            if self.box.contains(pos):
                self.grab = pos - self.box.topLeft()
            else:
                self.grab = QPointF(self.box.width() / 2.0, self.box.height() / 2.0)
                self.move_to(pos)

        def mouseMoveEvent(self, e):
            if self.mode is None:
                return
            pos = QPointF(
                clamp(e.position().x(), 0.0, float(self.width())),
                clamp(e.position().y(), 0.0, float(self.height())),
            )
            if self.mode == "move":
                self.move_to(pos)
                return
            a = self.anchor
            dx = pos.x() - a.x()
            dy = pos.y() - a.y()
            sx = 1.0 if dx >= 0 else -1.0
            sy = 1.0 if dy >= 0 else -1.0
            limx = self.width() - a.x() if sx > 0 else a.x()
            limy = self.height() - a.y() if sy > 0 else a.y()
            side = clamp(max(abs(dx), abs(dy)), self.dlg.MINS, max(self.dlg.MINS, min(limx, limy)))
            x = a.x() if sx > 0 else a.x() - side
            y = a.y() if sy > 0 else a.y() - side
            self.box = QRectF(x, y, side, side)
            self.dlg.changed()
            self.update()

        def mouseReleaseEvent(self, e):
            self.mode = None

        def wheelEvent(self, e):
            step = 1.08 if e.angleDelta().y() > 0 else 1.0 / 1.08
            c = self.box.center()
            self.place(self.box.width() * step, c.x(), c.y())

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHints(AA)
            pal = self.dlg.panel.state.pal_target
            p.drawPixmap(0, 0, self.pm)
            r = self.box
            shade = QPainterPath()
            shade.addRect(QRectF(self.rect()))
            hole = QPainterPath()
            if self.dlg.panel.cfg["welcome_pic_shape"] == "rounded":
                hole.addRoundedRect(r, r.width() * 0.26, r.width() * 0.26)
            else:
                hole.addEllipse(r)
            p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 150))
            p.setPen(QPen(pal.accent, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.accent)
            for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawRect(QRectF(pt.x() - 5, pt.y() - 5, 10, 10))
            p.end()

    class Sample(QWidget):
        def __init__(self, dlg):
            super().__init__()
            self.dlg = dlg
            self.setFixedSize(110, 110)

        def paintEvent(self, e):
            p = QPainter(self)
            p.setRenderHints(AA)
            dlg = self.dlg
            px = max(2, int(100 * self.devicePixelRatioF()))
            pm = cover_fit(crop_frame(dlg.img, dlg.norm()), px, px, 0)
            r = QRectF(5, 5, 100, 100)
            path = QPainterPath()
            if dlg.panel.cfg["welcome_pic_shape"] == "rounded":
                path.addRoundedRect(r, 26, 26)
            else:
                path.addEllipse(r)
            p.setClipPath(path)
            p.drawPixmap(r, pm, QRectF(pm.rect()))
            p.end()

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle("Crop profile picture")
        apply_qss(self, panel.state.pal_target, panel.ctl.theme.family)
        self.img = QImage(panel.cfg["welcome_pic"])
        if self.img.isNull():
            self.img = QImage(8, 8, QImage.Format.Format_RGB32)
            self.img.fill(QColor(80, 80, 80))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        hint = QLabel("Drag the box to move it, drag a corner or use the mouse wheel to resize it. The preview shows exactly what the profile picture will look like.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        scaled = self.img.scaled(
            self.MAXW, self.MAXH, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.canvas = PicCropDialog.Canvas(self, QPixmap.fromImage(scaled))
        self.sample = PicCropDialog.Sample(self)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(5, 100)
        self.zoom.valueChanged.connect(self.on_zoom)
        lay.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        mid = QHBoxLayout()
        sl = QVBoxLayout()
        label = QLabel("Crop size")
        label.setObjectName("rowlabel")
        sl.addStretch(1)
        sl.addWidget(label)
        sl.addWidget(self.zoom)
        sl.addStretch(1)
        mid.addLayout(sl, 1)
        mid.addSpacing(16)
        mid.addWidget(self.sample)
        lay.addLayout(mid)
        row = QHBoxLayout()
        full = QPushButton("Reset")
        full.clicked.connect(self.reset_sel)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Apply")
        ok.setObjectName("primary")
        ok.clicked.connect(self.apply_sel)
        for b in (full, cancel, ok):
            b.setAutoDefault(False)
        row.addWidget(full)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.load_sel()

    def load_sel(self):
        W = float(self.canvas.width())
        H = float(self.canvas.height())
        try:
            r = [float(v) for v in self.panel.cfg["welcome_pic_rect"]]
        except (TypeError, ValueError):
            r = []
        if len(r) != 4 or (r[0] < 0.01 and r[1] < 0.01 and r[2] > 0.98 and r[3] > 0.98):
            self.canvas.place(min(W, H), W / 2.0, H / 2.0)
            return
        side = max(r[2] * W, r[3] * H)
        self.canvas.place(side, r[0] * W + r[2] * W / 2.0, r[1] * H + r[3] * H / 2.0)

    def norm(self):
        b = self.canvas.box
        W = float(self.canvas.width())
        H = float(self.canvas.height())
        return [
            clamp(b.left() / W, 0.0, 1.0),
            clamp(b.top() / H, 0.0, 1.0),
            clamp(b.width() / W, 0.01, 1.0),
            clamp(b.height() / H, 0.01, 1.0),
        ]

    def changed(self):
        side = float(min(self.canvas.width(), self.canvas.height()))
        self.zoom.blockSignals(True)
        self.zoom.setValue(int(round(100.0 * self.canvas.box.width() / max(1.0, side))))
        self.zoom.blockSignals(False)
        self.sample.update()

    def on_zoom(self, v):
        side = float(min(self.canvas.width(), self.canvas.height()))
        c = self.canvas.box.center()
        self.canvas.place(side * v / 100.0, c.x(), c.y())

    def reset_sel(self):
        self.panel.cfg["welcome_pic_rect"] = [0.0, 0.0, 1.0, 1.0]
        self.load_sel()

    def apply_sel(self):
        self.panel.cfg["welcome_pic_rect"] = [round(float(v), 4) for v in self.norm()]
        self.panel.ctl.refresh()
        self.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            e.accept()
            return
        super().keyPressEvent(e)
