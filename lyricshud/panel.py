from PyQt6.QtCore import Qt, QTimer, QRectF, QAbstractAnimation, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QButtonGroup,
    QLabel,
    QSlider,
    QComboBox,
    QColorDialog,
)

from lyricshud.fonts import dark_titlebar
from lyricshud.painters import MenuPaint
from lyricshud.styles import AA
from lyricshud.widgets import PageLay, Switch


class Panel(QDialog, MenuPaint):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.state = ctl.state
        self.switches = []
        self.manual = []
        self.menu_init()
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(66)
        self.anim_timer.timeout.connect(self.tick_anim)

    def tick_anim(self):
        if self.cfg["menu_anim"] and self.cfg["optimize"] != "performance":
            self.update()

    def fade_in(self):
        if not self.cfg["menu_anim"]:
            return
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(300)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def showEvent(self, e):
        dark_titlebar(self, self.state.pal_target)
        self.anim_timer.start()
        self.fade_in()
        super().showEvent(e)

    def hideEvent(self, e):
        self.anim_timer.stop()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            e.accept()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(AA)
        self.paint_menu(p, QRectF(self.rect()), 0.0, self.state.pal_target)

    def sec(self, lay, text):
        if isinstance(lay, PageLay):
            lay.begin(text)
            return
        l = QLabel(text.upper())
        l.setObjectName("section")
        lay.addWidget(l)

    def row(self, lay, label, widget, hint=""):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 3, 0, 3)
        left = QVBoxLayout()
        left.setSpacing(2)
        l = QLabel(label)
        l.setObjectName("rowlabel")
        left.addWidget(l)
        if hint:
            hl = QLabel(hint)
            hl.setObjectName("hint")
            hl.setWordWrap(True)
            left.addWidget(hl)
        h.addLayout(left, 1)
        h.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(w)
        return w

    def set_val(self, key, value, refresh=True):
        self.cfg[key] = value
        if refresh:
            self.ctl.refresh()
        else:
            self.cfg.save()

    def switch(self, key, after=None):
        s = Switch(self.state)
        s.setChecked(bool(self.cfg[key]))

        def toggled(v):
            self.set_val(key, bool(v))
            if after:
                after()

        s.toggled.connect(toggled)
        self.switches.append(s)
        return s

    def slider(self, key, lo, hi, suffix=""):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(self.cfg[key]))
        s.setFixedWidth(200)
        lab = QLabel(f"{int(self.cfg[key])}{suffix}")
        lab.setFixedWidth(64)
        lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        def changed(v):
            lab.setText(f"{v}{suffix}")
            self.set_val(key, v)

        s.valueChanged.connect(changed)
        box = QWidget()
        l = QHBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(s)
        l.addWidget(lab)
        return box

    def color(self, key):
        b = QPushButton()
        b.setFixedWidth(120)

        def paint():
            c = QColor(self.cfg[key])
            fg = "#000" if c.lightness() > 140 else "#fff"
            b.setText(c.name().upper())
            b.setStyleSheet(
                f"QPushButton{{background:{c.name()};color:{fg};border:1px solid rgba(255,255,255,40);border-radius:9px;padding:7px;font-weight:700;}}"
            )

        def pick():
            c = QColorDialog.getColor(QColor(self.cfg[key]), self, "Pick color")
            if c.isValid():
                self.cfg[key] = c.name()
                paint()
                self.ctl.refresh()

        b.clicked.connect(pick)
        paint()
        self.manual.append(b)
        return b

    def combo(self, key, items, cast=None):
        c = QComboBox()
        c.setFixedWidth(200)
        for label, val in items:
            c.addItem(label, val)
        c.setCurrentIndex(max(0, c.findData(self.cfg[key])))
        c.currentIndexChanged.connect(lambda _: self.set_val(key, c.currentData()))
        return c

    def segmented(self, key, items):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        group = QButtonGroup(box)
        group.setExclusive(True)
        for label, val in items:
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(self.cfg[key] == val)
            b.clicked.connect(lambda _=False, v=val: self.set_val(key, v))
            group.addButton(b)
            h.addWidget(b)
        return box
