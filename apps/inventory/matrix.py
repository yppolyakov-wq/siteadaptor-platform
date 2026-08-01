"""Разрез остатка по осям варианта — «размер × цвет» (2026-08-01).

Вопрос владельца: «есть ли в настройках склада учёт количества определённого
цвета и размера отдельно». Учёт — есть: единица склада = вариант, а вариант с
M4-A несёт обе оси, поэтому «S · Blau» и «M · Blau» — независимые позиции со
своим остатком, леджером, Meldebestand и Warenwert. Чего не было — ЭКРАНА в
разрезе осей: склад показывал плоский список склеенных `label`, поэтому «сколько
всего синего» или «сколько всего размера M» посмотреть было негде.

Здесь только представление: ни модели, ни движения остатка не трогаются.
"""

from apps.catalog.models import Product

# Осей может не быть вовсе (легаси-варианты «100 g» одним label) — тогда матрица
# бессмысленна и товар остаётся в плоском списке.
_MIN_AXES = 2


def _axis(variant) -> tuple[str, str]:
    """Оси варианта. Размер с фолбэком на label — тот же резолвер, что у фасета
    каталога (`size_axis`): смешанный каталог не должен терять позиции."""
    return (variant.size or variant.label or "").strip(), (variant.color or "").strip()


def product_matrix(product) -> dict | None:
    """Сетка остатков товара: строки — размеры, столбцы — цвета.

    ``None``, если у товара нет обеих осей (матрица выродилась бы в один
    столбец). Ячейка без варианта — пустая (такой комбинации просто нет, это не
    «ноль на складе»: их важно различать при инвентаризации).
    """
    variants = [v for v in product.variants.all() if v.is_active]
    sizes, colors, cells = [], [], {}
    for v in variants:
        size, color = _axis(v)
        if not size or not color:
            continue
        if size not in sizes:
            sizes.append(size)
        if color not in colors:
            colors.append(color)
        cells[(size, color)] = v
    if len(sizes) < 1 or len(colors) < _MIN_AXES - 1 or not cells:
        return None
    if len(sizes) < 2 and len(colors) < 2:
        return None  # одна-единственная комбинация — таблица ничего не добавит

    rows, col_totals, total, tracked_any = [], {c: None for c in colors}, 0, False
    for size in sizes:
        line, row_total = [], None
        for color in colors:
            v = cells.get((size, color))
            qty = None if v is None else v.stock_quantity
            if qty is not None:
                tracked_any = True
                row_total = (row_total or 0) + qty
                col_totals[color] = (col_totals[color] or 0) + qty
                total += qty
            line.append({"variant": v, "qty": qty, "value": f"v{v.pk}" if v else ""})
        rows.append({"size": size, "cells": line, "total": row_total})
    return {
        "product": product,
        "sizes": sizes,
        "colors": colors,
        "rows": rows,
        # Итоги по колонкам — «сколько всего этого цвета»; по строкам — «сколько
        # всего этого размера». Не считаем неучитываемые позиции (stock=None):
        # они означают «без лимита», а не ноль.
        "col_totals": [col_totals[c] for c in colors],
        "total": total if tracked_any else None,
    }


def matrices(products=None) -> list[dict]:
    """Матрицы всех товаров, у которых заполнены обе оси (прочие — не наше дело)."""
    qs = products if products is not None else Product.objects.prefetch_related("variants")
    out = []
    for product in qs:
        m = product_matrix(product)
        if m:
            out.append(m)
    return out


def axis_values(rows) -> tuple[list[str], list[str]]:
    """Уникальные размеры и цвета по строкам сверки — для фильтров плоской
    таблицы. Строка товара без вариантов осей не имеет и в фильтры не попадает."""
    sizes, colors = [], []
    for r in rows:
        v = r.get("variant")
        if v is None:
            continue
        size, color = _axis(v)
        if size and size not in sizes:
            sizes.append(size)
        if color and color not in colors:
            colors.append(color)
    return sizes, colors


def filter_rows(rows, size: str = "", color: str = "") -> list:
    """Фильтр плоской таблицы по осям. Пустой фильтр — список без изменений;
    товары без вариантов при активном фильтре уходят (у них нет ни размера, ни
    цвета — показывать их в выдаче «размер M» было бы враньём)."""
    if not size and not color:
        return list(rows)
    out = []
    for r in rows:
        v = r.get("variant")
        if v is None:
            continue
        vsize, vcolor = _axis(v)
        if size and vsize != size:
            continue
        if color and vcolor != color:
            continue
        out.append(r)
    return out
