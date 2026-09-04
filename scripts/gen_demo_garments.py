"""Процедурные товарные иллюстрации для демо-магазина одежды (кит `clothing`).

Зачем свой генератор. Демо-фото платформы — CC0/PDM или AI-набор
(`static/demo/photos/README.md`). Для одежды честного CC0-набора не существует:
прогон Openverse (`license=cc0,pdm`) по 68 запросам дал открытки, музейные
экспонаты и снимки людей с узнаваемыми лицами — товарной съёмки там нет, а
ключа генеративной модели в окружении нет. Поэтому иллюстрации рисуются
детерминированно: единый «студийный flat-lay» — силуэт вещи, фактура ткани,
мягкая тень, зерно бумаги.

Что это даёт демо: (1) единый стиль на весь каталог, как у настоящего бренда;
(2) ЦВЕТ картинки = цвет варианта (реестр `catalog.option_styles.COLOR_HEX`),
поэтому выбор «Sand» на карточке реально меняет изображение; (3) никаких
лицензионных и GDPR-вопросов; (4) ~6 КБ на файл.

Запуск (файлы пишутся в static/demo/photos/, имена = ключи фото кита):

    uv run python scripts/gen_demo_garments.py

Идемпотентно: одна и та же спека даёт байт-в-байт тот же файл. После прогона
демо надо пересеять — URL пишется при сидинге:

    python manage.py seed_demo_tenants --kit clothing --recreate
"""

from __future__ import annotations

import math
import os
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 3


# ---------------- геометрия ----------------
def cub(p0, p1, p2, p3, n=26):
    out = []
    for i in range(n):
        t = i / (n - 1)
        mt = 1 - t
        out.append(
            (
                mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
                mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


class P:
    """Мини-путь в нормированных координатах (0..1)."""

    def __init__(self, start):
        self.pts = [start]

    def ln(self, p):
        self.pts.append(p)
        return self

    def c(self, c1, c2, p):
        self.pts += cub(self.pts[-1], c1, c2, p)[1:]
        return self

    def q(self, c, p):
        a = self.pts[-1]
        c1 = (a[0] + 2 / 3 * (c[0] - a[0]), a[1] + 2 / 3 * (c[1] - a[1]))
        c2 = (p[0] + 2 / 3 * (c[0] - p[0]), p[1] + 2 / 3 * (c[1] - p[1]))
        return self.c(c1, c2, p)

    def done(self):
        return self.pts


def mir(pts):
    return [(1 - x, y) for x, y in reversed(pts)]


def sym(right):
    """Правая половина (сверху вниз) → замкнутый симметричный контур."""
    return right + mir(right)


def scale(pts, w, h):
    return [(x * w, y * h) for x, y in pts]


# ---------------- цвет ----------------
def hx(c):
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))


def sh(rgb, f):
    if f >= 0:
        return tuple(min(255, int(v + (255 - v) * f)) for v in rgb)
    return tuple(max(0, int(v * (1 + f))) for v in rgb)


def luma(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


# ---------------- силуэты ----------------
def _top(
    *,
    sleeve="short",
    body=0.60,
    hem_w=0.30,
    shoulder=0.175,
    neck=0.055,
    waist=0.0,
    hemline=0.012,
    open_front=False,
):
    """Верх: футболка/свитер/рубашка/кардиган. Возвращает (контур, вырез)."""
    shy = 0.205
    shx = 0.5 + shoulder
    if sleeve == "short":
        cuff_y, cuff_x, arm_y = shy + 0.155, 0.5 + 0.298, shy + 0.185
    elif sleeve == "long":
        cuff_y, cuff_x, arm_y = shy + 0.425, 0.5 + 0.272, shy + 0.275
    else:  # sleeveless
        cuff_y, cuff_x, arm_y = shy + 0.02, shx, shy + 0.16
    hem_y = shy + body
    p = P((0.5 + neck * 1.45, shy - 0.018))
    p.q((0.5 + shoulder * 0.62, shy - 0.028), (shx, shy + 0.008))  # плечо
    if sleeve != "sleeveless":
        p.c(
            (shx + 0.075, shy + 0.045), (cuff_x - 0.012, cuff_y - 0.115), (cuff_x, cuff_y - 0.055)
        )  # внешний шов рукава
        p.q((cuff_x + 0.004, cuff_y + 0.010), (cuff_x - 0.042, cuff_y + 0.016))  # манжета
        p.c(
            (cuff_x - 0.10, cuff_y - 0.05), (shx - 0.048, arm_y - 0.055), (shx - 0.055, arm_y)
        )  # внутренний шов
    else:
        p.c((shx - 0.01, shy + 0.06), (shx - 0.045, arm_y - 0.05), (shx - 0.055, arm_y))
    side_x = 0.5 + hem_w / 2
    mid = (0.5 + hem_w / 2 - waist, shy + body * 0.55)
    p.c((shx - 0.062, arm_y + 0.06), (mid[0], mid[1] - 0.06), mid)
    p.q((side_x - 0.004, hem_y - 0.06), (side_x, hem_y))  # бок к подолу
    right = p.done()
    hemc = P((side_x, hem_y)).q((0.5, hem_y + hemline * 2.4), (0.5 - hem_w / 2, hem_y)).done()
    outline = right + hemc[1:] + mir(right)[1:]
    neck_sh = (
        P((0.5 - neck * 1.45, shy - 0.018))
        .q((0.5, shy + neck * 2.0), (0.5 + neck * 1.45, shy - 0.018))
        .done()
    )
    front = None
    if open_front:
        front = [(0.5, shy + neck * 0.6), (0.5, hem_y + hemline)]
    return (
        outline,
        neck_sh,
        front,
        dict(
            shy=shy, hem_y=hem_y, shx=shx, hem_w=hem_w, cuff_y=cuff_y, cuff_x=cuff_x, sleeve=sleeve
        ),
    )


def _pants(*, leg=0.60, waist=0.285, hip=0.325, cuff=0.105, crotch=0.30, short=False):
    top = 0.155
    hip_y = top + 0.155
    hem_y = top + (0.42 if short else leg + 0.10)
    cr_y = top + (0.30 if short else crotch)
    p = P((0.5 + waist / 2, top))
    p.q((0.5 + hip / 2 + 0.012, top + 0.09), (0.5 + hip / 2, hip_y))
    p.c(
        (0.5 + hip / 2 - 0.004, hip_y + (hem_y - hip_y) * 0.45),
        (0.5 + cuff + 0.055, hem_y - 0.12),
        (0.5 + cuff + 0.052, hem_y),
    )
    p.ln((0.5 + 0.032, hem_y))
    p.c((0.5 + 0.030, hem_y - 0.18), (0.5 + 0.026, cr_y + 0.05), (0.5 + 0.020, cr_y))
    right = p.done()
    outline = right + [(0.5 - 0.020, cr_y)] + mir(right)[:-1]
    return outline, None, None, dict(top=top, hem_y=hem_y, cr_y=cr_y, hip_y=hip_y, waist=waist)


def _skirt(*, flare=0.50, length=0.50, waist=0.255):
    top = 0.215
    hem = top + length
    p = P((0.5 + waist / 2, top)).c(
        (0.5 + waist / 2 + 0.035, top + length * 0.4),
        (0.5 + flare / 2 - 0.03, hem - length * 0.25),
        (0.5 + flare / 2, hem),
    )
    right = p.done()
    hemc = P((0.5 + flare / 2, hem)).q((0.5, hem + 0.05), (0.5 - flare / 2, hem)).done()
    return right + hemc[1:] + mir(right)[1:], None, None, dict(top=top, hem_y=hem, waist=waist)


def _dress(*, flare=0.44, length=0.66, neck=0.05, sleeve="sleeveless"):
    out, nk, _, m = _top(sleeve=sleeve, body=0.24, hem_w=0.185, neck=neck, shoulder=0.135)
    shy = m["shy"]
    waist_y = shy + 0.245
    hem = shy + length
    # заново: верх до талии + юбка
    p = P((0.5 + neck * 1.45, shy - 0.018))
    p.q((0.5 + 0.085, shy - 0.03), (0.5 + 0.135, shy + 0.01))
    if sleeve == "sleeveless":
        p.c((0.5 + 0.128, shy + 0.06), (0.5 + 0.105, shy + 0.10), (0.5 + 0.098, shy + 0.135))
    else:
        p.c((0.5 + 0.215, shy + 0.05), (0.5 + 0.245, shy + 0.15), (0.5 + 0.238, shy + 0.20))
        p.q((0.5 + 0.185, shy + 0.215), (0.5 + 0.178, shy + 0.19))
        p.c((0.5 + 0.15, shy + 0.145), (0.5 + 0.105, shy + 0.115), (0.5 + 0.098, shy + 0.135))
    p.q((0.5 + 0.092, waist_y - 0.05), (0.5 + 0.088, waist_y))
    p.c(
        (0.5 + 0.16, waist_y + (hem - waist_y) * 0.4),
        (0.5 + flare / 2 - 0.02, hem - 0.14),
        (0.5 + flare / 2, hem),
    )
    right = p.done()
    hemc = P((0.5 + flare / 2, hem)).q((0.5, hem + 0.055), (0.5 - flare / 2, hem)).done()
    neck_sh = (
        P((0.5 - neck * 1.45, shy - 0.018))
        .q((0.5, shy + neck * 2.1), (0.5 + neck * 1.45, shy - 0.018))
        .done()
    )
    return (
        right + hemc[1:] + mir(right)[1:],
        neck_sh,
        None,
        dict(shy=shy, hem_y=hem, waist_y=waist_y),
    )


# ---------------- аксессуары ----------------
def _beanie():
    cy = 0.66
    p = P((0.5 - 0.285, cy))
    p.c((0.5 - 0.285, cy - 0.40), (0.5 + 0.285, cy - 0.40), (0.5 + 0.285, cy))
    dome = p.done()
    return (
        dome + [(0.5 + 0.285, cy + 0.115), (0.5 - 0.285, cy + 0.115)],
        None,
        None,
        dict(cuff_y=cy, r=0.285),
    )


def _scarf():
    p = P((0.235, 0.255))
    p.c((0.42, 0.30), (0.58, 0.30), (0.765, 0.255))
    p.ln((0.765, 0.62))
    p.c((0.58, 0.665), (0.42, 0.665), (0.235, 0.62))
    return p.done(), None, None, dict(top=0.255, bot=0.62)


def _bag():
    p = P((0.265, 0.395))
    p.c((0.27, 0.60), (0.28, 0.72), (0.315, 0.80))
    p.q((0.5, 0.835), (0.685, 0.80))
    p.c((0.72, 0.72), (0.73, 0.60), (0.735, 0.395))
    return p.done(), None, None, dict(top=0.395)


def _belt():
    return [(0.16, 0.44), (0.84, 0.44), (0.84, 0.56), (0.16, 0.56)], None, None, dict()


def _socks():
    p = P((0.40, 0.235))
    p.ln((0.60, 0.235))
    p.c((0.605, 0.46), (0.60, 0.55), (0.615, 0.635))
    p.q((0.78, 0.665), (0.775, 0.755))
    p.q((0.77, 0.80), (0.66, 0.795))
    p.c((0.52, 0.79), (0.395, 0.72), (0.395, 0.55))
    return p.done(), None, None, dict()


def _sneaker():
    p = P((0.17, 0.66))
    p.c((0.20, 0.50), (0.30, 0.44), (0.42, 0.455))
    p.c((0.52, 0.47), (0.60, 0.52), (0.74, 0.575))
    p.c((0.83, 0.605), (0.855, 0.63), (0.855, 0.68))
    p.q((0.855, 0.735), (0.79, 0.735))
    p.ln((0.235, 0.735))
    p.q((0.17, 0.735), (0.17, 0.66))
    return p.done(), None, None, dict()


def _cap():
    p = P((0.245, 0.575))
    p.c((0.245, 0.355), (0.755, 0.355), (0.755, 0.575))
    p.q((0.86, 0.585), (0.865, 0.645))
    p.q((0.86, 0.665), (0.72, 0.655))
    p.q((0.5, 0.645), (0.245, 0.62))
    return p.done(), None, None, dict()


def _glove():
    p = P((0.36, 0.76))
    p.ln((0.355, 0.50))
    p.q((0.355, 0.415), (0.40, 0.415))
    p.q((0.44, 0.415), (0.44, 0.50))
    p.ln((0.445, 0.395))
    p.q((0.447, 0.30), (0.492, 0.30))
    p.q((0.537, 0.30), (0.535, 0.395))
    p.ln((0.54, 0.415))
    p.q((0.545, 0.325), (0.588, 0.325))
    p.q((0.63, 0.325), (0.628, 0.42))
    p.ln((0.633, 0.47))
    p.q((0.64, 0.40), (0.678, 0.405))
    p.q((0.715, 0.41), (0.71, 0.50))
    p.c((0.705, 0.60), (0.70, 0.70), (0.685, 0.76))
    return p.done(), None, None, dict()


def _sunglasses():
    return None, None, None, dict(kind="sunglasses")


def _bottle_bag():  # рюкзак
    p = P((0.28, 0.42))
    p.q((0.28, 0.32), (0.375, 0.315))
    p.q((0.5, 0.30), (0.625, 0.315))
    p.q((0.72, 0.32), (0.72, 0.42))
    p.c((0.735, 0.60), (0.735, 0.72), (0.71, 0.80))
    p.q((0.5, 0.835), (0.29, 0.80))
    p.c((0.265, 0.72), (0.265, 0.60), (0.28, 0.42))
    return p.done(), None, None, dict()


SHAPES = {
    "tshirt": lambda: _top(sleeve="short"),
    "longsleeve": lambda: _top(sleeve="long", body=0.60),
    "polo": lambda: _top(sleeve="short", neck=0.045),
    "shirt": lambda: _top(sleeve="long", body=0.635, hem_w=0.29, neck=0.045),
    "blouse": lambda: _top(sleeve="long", body=0.575, hem_w=0.305, neck=0.062, shoulder=0.16),
    "sweater": lambda: _top(sleeve="long", body=0.575, hem_w=0.325, neck=0.052),
    "cardigan": lambda: _top(sleeve="long", body=0.645, hem_w=0.315, neck=0.075, open_front=True),
    "hoodie": lambda: _top(sleeve="long", body=0.60, hem_w=0.335, neck=0.07),
    "jacket": lambda: _top(sleeve="long", body=0.605, hem_w=0.315, neck=0.065, open_front=True),
    "coat": lambda: _top(sleeve="long", body=0.70, hem_w=0.33, neck=0.07, open_front=True),
    "vest": lambda: _top(
        sleeve="sleeveless", body=0.50, hem_w=0.30, neck=0.062, shoulder=0.155, open_front=True
    ),
    "top": lambda: _top(sleeve="sleeveless", body=0.47, hem_w=0.245, neck=0.07, shoulder=0.12),
    "jeans": lambda: _pants(),
    "chinos": lambda: _pants(cuff=0.098, leg=0.585),
    "trousers": lambda: _pants(cuff=0.125, leg=0.60, hip=0.34),
    "shorts": lambda: _pants(short=True, cuff=0.135),
    "skirt": lambda: _skirt(),
    "dress": lambda: _dress(),
    "dress_sl": lambda: _dress(sleeve="long", flare=0.42),
    "beanie": _beanie,
    "scarf": _scarf,
    "bag": _bag,
    "backpack": _bottle_bag,
    "belt": _belt,
    "socks": _socks,
    "sneaker": _sneaker,
    "cap": _cap,
    "glove": _glove,
}


# ---------------- фактуры ----------------
def _texture(kind, w, h, rnd):
    """L-маска фактуры (128 = нейтраль)."""
    t = Image.new("L", (w, h), 128)
    d = ImageDraw.Draw(t)
    if kind == "strick":  # трикотаж: ряды V-образных петель
        step = int(0.020 * h)
        for i, y in enumerate(range(0, h, step)):
            off = (i % 2) * step // 2
            for x in range(-step, w + step, step):
                d.line(
                    [
                        (x + off, y + step * 0.62),
                        (x + off + step * 0.5, y),
                        (x + off + step, y + step * 0.62),
                    ],
                    fill=150,
                    width=max(1, int(0.0022 * h)),
                )
        t = t.filter(ImageFilter.GaussianBlur(0.0012 * h))
    elif kind == "denim":  # твил: диагональ
        step = int(0.0105 * h)
        for x in range(-h, w, step):
            d.line([(x, 0), (x + h, h)], fill=148, width=max(1, int(0.0016 * h)))
        t = t.filter(ImageFilter.GaussianBlur(0.0009 * h))
    elif kind == "cord":  # вельвет: вертикальные рубчики
        step = int(0.017 * w)
        for x in range(0, w, step):
            d.rectangle([x, 0, x + step * 0.45, h], fill=146)
        t = t.filter(ImageFilter.GaussianBlur(0.0022 * h))
    elif kind == "leder":
        n = Image.effect_noise((w // 4, h // 4), 26).resize((w, h), Image.BILINEAR)
        t = ImageChops.blend(t, n, 0.55).filter(ImageFilter.GaussianBlur(0.003 * h))
    elif kind == "leinen":  # лён: перекрёстное плетение
        step = max(2, int(0.0055 * h))
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=142, width=1)
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=140, width=1)
        t = t.filter(ImageFilter.GaussianBlur(0.0011 * h))
    else:  # хлопок/шёлк — тонкий шум
        n = Image.effect_noise((w // 3, h // 3), 12).resize((w, h), Image.BILINEAR)
        t = ImageChops.blend(t, n, 0.42).filter(ImageFilter.GaussianBlur(0.0016 * h))
    return t


# ---------------- детали ----------------
def _details(d, key, m, w, h, base, rnd, line):
    dark = sh(base, -0.30)
    mid = sh(base, -0.16)
    lite = sh(base, 0.22)

    def L(pts, col, wd):
        d.line([(x * w, y * h) for x, y in pts], fill=col, width=int(wd * S), joint="curve")

    if key in (
        "tshirt",
        "longsleeve",
        "polo",
        "shirt",
        "blouse",
        "sweater",
        "cardigan",
        "hoodie",
        "jacket",
        "coat",
        "vest",
        "top",
        "dress",
        "dress_sl",
    ):
        shy = m.get("shy", 0.205)
        hem_y = m.get("hem_y", 0.8)
        L(
            [
                (0.5 - m.get("hem_w", 0.30) / 2 + 0.012, hem_y - 0.020),
                (0.5 + m.get("hem_w", 0.30) / 2 - 0.012, hem_y - 0.020),
            ],
            mid + (90,),
            1.6,
        )
        if m.get("sleeve") == "long":
            cy, cx = m["cuff_y"], m["cuff_x"]
            for k in range(3):
                L(
                    [
                        (cx - 0.056 + 0.004 * k, cy + 0.012 - 0.012 * k),
                        (cx - 0.004, cy - 0.048 - 0.012 * k),
                    ],
                    mid + (80,),
                    1.4,
                )
                L(
                    [
                        (1 - (cx - 0.056 + 0.004 * k), cy + 0.012 - 0.012 * k),
                        (1 - (cx - 0.004), cy - 0.048 - 0.012 * k),
                    ],
                    mid + (80,),
                    1.4,
                )
    if key in ("shirt", "blouse"):
        L([(0.5 - 0.018, shy + 0.03), (0.5 - 0.018, hem_y - 0.02)], mid + (120,), 1.6)
        L([(0.5 + 0.018, shy + 0.03), (0.5 + 0.018, hem_y - 0.02)], mid + (120,), 1.6)
        for i in range(5):
            y = shy + 0.09 + i * (hem_y - shy - 0.14) / 4
            d.ellipse(
                [(0.5 - 0.010) * w, (y - 0.010) * h, (0.5 + 0.010) * w, (y + 0.010) * h],
                fill=lite + (255,),
                outline=dark + (180,),
                width=int(1.2 * S),
            )
        # воротник
        L(
            [(0.5 - 0.062, shy - 0.012), (0.5 - 0.028, shy + 0.055), (0.5, shy + 0.028)],
            dark + (200,),
            2.0,
        )
        L(
            [(0.5 + 0.062, shy - 0.012), (0.5 + 0.028, shy + 0.055), (0.5, shy + 0.028)],
            dark + (200,),
            2.0,
        )
    if key in ("cardigan", "jacket", "coat", "vest"):
        L([(0.5, shy + 0.02), (0.5, hem_y - 0.005)], dark + (150,), 2.0)
        for i in range(4):
            y = shy + 0.11 + i * (hem_y - shy - 0.20) / 3
            d.ellipse(
                [(0.5 - 0.028) * w, (y - 0.011) * h, (0.5 - 0.006) * w, (y + 0.011) * h],
                fill=lite + (255,),
                outline=dark + (190,),
                width=int(1.2 * S),
            )
    if key == "hoodie":
        L(
            [(0.5 - 0.115, shy + 0.005), (0.5, shy + 0.10), (0.5 + 0.115, shy + 0.005)],
            dark + (170,),
            2.4,
        )
        L(
            [
                (0.5 - 0.115, hem_y - 0.20),
                (0.5 - 0.105, hem_y - 0.075),
                (0.5 + 0.105, hem_y - 0.075),
                (0.5 + 0.115, hem_y - 0.20),
            ],
            mid + (140,),
            2.0,
        )
        for sgn in (-1, 1):
            L(
                [(0.5 + sgn * 0.022, shy + 0.075), (0.5 + sgn * 0.030, shy + 0.175)],
                lite + (220,),
                2.2,
            )
    if key in ("jeans", "chinos", "trousers", "shorts"):
        top, hem_y, cr_y = m["top"], m["hem_y"], m["cr_y"]
        L(
            [(0.5 - m["waist"] / 2, top + 0.030), (0.5 + m["waist"] / 2, top + 0.030)],
            mid + (140,),
            1.8,
        )
        L([(0.5 + 0.006, top + 0.030), (0.5 + 0.006, cr_y - 0.055)], mid + (150,), 1.6)  # ширинка
        if key == "jeans":
            for sgn in (-1, 1):
                L(
                    [
                        (0.5 + sgn * 0.055, top + 0.045),
                        (0.5 + sgn * 0.125, top + 0.045),
                        (0.5 + sgn * 0.105, top + 0.105),
                    ],
                    mid + (120,),
                    1.5,
                )
        if key == "chinos":
            for sgn in (-1, 1):
                L([(0.5 + sgn * 0.075, cr_y), (0.5 + sgn * 0.070, hem_y - 0.01)], lite + (90,), 1.8)
        L(
            [(0.5 + 0.034, hem_y - 0.022), (0.5 + m.get("cuffx", 0.155), hem_y - 0.022)],
            mid + (90,),
            1.4,
        )
        L(
            [(0.5 - 0.034, hem_y - 0.022), (0.5 - m.get("cuffx", 0.155), hem_y - 0.022)],
            mid + (90,),
            1.4,
        )
    if key == "skirt":
        L(
            [(0.5 - m["waist"] / 2, m["top"] + 0.030), (0.5 + m["waist"] / 2, m["top"] + 0.030)],
            mid + (150,),
            2.0,
        )
    if key in ("dress", "dress_sl"):
        wy = m["waist_y"]
        L([(0.5 - 0.088, wy), (0.5 + 0.088, wy)], mid + (120,), 1.8)
    if key == "beanie":
        cy, r = m["cuff_y"], m["r"]
        d.rectangle(
            [(0.5 - r) * w, cy * h, (0.5 + r) * w, (cy + 0.115) * h], fill=sh(base, -0.10) + (255,)
        )
        for i in range(11):
            x = 0.5 - r + 0.006 + i * (2 * r - 0.012) / 10
            L([(x, cy + 0.008), (x, cy + 0.107)], dark + (80,), 1.6)
        d.ellipse(
            [(0.5 - 0.075) * w, (cy - 0.475) * h, (0.5 + 0.075) * w, (cy - 0.325) * h],
            fill=sh(base, 0.28) + (255,),
            outline=dark + (120,),
            width=int(1.4 * S),
        )
    if key == "scarf":
        for i in range(13):
            x = 0.245 + i * 0.041
            L([(x, 0.63 + 0.012 * math.sin(i)), (x, 0.70 + 0.012 * math.sin(i))], mid + (200,), 2.0)
    if key == "crossbody":
        L([(0.310, 0.556), (0.690, 0.556)], mid + (140,), 2.0)
        d.rectangle([0.472 * w, 0.520 * h, 0.528 * w, 0.566 * h], fill=sh(base, -0.34) + (255,))
    if key == "drawstring":
        L([(0.300, 0.404), (0.700, 0.404)], mid + (150,), 2.2)
        for i in range(6):
            x = 0.330 + i * 0.068
            L([(x, 0.398), (x, 0.436)], dark + (90,), 1.6)
    if key in ("bag", "backpack"):
        for sgn in (-1, 1):
            pts = cub(
                (0.5 + sgn * 0.155, 0.40),
                (0.5 + sgn * 0.175, 0.235),
                (0.5 + sgn * 0.055, 0.225),
                (0.5 + sgn * 0.052, 0.40),
                22,
            )
            d.line(
                [(x * w, y * h) for x, y in pts],
                fill=sh(base, -0.34) + (255,),
                width=int(5.5 * S),
                joint="curve",
            )
        if key == "backpack":
            L([(0.30, 0.58), (0.70, 0.58)], dark + (130,), 2.0)
    if key == "tank_noop":
        pass
    if key == "belt":
        d.rectangle(
            [0.80 * w, 0.405 * h, 0.905 * w, 0.595 * h],
            outline=sh((190, 170, 120), -0.1) + (255,),
            width=int(5 * S),
        )
        L([(0.855, 0.50), (0.72, 0.50)], sh((190, 170, 120), -0.1) + (255,), 4)
        for i in range(5):
            x = 0.22 + i * 0.028
            d.ellipse(
                [x * w - 4 * S, 0.495 * h - 4 * S, x * w + 4 * S, 0.495 * h + 4 * S],
                fill=dark + (200,),
            )
    if key == "socks":
        for dx in (-0.145, 0.075):
            L([(0.325 + dx, 0.262), (0.440 + dx, 0.262)], lite + (200,), 3.2)
            L([(0.325 + dx, 0.292), (0.440 + dx, 0.292)], lite + (200,), 3.2)
    if key == "sneaker":
        for i in range(4):
            x = 0.300 + i * 0.062
            L([(x, 0.512 + 0.026 * i), (x + 0.052, 0.556 + 0.026 * i)], dark + (150,), 2.6)
            L([(x + 0.052, 0.512 + 0.026 * i), (x, 0.556 + 0.026 * i)], dark + (150,), 2.6)
        L([(0.148, 0.722), (0.860, 0.722)], dark + (90,), 1.8)
        L([(0.560, 0.585), (0.700, 0.700)], mid + (120,), 2.2)
    if key == "cap":
        for sgn in (-1, 1):
            L([(0.5 + sgn * 0.128, 0.598), (0.5 + sgn * 0.062, 0.402)], dark + (110,), 1.8)
        L([(0.5, 0.600), (0.5, 0.388)], dark + (110,), 1.8)
        d.ellipse([0.488 * w, 0.392 * h, 0.512 * w, 0.416 * h], fill=sh(base, -0.18) + (255,))
    if key == "glove":
        L([(0.358, 0.726), (0.690, 0.726)], mid + (170,), 3.4)
        L([(0.400, 0.470), (0.690, 0.470)], mid + (110,), 2.0)


# ---------------- v2.2: детские и мелкие формы ----------------
def _onesie():
    shy = 0.185
    shx = 0.5 + 0.165
    p = P((0.5 + 0.075, shy - 0.014))
    p.q((0.5 + 0.115, shy - 0.024), (shx, shy + 0.010))
    p.c((shx + 0.070, shy + 0.045), (shx + 0.076, shy + 0.125), (shx + 0.070, shy + 0.165))
    p.q((shx + 0.030, shy + 0.180), (shx + 0.012, shy + 0.148))
    p.c((shx - 0.030, shy + 0.105), (shx - 0.052, shy + 0.092), (shx - 0.058, shy + 0.130))
    p.c((0.5 + 0.112, shy + 0.230), (0.5 + 0.118, shy + 0.300), (0.5 + 0.120, shy + 0.345))
    p.q((0.5 + 0.122, shy + 0.395), (0.5 + 0.072, shy + 0.398))  # низ правой ножки
    p.ln((0.5 + 0.022, shy + 0.395))
    p.q((0.5 + 0.018, shy + 0.330), (0.5, shy + 0.318))
    right = p.done()
    outline = right + mir(right)[1:]
    neck = P((0.5 - 0.075, shy - 0.014)).q((0.5, shy + 0.062), (0.5 + 0.075, shy - 0.014)).done()
    return (
        outline,
        neck,
        None,
        dict(shy=shy, hem_y=shy + 0.398, hem_w=0.24, sleeve="short", kind="onesie"),
    )


def _dungarees():
    top = 0.235
    p = P((0.5 + 0.098, top))  # верх нагрудника
    p.ln((0.5 + 0.098, top + 0.075))
    p.q((0.5 + 0.168, top + 0.085), (0.5 + 0.172, top + 0.165))  # бок штанины
    p.c((0.5 + 0.176, top + 0.30), (0.5 + 0.170, top + 0.36), (0.5 + 0.166, top + 0.425))
    p.ln((0.5 + 0.040, top + 0.425))
    p.c((0.5 + 0.036, top + 0.36), (0.5 + 0.030, top + 0.32), (0.5 + 0.020, top + 0.295))
    right = p.done()
    outline = right + [(0.5 - 0.020, top + 0.295)] + mir(right)[1:]
    straps = [
        [
            (0.5 - 0.098, top),
            (0.5 - 0.062, top),
            (0.5 - 0.070, top - 0.115),
            (0.5 - 0.106, top - 0.115),
        ],
        [
            (0.5 + 0.098, top),
            (0.5 + 0.062, top),
            (0.5 + 0.070, top - 0.115),
            (0.5 + 0.106, top - 0.115),
        ],
    ]
    return (
        [outline] + straps,
        None,
        None,
        dict(top=top, hem_y=top + 0.425, cr_y=top + 0.295, waist=0.196, kind="dungarees"),
    )


def _leggings():
    return _pants(waist=0.235, hip=0.255, cuff=0.062, leg=0.615, crotch=0.285)


def _wallet():
    p = P((0.245, 0.352))
    p.q((0.235, 0.345), (0.235, 0.372))
    p.ln((0.235, 0.622))
    p.q((0.235, 0.652), (0.268, 0.652))
    p.ln((0.732, 0.652))
    p.q((0.765, 0.652), (0.765, 0.622))
    p.ln((0.765, 0.372))
    p.q((0.765, 0.345), (0.732, 0.352))
    return p.done(), None, None, dict(kind="wallet")


def _sunglasses():
    def lens(cx):
        p = P((cx - 0.098, 0.452))
        p.q((cx - 0.100, 0.560), (cx - 0.020, 0.572))
        p.q((cx + 0.086, 0.578), (cx + 0.094, 0.470))
        p.q((cx + 0.096, 0.446), (cx + 0.030, 0.442))
        p.q((cx - 0.060, 0.438), (cx - 0.098, 0.452))
        return p.done()

    bridge = [(0.386, 0.452), (0.614, 0.452), (0.614, 0.486), (0.386, 0.486)]
    arms = [
        [(0.196, 0.452), (0.150, 0.470), (0.146, 0.492), (0.196, 0.480)],
        [(0.804, 0.452), (0.850, 0.470), (0.854, 0.492), (0.804, 0.480)],
    ]
    return [lens(0.302), lens(0.698), bridge] + arms, None, None, dict(kind="sunglasses")


def _headband():
    outer = [
        (0.5 + 0.235 * math.cos(a), 0.52 - 0.205 * math.sin(a))
        for a in (math.pi * i / 48 for i in range(49))
    ]
    inner = [
        (0.5 + 0.175 * math.cos(a), 0.52 - 0.150 * math.sin(a))
        for a in (math.pi * (48 - i) / 48 for i in range(49))
    ]
    return outer + inner, None, None, dict(kind="headband")


SHAPES["onesie"] = _onesie
SHAPES["dungarees"] = _dungarees
SHAPES["leggings"] = _leggings
SHAPES["wallet"] = _wallet
SHAPES["sunglasses"] = _sunglasses
SHAPES["headband"] = _headband


def _crossbody():
    """Сумка через плечо: корпус с клапаном + длинный ремень (в отличие от тоута)."""
    body = P((0.305, 0.520))
    body.ln((0.695, 0.520))
    body.c((0.706, 0.640), (0.700, 0.720), (0.686, 0.780))
    body.q((0.500, 0.812), (0.314, 0.780))
    body.c((0.300, 0.720), (0.294, 0.640), (0.305, 0.520))
    flap = P((0.298, 0.520))
    flap.q((0.298, 0.432), (0.386, 0.428))
    flap.ln((0.614, 0.428))
    flap.q((0.702, 0.432), (0.702, 0.520))
    flap.q((0.500, 0.556), (0.298, 0.520))
    strap = [
        (0.318, 0.470),
        (0.352, 0.470),
        (0.352, 0.250),
        (0.648, 0.250),
        (0.648, 0.470),
        (0.682, 0.470),
        (0.682, 0.216),
        (0.318, 0.216),
    ]
    return [body.done(), flap.done(), strap], None, None, dict(kind="crossbody")


def _drawstring():
    """Мешок на шнурке (Turnbeutel): мягкий корпус + два шнура углами."""
    body = P((0.300, 0.392))
    body.c((0.276, 0.520), (0.276, 0.660), (0.312, 0.790))
    body.q((0.500, 0.836), (0.688, 0.790))
    body.c((0.724, 0.660), (0.724, 0.520), (0.700, 0.392))
    body.q((0.500, 0.356), (0.300, 0.392))
    cords = [
        [(0.312, 0.394), (0.336, 0.386), (0.470, 0.262), (0.452, 0.246)],
        [(0.688, 0.394), (0.664, 0.386), (0.530, 0.262), (0.548, 0.246)],
    ]
    return [body.done()] + cords, None, None, dict(kind="drawstring")


SHAPES["crossbody"] = _crossbody
SHAPES["drawstring"] = _drawstring


# ---------------- рендер ----------------
BG_TOP, BG_BOT = (247, 244, 240), (231, 225, 217)


def _studio_bg(w, h):
    """Мягкий студийный фон: вертикальный градиент + виньетка."""
    bg = Image.new("RGB", (w, h), BG_TOP)
    grad = Image.linear_gradient("L").resize((w, h))
    bg = Image.composite(Image.new("RGB", (w, h), BG_BOT), bg, grad)
    vign = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vign).ellipse([-0.18 * w, -0.18 * h, 1.18 * w, 1.18 * h], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(0.09 * w))
    dim = ImageChops.multiply(bg, Image.new("RGB", (w, h), (232, 228, 222)))
    return Image.composite(bg, dim, vign)


def _garment(key, color, texture, seed, w, h):
    """Слой вещи: (RGBA с альфой по силуэту, маска)."""
    rnd = random.Random(seed)
    base = hx(color)
    outline, neck, _front, m = SHAPES[key]()
    polys = outline if outline and isinstance(outline[0], list) else [outline]
    polys = [scale(pl, w, h) for pl in polys]

    mask = Image.new("L", (w, h), 0)
    for pl in polys:
        ImageDraw.Draw(mask).polygon(pl, fill=255)
    for cut in m.get("cutout", []):
        ImageDraw.Draw(mask).polygon(scale(cut, w, h), fill=0)

    lit = sh(base, 0.20 if luma(base) < 0.86 else 0.05)
    drk = sh(base, -0.26)
    lg = Image.linear_gradient("L").rotate(35, resample=Image.BICUBIC, expand=False)
    lg = lg.crop(
        (int(0.14 * lg.width), int(0.14 * lg.height), int(0.86 * lg.width), int(0.86 * lg.height))
    ).resize((w, h))
    body = Image.composite(Image.new("RGB", (w, h), drk), Image.new("RGB", (w, h), lit), lg)

    tex = _texture(texture, w, h, rnd)
    body = Image.blend(body, ImageChops.overlay(body, Image.merge("RGB", (tex, tex, tex))), 0.55)

    fl = Image.new("L", (w, h), 128)
    fd = ImageDraw.Draw(fl)
    for _ in range(rnd.randint(4, 6)):
        x0, y0 = rnd.uniform(0.30, 0.70), rnd.uniform(0.30, 0.62)
        pts = cub(
            (x0, y0),
            (x0 + rnd.uniform(-0.06, 0.06), y0 + 0.08),
            (x0 + rnd.uniform(-0.05, 0.05), y0 + 0.14),
            (x0 + rnd.uniform(-0.04, 0.06), y0 + 0.22),
            20,
        )
        fd.line(
            [(x * w, y * h) for x, y in pts],
            fill=rnd.choice([104, 150]),
            width=int(rnd.uniform(6, 11) * S),
            joint="curve",
        )
    fl = fl.filter(ImageFilter.GaussianBlur(0.012 * w))
    body = ImageChops.overlay(body, Image.merge("RGB", (fl, fl, fl)))

    edge = mask.filter(ImageFilter.MinFilter(3))
    for _ in range(3):
        edge = edge.filter(ImageFilter.MinFilter(9))
    inner = ImageChops.subtract(mask, edge).filter(ImageFilter.GaussianBlur(0.010 * w))
    body = Image.composite(
        ImageChops.multiply(body, Image.new("RGB", (w, h), (214, 208, 200))), body, inner
    )

    layer = body.convert("RGBA")
    layer.putalpha(mask)
    d = ImageDraw.Draw(layer, "RGBA")
    if neck:
        npx = scale(neck, w, h)
        band = npx + [(npx[-1][0], npx[-1][1] - 0.026 * h), (npx[0][0], npx[0][1] - 0.026 * h)]
        d.polygon(band, fill=sh(base, -0.26) + (255,))
        d.line(npx, fill=sh(base, -0.42) + (220,), width=int(2.4 * S), joint="curve")
    _details(d, key, m, w, h, base, rnd, None)
    for pl in polys:
        d.line(pl + [pl[0]], fill=sh(base, -0.40) + (200,), width=int(2.6 * S), joint="curve")
    layer.putalpha(ImageChops.lighter(layer.getchannel("A"), mask))
    return layer, mask


def _drop_shadow(bg, mask, dx, dy, blur):
    shd = mask.filter(ImageFilter.GaussianBlur(blur))
    shd = ImageChops.offset(shd, dx, dy).point(lambda v: int(v * 0.42))
    dark = ImageChops.multiply(bg, Image.new("RGB", bg.size, (176, 168, 158)))
    return Image.composite(dark, bg, shd)


def _grain(img):
    w, h = img.size
    noise = Image.effect_noise((w // 2, h // 2), 7).resize((w, h), Image.BILINEAR)
    grained = ImageChops.overlay(img, Image.merge("RGB", (noise, noise, noise)))
    return Image.blend(img, grained, 0.14)


def render(key, color="#2563eb", texture="", seed=1, size=800):
    """Один предмет на студийном фоне."""
    w = h = size * S
    bg = _studio_bg(w, h)
    layer, mask = _garment(key, color, texture, seed, w, h)
    bg = _drop_shadow(bg, mask, int(0.012 * w), int(0.020 * h), 0.028 * w)
    out = Image.alpha_composite(bg.convert("RGBA"), layer).convert("RGB")
    return _grain(out).resize((size, size), Image.LANCZOS)


def render_group(items, seed=1, size=800, ratio=(4, 3)):
    """Коллаж из 2-4 вещей — плитка направления / обложка подборки.

    Портретное соотношение (3:4 у плиток направлений) раскладывает вещи в
    ДВЕ строки со смещением: широкий ряд обрезался бы по краям и половина
    вещей уходила бы за кадр."""
    w = size * ratio[0] // max(ratio)
    h = size * ratio[1] // max(ratio)
    w, h = w * S, h * S
    bg = _studio_bg(w, h)
    n = len(items)
    portrait = ratio[1] > ratio[0]
    if portrait:
        rows = [items[: (n + 1) // 2], items[(n + 1) // 2 :]]
    else:
        rows = [items]
    tops, masks = [], []
    idx = 0
    for ri, row in enumerate(rows):
        if not row:
            continue
        cell_w = w / len(row)
        cell_h = h / len([r for r in rows if r])
        side = int(min(cell_w * 1.28, cell_h * 1.18))
        for i, (key, color, texture) in enumerate(row):
            layer, mask = _garment(key, color, texture, seed + idx * 13, side, side)
            idx += 1
            x = int(i * cell_w + (cell_w - side) / 2)
            y = int(ri * cell_h + (cell_h - side) / 2 + (0.012 * h if i % 2 else -0.012 * h))
            full = Image.new("L", (w, h), 0)
            full.paste(mask, (x, y))
            big = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            big.paste(layer, (x, y), layer)
            masks.append(full)
            tops.append(big)
    for m in masks:
        bg = _drop_shadow(bg, m, int(0.010 * w), int(0.018 * h), 0.020 * w)
    out = bg.convert("RGBA")
    for t in tops:
        out = Image.alpha_composite(out, t)
    return _grain(out.convert("RGB")).resize(
        (size * ratio[0] // max(ratio), size * ratio[1] // max(ratio)), Image.LANCZOS
    )


# ---------------- палитра ----------------
# Зеркало `apps.catalog.option_styles.COLOR_HEX` (замок сверяет — свотч варианта
# и цвет картинки обязаны совпадать). Скрипт намеренно не поднимает Django.
COLORS = {
    "schwarz": "#111827",
    "weiss": "#ffffff",
    "grau": "#9ca3af",
    "anthrazit": "#374151",
    "blau": "#2563eb",
    "hellblau": "#7dd3fc",
    "navy": "#1e3a8a",
    "tuerkis": "#14b8a6",
    "gruen": "#16a34a",
    "oliv": "#4d7c0f",
    "rot": "#dc2626",
    "bordeaux": "#7f1d1d",
    "rosa": "#f9a8d4",
    "lila": "#8b5cf6",
    "gelb": "#facc15",
    "braun": "#78350f",
    "beige": "#e7dcc7",
    "creme": "#f5f0e1",
    "sand": "#e0cfa9",
}

# ---------------- каталог «Studio Nordwind» ----------------
# (ключ фото, силуэт, фактура, [цвета]) — первый цвет даёт базовый файл
# `<ключ>.webp`, остальные `<ключ>-<цвет>.webp` (фото варианта).
GARMENTS = [
    # --- Damen -------------------------------------------------------------
    ("mode-sommerkleid-nordlicht", "dress", "cotton", ["blau", "sand"]),
    ("mode-wickelkleid-deichgold", "dress", "cotton", ["oliv", "bordeaux"]),
    ("mode-strickkleid-winterlicht", "dress_sl", "strick", ["anthrazit", "creme"]),
    ("mode-midirock-elbwelle", "skirt", "leinen", ["sand", "navy"]),
    ("mode-plisseerock-alster", "skirt", "cotton", ["schwarz", "rosa"]),
    ("mode-leinenbluse-kueste", "blouse", "leinen", ["weiss", "hellblau"]),
    ("mode-seidenbluse-aurora", "blouse", "cotton", ["creme", "bordeaux"]),
    ("mode-shirt-moewe", "tshirt", "cotton", ["weiss", "schwarz", "navy"]),
    ("mode-ringelshirt-hafenkante", "longsleeve", "cotton", ["navy", "rot"]),
    ("mode-traegertop-sommerbrise", "top", "cotton", ["creme", "rosa"]),
    ("mode-cardigan-wolke", "cardigan", "strick", ["beige", "braun"]),
    ("mode-merinopullover-nordwind", "sweater", "strick", ["grau", "gruen"]),
    ("mode-grobstrick-fischer", "sweater", "strick", ["creme", "navy"]),
    ("mode-strickweste-moewenflug", "vest", "strick", ["schwarz", "sand"]),
    ("mode-jeans-deich", "jeans", "denim", ["blau", "schwarz"]),
    ("mode-marlenehose-kontor", "trousers", "cotton", ["oliv", "anthrazit"]),
    ("mode-leinenhose-sommerdeich", "trousers", "leinen", ["creme", "sand"]),
    ("mode-steppjacke-elbnebel", "jacket", "cotton", ["anthrazit", "oliv"]),
    ("mode-wollmantel-winterhafen", "coat", "cord", ["bordeaux", "anthrazit"]),
    ("mode-regenjacke-nordsee", "jacket", "cotton", ["gelb", "navy"]),
    # --- Herren ------------------------------------------------------------
    ("mode-leinenhemd-hafen", "shirt", "leinen", ["weiss", "hellblau"]),
    ("mode-oxfordhemd-kontor", "shirt", "cotton", ["weiss", "blau"]),
    ("mode-flanellhemd-werft", "shirt", "cord", ["rot", "oliv"]),
    ("mode-kurzarmhemd-sommerdock", "shirt", "leinen", ["sand"]),
    ("mode-basic-tshirt", "tshirt", "cotton", ["weiss", "schwarz", "navy", "oliv"]),
    ("mode-jerseyshirt-docker", "tshirt", "cotton", ["anthrazit"]),
    ("mode-longsleeve-nordkap", "longsleeve", "cotton", ["navy", "grau"]),
    ("mode-poloshirt-reederei", "polo", "cotton", ["navy", "weiss"]),
    ("mode-ringelshirt-seemann", "longsleeve", "cotton", ["weiss", "navy"]),
    ("mode-merinopullover-herren", "sweater", "strick", ["anthrazit", "braun"]),
    ("mode-strickjacke-kapitaen", "cardigan", "strick", ["navy", "grau"]),
    ("mode-rollkragen-fischer", "sweater", "strick", ["creme", "schwarz"]),
    ("mode-sweatshirt-werfthalle", "hoodie", "cotton", ["grau", "oliv"]),
    ("mode-chino-deich", "chinos", "cotton", ["beige", "oliv"]),
    ("mode-jeans-elbe", "jeans", "denim", ["blau", "anthrazit"]),
    ("mode-cordhose-kontor", "chinos", "cord", ["braun", "oliv"]),
    ("mode-leinenhose-hafenbrise", "trousers", "leinen", ["creme", "sand"]),
    ("mode-steppjacke-nordwind", "jacket", "cotton", ["schwarz", "oliv"]),
    ("mode-wollmantel-reeder", "coat", "cord", ["anthrazit", "braun"]),
    ("mode-regenjacke-sturmflut", "jacket", "cotton", ["gelb", "navy"]),
    # --- Kinder ------------------------------------------------------------
    ("mode-strampler-seestern", "onesie", "cotton", ["hellblau", "rosa"]),
    ("mode-babybody-muschel", "onesie", "cotton", ["creme", "weiss"]),
    ("mode-babystrickjacke-wolke", "cardigan", "strick", ["creme", "rosa"]),
    ("mode-babymuetze-sturmhaube", "beanie", "strick", ["hellblau", "rosa"]),
    ("mode-latzhose-krabbe", "dungarees", "denim", ["blau", "oliv"]),
    ("mode-musselintuch-nordlicht", "scarf", "leinen", ["creme", "hellblau"]),
    ("mode-kindershirt-leuchtturm", "tshirt", "cotton", ["weiss", "gelb"]),
    ("mode-kinderlongsleeve-anker", "longsleeve", "cotton", ["navy", "rot"]),
    ("mode-maedchenkleid-sommerwiese", "dress", "cotton", ["rosa", "gelb"]),
    ("mode-jerseykleid-regenbogen", "dress", "cotton", ["tuerkis", "lila"]),
    ("mode-kinderleggings-seehund", "leggings", "cotton", ["schwarz", "grau"]),
    ("mode-kinderjeans-werft", "jeans", "denim", ["blau"]),
    ("mode-kindersweat-moewe", "hoodie", "cotton", ["grau", "gruen"]),
    ("mode-kinderpullover-nordstern", "sweater", "strick", ["creme", "blau"]),
    ("mode-kinderregenjacke-pfuetze", "jacket", "cotton", ["gelb", "tuerkis"]),
    ("mode-kindershorts-sandkiste", "shorts", "cotton", ["sand", "navy"]),
    ("mode-kinderrock-loewenzahn", "skirt", "cotton", ["gelb", "rosa"]),
    ("mode-kindersocken-krabbe", "socks", "strick", ["grau", "rosa"]),
    ("mode-kindermuetze-sternchen", "beanie", "strick", ["rot", "tuerkis"]),
    ("mode-turnbeutel-seepferd", "drawstring", "leinen", ["tuerkis", "gelb"]),
    # --- Accessoires -------------------------------------------------------
    ("mode-canvastasche-hafen", "bag", "leinen", ["beige", "navy"]),
    ("mode-ledershopper-kontor", "bag", "leder", ["braun", "schwarz"]),
    ("mode-rucksack-wattenmeer", "backpack", "leder", ["anthrazit", "oliv"]),
    ("mode-umhaengetasche-elbe", "crossbody", "leder", ["schwarz", "braun"]),
    ("mode-turnbeutel-deich", "drawstring", "leinen", ["creme"]),
    ("mode-wollschal-nordwind", "scarf", "strick", ["grau", "bordeaux"]),
    ("mode-seidentuch-aurora", "scarf", "cotton", ["rosa", "creme"]),
    ("mode-kaschmirschal-winterlicht", "scarf", "strick", ["creme", "anthrazit"]),
    ("mode-strickmuetze-leuchtturm", "beanie", "strick", ["rot", "navy"]),
    ("mode-cap-segeltuch", "cap", "cotton", ["navy", "beige"]),
    ("mode-stirnband-deichwind", "headband", "strick", ["anthrazit", "rosa"]),
    ("mode-handschuhe-winterhafen", "glove", "leder", ["schwarz", "braun"]),
    ("mode-faeustlinge-nordlicht", "glove", "strick", ["bordeaux", "grau"]),
    ("mode-lederguertel-werft", "belt", "leder", ["braun", "schwarz"]),
    ("mode-stoffguertel-sommerdeich", "belt", "leinen", ["sand", "navy"]),
    ("mode-portemonnaie-kontor", "wallet", "leder", ["braun", "schwarz"]),
    ("mode-kartenetui-anker", "wallet", "leder", ["schwarz", "bordeaux"]),
    ("mode-socken-moewe", "socks", "strick", ["grau", "navy"]),
    ("mode-kniestruempfe-winterhafen", "socks", "strick", ["anthrazit", "creme"]),
    ("mode-sonnenbrille-kueste", "sunglasses", "cotton", ["schwarz", "braun"]),
]

# Коллажи: плитки направлений, обложки подборок и комплектов.
GROUPS = [
    (
        "mode-kat-damen",
        [("dress", "blau", "cotton"), ("blouse", "creme", "leinen"), ("skirt", "sand", "leinen")],
    ),
    (
        "mode-kat-herren",
        [
            ("shirt", "hellblau", "leinen"),
            ("chinos", "beige", "cotton"),
            ("sweater", "anthrazit", "strick"),
        ],
    ),
    (
        "mode-kat-kinder",
        [
            ("onesie", "hellblau", "cotton"),
            ("dungarees", "blau", "denim"),
            ("beanie", "rot", "strick"),
        ],
    ),
    (
        "mode-kat-accessoires",
        [
            ("bag", "braun", "leder"),
            ("scarf", "grau", "strick"),
            ("sunglasses", "schwarz", "cotton"),
        ],
    ),
    ("mode-kat-kleider", [("dress", "bordeaux", "cotton"), ("skirt", "navy", "leinen")]),
    ("mode-kat-oberteile", [("blouse", "weiss", "leinen"), ("tshirt", "navy", "cotton")]),
    ("mode-kat-strick", [("sweater", "creme", "strick"), ("cardigan", "braun", "strick")]),
    ("mode-kat-hosen", [("jeans", "blau", "denim"), ("trousers", "oliv", "cotton")]),
    ("mode-kat-jacken", [("jacket", "anthrazit", "cotton"), ("coat", "bordeaux", "cord")]),
    ("mode-kat-hemden", [("shirt", "weiss", "cotton"), ("shirt", "rot", "cord")]),
    ("mode-kat-shirts", [("tshirt", "weiss", "cotton"), ("polo", "navy", "cotton")]),
    ("mode-kat-baby", [("onesie", "creme", "cotton"), ("beanie", "hellblau", "strick")]),
    ("mode-kat-maedchen", [("dress", "rosa", "cotton"), ("skirt", "gelb", "cotton")]),
    ("mode-kat-jungen", [("hoodie", "gruen", "cotton"), ("jeans", "blau", "denim")]),
    ("mode-kat-taschen", [("bag", "beige", "leinen"), ("crossbody", "anthrazit", "leder")]),
    ("mode-kat-schals", [("scarf", "bordeaux", "strick"), ("beanie", "navy", "strick")]),
    ("mode-kat-kleinleder", [("belt", "braun", "leder"), ("wallet", "schwarz", "leder")]),
    ("mode-kat-kindermuetzen", [("beanie", "rot", "strick"), ("socks", "rosa", "strick")]),
    ("mode-kat-kleines", [("socks", "navy", "strick"), ("sunglasses", "schwarz", "cotton")]),
    # подборки / лукбук
    (
        "mode-look-herbst",
        [
            ("cardigan", "braun", "strick"),
            ("jeans", "blau", "denim"),
            ("scarf", "bordeaux", "strick"),
        ],
    ),
    (
        "mode-look-business",
        [
            ("blouse", "weiss", "leinen"),
            ("trousers", "anthrazit", "cotton"),
            ("bag", "schwarz", "leder"),
        ],
    ),
    (
        "mode-look-strand",
        [
            ("dress", "sand", "cotton"),
            ("bag", "beige", "leinen"),
            ("sunglasses", "braun", "cotton"),
        ],
    ),
    (
        "mode-look-kids",
        [("tshirt", "gelb", "cotton"), ("dungarees", "blau", "denim"), ("socks", "rosa", "strick")],
    ),
    (
        "mode-look-basics",
        [("tshirt", "weiss", "cotton"), ("jeans", "blau", "denim"), ("sweater", "grau", "strick")],
    ),
    # комплекты (Kombi)
    ("mode-set-sonntag", [("blouse", "creme", "leinen"), ("skirt", "navy", "leinen")]),
    (
        "mode-set-buero",
        [("shirt", "weiss", "cotton"), ("chinos", "beige", "cotton"), ("belt", "braun", "leder")],
    ),
    (
        "mode-set-winter",
        [("coat", "anthrazit", "cord"), ("scarf", "grau", "strick"), ("glove", "schwarz", "leder")],
    ),
    (
        "mode-set-erstausstattung",
        [
            ("onesie", "creme", "cotton"),
            ("beanie", "hellblau", "strick"),
            ("socks", "grau", "strick"),
        ],
    ),
    (
        "mode-set-wochenende",
        [
            ("hoodie", "oliv", "cotton"),
            ("jeans", "blau", "denim"),
            ("backpack", "anthrazit", "leder"),
        ],
    ),
]

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "demo", "photos"
)


def main():
    """Аргументы: [каталог] [--only <префикс>] — префикс перерисовывает часть набора."""
    argv = list(sys.argv[1:])
    only = ""
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1] if len(argv) > i + 1 else ""
        del argv[i : i + 2]
    out = argv[0] if argv else OUT_DIR
    os.makedirs(out, exist_ok=True)
    n = 0
    for seed, (key, shape, texture, colors) in enumerate(GARMENTS):
        if only and not key.startswith(only):
            continue
        for ci, color in enumerate(colors):
            name = key if ci == 0 else f"{key}-{color}"
            img = render(shape, COLORS[color], texture, seed=seed * 7 + ci, size=800)
            img.save(os.path.join(out, f"{name}.webp"), "WEBP", quality=80, method=6)
            n += 1
    for seed, (key, items) in enumerate(GROUPS):
        if only and not key.startswith(only):
            continue
        parts = [(sh_key, COLORS[c], tex) for sh_key, c, tex in items]
        # Плитки направлений стоят в высоких карточках (3:4) — широкий коллаж
        # там обрезался бы по краям; обложки лукбука и комплектов — 4:3.
        ratio = (3, 4) if key.startswith("mode-kat-") else (4, 3)
        img = render_group(parts, seed=900 + seed * 5, size=1000, ratio=ratio)
        img.save(os.path.join(out, f"{key}.webp"), "WEBP", quality=80, method=6)
        n += 1
    print(f"{n} Bilder → {out}")


if __name__ == "__main__":
    main()
