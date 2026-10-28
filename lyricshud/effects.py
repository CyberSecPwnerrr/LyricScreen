import math

from PyQt6.QtGui import QColor

from lyricshud.themes import RANDOM_ENTER, RANDOM_EXIT, random_pick
from lyricshud.utils import clamp, ease, mix


def ease_back(x):
    x = clamp(x, 0.0, 1.0) - 1.0
    return 1.0 + 2.70158 * x * x * x + 1.70158 * x * x


def shape_colors(acc, sec, mode):
    white = QColor(255, 255, 255)
    black = QColor(0, 0, 0)
    if mode == "pastel":
        return mix(acc, white, 0.4), mix(sec, white, 0.4)
    if mode == "deep":
        return mix(acc, black, 0.28), mix(sec, black, 0.28)
    if mode == "mono":
        return acc, mix(acc, white, 0.5)
    h, s, v, _ = acc.getHsvF()
    shift = {"complement": 0.5, "triad": 1.0 / 3.0, "analog": 0.08}.get(mode)
    if shift is None:
        return acc, sec
    return acc, QColor.fromHsvF((max(0.0, h) + shift) % 1.0, clamp(s, 0.6, 1.0), 1.0)


def line_fx(cfg, enter, eo, side, t, i, life=0.0, nx=0.0, ny=0.0):
    mo = cfg["motion"] / 100.0
    es = cfg["enter_style"]
    if es == "random":
        es = random_pick(RANDOM_ENTER, i, 1)
    k = 1.0 - enter
    ox = oy = rx = rz = 0.0
    sc = sx = 1.0
    if es == "rise":
        oy = 44.0 * mo * k
    elif es == "drop":
        oy = -44.0 * mo * k
    elif es == "zoom":
        sc = 1.0 - 0.24 * mo * k
    elif es == "flip":
        rx = 80.0 * mo * k
    elif es == "bounce":
        kb = 1.0 - ease_back(enter)
        sc = 1.0 - 0.45 * mo * kb
        oy = 24.0 * mo * kb
    elif es == "stretch":
        sx = 1.0 - 0.7 * mo * k
    elif es == "swing":
        rz = -14.0 * mo * k
        oy = 20.0 * mo * k
    elif es == "spin":
        rz = 90.0 * mo * k
        sc = 1.0 - 0.3 * mo * k
    elif es == "classic":
        ox = side * 60.0 * mo * k
        oy = 30.0 * mo * k if side == 0 else 0.0
        sc = 1.0 - 0.06 * mo * k
    elif es == "left":
        ox = -90.0 * mo * k
    elif es == "right":
        ox = 90.0 * mo * k
    elif es == "pop":
        kb = 1.0 - ease_back(enter)
        sc = 1.0 - 0.6 * mo * kb
    elif es == "settle":
        sc = 1.0 + 0.35 * mo * k
    elif es == "twist":
        rz = 28.0 * mo * k
        sc = 1.0 - 0.2 * mo * k
    elif es == "wave":
        oy = 26.0 * mo * k * math.sin(k * 9.0)
    e = ease(eo)
    xs = cfg["exit_style"]
    if xs == "random":
        xs = random_pick(RANDOM_EXIT, i, 2)
    if xs == "shrink":
        sc *= 1.0 - 0.18 * mo * e
    elif xs == "drop":
        oy += 24.0 * mo * e
    elif xs == "slide":
        ox += (side or 1) * 70.0 * mo * e
    elif xs == "float":
        oy -= 20.0 * mo * e
        sc *= 1.0 + 0.03 * mo * e
    elif xs == "rise":
        oy -= 46.0 * mo * e
    elif xs == "grow":
        sc *= 1.0 + 0.28 * mo * e
    elif xs == "spin":
        rz += 70.0 * mo * e
        sc *= 1.0 - 0.15 * mo * e
    elif xs == "next":
        if abs(nx) + abs(ny) < 1.0:
            oy -= 28.0 * mo * e
        else:
            ox += nx * min(1.0, mo) * e
            oy += ny * min(1.0, mo) * e
        sc *= 1.0 - 0.05 * mo * e
    idle = cfg["idle_anim"]
    if idle == "float":
        oy += math.sin(t * 1.2 + i) * 5.0 * min(1.0, mo)
    elif idle == "pulse":
        sc *= 1.0 + 0.015 * mo * math.sin(t * 2.4 + i)
    elif idle == "sway":
        rz += math.sin(t * 0.9 + i) * 1.6 * min(1.0, mo)
    elif idle == "breathe":
        sc *= 1.0 + 0.035 * mo * math.sin(t * 1.3 + i)
    elif idle == "wobble":
        rz += math.sin(t * 2.2 + i) * 2.6 * min(1.0, mo)
        ox += math.sin(t * 1.1 + i) * 4.0 * min(1.0, mo)
    elif idle == "drift":
        ox += math.sin(t * 0.7 + i) * 9.0 * min(1.0, mo)
        oy += math.cos(t * 0.5 + i) * 4.0 * min(1.0, mo)
    drift = cfg["lyric_drift"]
    if drift == "up" or drift == "down":
        span = float(cfg["lyric_drift_px"]) * min(1.0, mo) * (life - 0.5)
        oy += -span if drift == "up" else span
    return ox, oy, sc, sx, rx, rz
