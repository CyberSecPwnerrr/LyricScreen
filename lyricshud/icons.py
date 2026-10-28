from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainterPath, QPen, QFont


def icon_pen(col, w=1.7):
    pen = QPen(col, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def icon_play(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    path = QPainterPath()
    path.moveTo(-4, -7)
    path.lineTo(7, 0)
    path.lineTo(-4, 7)
    path.closeSubpath()
    p.setPen(icon_pen(col, 1.6))
    p.setBrush(col)
    p.drawPath(path)
    p.restore()


def icon_pause(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawRoundedRect(QRectF(-6, -7, 4.2, 14), 1.4, 1.4)
    p.drawRoundedRect(QRectF(1.8, -7, 4.2, 14), 1.4, 1.4)
    p.restore()


def icon_skip(p, cx, cy, s, col, flip=False, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(-k if flip else k, k)
    path = QPainterPath()
    path.moveTo(7, -6.5)
    path.lineTo(-3.5, 0)
    path.lineTo(7, 6.5)
    path.closeSubpath()
    p.setPen(icon_pen(col, 1.4))
    p.setBrush(col)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(-8, -6.5, 2.6, 13), 1.1, 1.1)
    p.restore()


def icon_prev(p, cx, cy, s, col, **kw):
    icon_skip(p, cx, cy, s, col, False)


def icon_next(p, cx, cy, s, col, **kw):
    icon_skip(p, cx, cy, s, col, True)


def icon_shuffle(p, cx, cy, s, col, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    a = QPainterPath()
    a.moveTo(-8, -4)
    a.lineTo(-4, -4)
    a.cubicTo(0, -4, 0, 4, 4, 4)
    a.lineTo(5.5, 4)
    b = QPainterPath()
    b.moveTo(-8, 4)
    b.lineTo(-4, 4)
    b.cubicTo(0, 4, 0, -4, 4, -4)
    b.lineTo(5.5, -4)
    p.setPen(icon_pen(col, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(a)
    p.drawPath(b)
    p.setBrush(col)
    for yy in (-4, 4):
        tri = QPainterPath()
        tri.moveTo(5, yy - 3)
        tri.lineTo(9, yy)
        tri.lineTo(5, yy + 3)
        tri.closeSubpath()
        p.drawPath(tri)
    p.restore()


def icon_repeat(p, cx, cy, s, col, mode=0, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    p.setPen(icon_pen(col, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-7, -4.5, 14, 9), 3.2, 3.2)
    p.setBrush(col)
    t1 = QPainterPath()
    t1.moveTo(1, -7.8)
    t1.lineTo(5.2, -4.5)
    t1.lineTo(1, -1.2)
    t1.closeSubpath()
    t2 = QPainterPath()
    t2.moveTo(-1, 1.2)
    t2.lineTo(-5.2, 4.5)
    t2.lineTo(-1, 7.8)
    t2.closeSubpath()
    p.drawPath(t1)
    p.drawPath(t2)
    if mode == 1:
        f = QFont("Segoe UI", 1)
        f.setPixelSize(8)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(-4, -4, 8, 8), Qt.AlignmentFlag.AlignCenter, "1")
    p.restore()


def icon_speaker(p, cx, cy, s, col, level=1.0, muted=False, **kw):
    p.save()
    p.translate(cx, cy)
    k = s / 16.0
    p.scale(k, k)
    body = QPainterPath()
    body.moveTo(-8, -2.8)
    body.lineTo(-4, -2.8)
    body.lineTo(0.5, -6.5)
    body.lineTo(0.5, 6.5)
    body.lineTo(-4, 2.8)
    body.lineTo(-8, 2.8)
    body.closeSubpath()
    p.setPen(icon_pen(col, 1.2))
    p.setBrush(col)
    p.drawPath(body)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(icon_pen(col, 1.6))
    if muted or level <= 0.01:
        p.drawLine(QPointF(3.5, -3), QPointF(8.5, 3))
        p.drawLine(QPointF(8.5, -3), QPointF(3.5, 3))
    else:
        w1 = QPainterPath()
        w1.moveTo(3.5, -3)
        w1.cubicTo(5.5, -1.5, 5.5, 1.5, 3.5, 3)
        p.drawPath(w1)
        if level > 0.5:
            w2 = QPainterPath()
            w2.moveTo(5.8, -6)
            w2.cubicTo(9.5, -3, 9.5, 3, 5.8, 6)
            p.drawPath(w2)
    p.restore()
