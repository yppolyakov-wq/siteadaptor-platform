"""PAngV: расчёт Grundpreis — цена за базовую единицу (€/kg или €/l), R2.

Несчётные товары (вес/объём) обязаны показывать Grundpreis рядом с ценой
(Preisangabenverordnung). g→/kg, ml→/l; Stück/пусто/нулевой контент → None.
"""

from decimal import Decimal, InvalidOperation


def grundpreis(price, unit, content_amount):
    """(value: Decimal, ref: 'kg'|'l') или None.

    value = price / (content в базовой единице). None, если unit пустой
    (Stück/несчётное), цена/контент отсутствуют или контент ≤ 0.
    """
    if not unit or price is None or content_amount in (None, ""):
        return None
    try:
        content = Decimal(str(content_amount))
        price = Decimal(str(price))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if content <= 0:
        return None
    if unit == "g":
        base, ref = content / 1000, "kg"
    elif unit == "kg":
        base, ref = content, "kg"
    elif unit == "ml":
        base, ref = content / 1000, "l"
    elif unit == "l":
        base, ref = content, "l"
    else:
        return None
    return (price / base).quantize(Decimal("0.01")), ref


def margin_pct(sale_price, cost_price):
    """Marge в процентах = (VK − EK)/VK × 100 (T5).

    int (усечение к нулю). None, если EK или VK отсутствуют или VK ≤ 0.
    Отрицательный результат (продажа ниже закупки) допускается и возвращается.
    """
    if cost_price is None or sale_price is None:
        return None
    try:
        vk = Decimal(str(sale_price))
        ek = Decimal(str(cost_price))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if vk <= 0:
        return None
    return int((vk - ek) / vk * 100)
