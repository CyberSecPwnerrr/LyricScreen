import os
import math

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase

from lyricshud.paths import DEFAULT_FAMILY
from lyricshud.styles import QSS_TEMPLATE
from lyricshud.utils import clamp, mix


class Theme:
    def __init__(self, cfg):
        self.cfg = cfg
        self.version = 0
        self.family = DEFAULT_FAMILY
        self.font_ok = True
        self.loaded_path = None
        self.loaded_family = None
        self.reload()

    def reload(self):
        path = self.cfg["font_path"]
        self.font_ok = True
        if path and os.path.isfile(path):
            if path != self.loaded_path:
                fid = QFontDatabase.addApplicationFont(path)
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                self.loaded_path = path
                self.loaded_family = fams[0] if fams else None
            if self.loaded_family:
                self.family = self.loaded_family
            else:
                self.family = DEFAULT_FAMILY
                self.font_ok = False
        else:
            self.family = DEFAULT_FAMILY
            if path:
                self.font_ok = False
        self.version += 1

    def font(self, px, weight=QFont.Weight.Medium, spacing=0.0):
        f = QFont(self.family)
        f.setPixelSize(max(6, int(px)))
        f.setWeight(weight)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        if spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return f


class Palette:
    __slots__ = ("accent", "secondary", "bg", "surface", "text", "dim")

    def __init__(self, accent, secondary, text=None, bg=None):
        self.accent = QColor(accent)
        self.secondary = QColor(secondary)
        h = self.accent.hsvHueF()
        if h < 0:
            h = 0.0
        if bg is not None:
            self.bg = QColor(bg)
            self.surface = mix(mix(self.bg, QColor(255, 255, 255), 0.07), self.accent, 0.1)
        else:
            self.bg = QColor.fromHsvF(h % 1.0, 0.55, 0.075)
            self.surface = QColor.fromHsvF(h % 1.0, 0.45, 0.15)
        self.text = QColor(text) if text is not None else QColor.fromHsvF(h % 1.0, 0.07, 0.97)
        self.dim = mix(self.text, self.bg, 0.5)

    @staticmethod
    def blend(a, b, k):
        p = Palette.__new__(Palette)
        for n in Palette.__slots__:
            setattr(p, n, mix(getattr(a, n), getattr(b, n), k))
        return p

    def close_to(self, o):
        d = 0.0
        for n in ("accent", "secondary", "bg", "text"):
            a = getattr(self, n)
            b = getattr(o, n)
            d += abs(a.redF() - b.redF()) + abs(a.greenF() - b.greenF()) + abs(a.blueF() - b.blueF())
        return d < 0.012


def palette_from_image(img):
    small = img.scaled(
        40, 40, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    bins = [[0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(12)]
    for yy in range(40):
        for xx in range(40):
            h, s, v, _ = small.pixelColor(xx, yy).getHsvF()
            if h < 0 or s < 0.2 or v < 0.22:
                continue
            w = s * s * (0.3 + v)
            e = bins[int(h * 12) % 12]
            e[0] += w
            e[1] += math.cos(h * 6.2831853) * w
            e[2] += math.sin(h * 6.2831853) * w
            e[3] += s * w
            e[4] += v * w
    order = sorted(range(12), key=lambda i: bins[i][0], reverse=True)
    top = bins[order[0]]
    if top[0] < 1.5:
        return None

    def hsv_of(e):
        return (math.atan2(e[2], e[1]) / 6.2831853) % 1.0, e[3] / e[0], e[4] / e[0]

    h1, s1, v1 = hsv_of(top)
    acc = QColor.fromHsvF(h1, clamp(s1 * 1.1, 0.6, 1.0), clamp(v1 * 1.1 + 0.1, 0.85, 1.0))
    sec = None
    for i in order[1:]:
        e = bins[i]
        if e[0] < top[0] * 0.22:
            break
        h2, s2, v2 = hsv_of(e)
        dh = abs(h2 - h1)
        dh = min(dh, 1.0 - dh)
        if dh >= 0.09:
            sec = QColor.fromHsvF(h2, clamp(s2 * 1.1, 0.6, 1.0), clamp(v2 * 1.1 + 0.1, 0.85, 1.0))
            break
    if sec is None:
        sec = QColor.fromHsvF((h1 + 0.45) % 1.0, 0.8, 1.0)
    return Palette(acc, sec)


def apply_qss(widget, pal, family=None):
    q = build_qss(pal, family)
    if getattr(widget, "applied_qss", None) != q:
        widget.applied_qss = q
        widget.setStyleSheet(q)


def build_qss(pal, family=None):
    def rgba(c, a):
        return f"rgba({c.red()},{c.green()},{c.blue()},{a})"

    bg2 = mix(pal.bg, pal.surface, 0.45)
    line = mix(pal.surface, pal.accent, 0.22)
    rep = {
        "@BG@": pal.bg.name(),
        "@BG2@": bg2.name(),
        "@BG2A@": rgba(bg2, 190),
        "@SFA@": rgba(pal.surface, 215),
        "@SF@": pal.surface.name(),
        "@LINE@": line.name(),
        "@ACC@": pal.accent.name(),
        "@SEC@": pal.secondary.name(),
        "@TX@": pal.text.name(),
        "@DIM@": mix(pal.text, pal.bg, 0.42).name(),
        "@ACCA@": rgba(pal.accent, 60),
        "@ACCA2@": rgba(pal.accent, 90),
        "@FAM@": str(family or DEFAULT_FAMILY).replace('"', ""),
    }
    out = QSS_TEMPLATE
    for k, v in rep.items():
        out = out.replace(k, v)
    return out
