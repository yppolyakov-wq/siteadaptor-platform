"""KA-12 PR-3: количественные акции («2. Stück −50 %», «3 für 2», «ab 3 Stück −20 %»)
реально считаются в корзине и заказе — одной функцией (`split_units`) для обоих.

План `docs/ka-12-pr3-quantity-deals-plan-2026-10-26.md`. Условие хранится в
`Promotion.metadata["price_condition"]` (В2, `apps/core/price_conditions.py`); цена штуки
на витрине остаётся обычной, выгода появляется на строке корзины и в заказе.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.core import price_conditions

_CENT = Decimal("0.01")


def _reduced(base: Decimal, percent) -> Decimal | None:
    try:
        pct = int(percent or 0)
    except (TypeError, ValueError):
        return None
    if not 0 < pct < 100:
        return None
    return (base * (Decimal(100) - pct) / Decimal(100)).quantize(_CENT, rounding=ROUND_HALF_UP)


def split_units(cond, percent, base, qty, cap=None) -> list[tuple[int, Decimal, bool]]:
    """Разбивка строки: [(штук, цена базы за штуку, скидочная?)] — сумма штук = qty.
    Без применимого условия — одна строка по base (выгоды нет). `cap` — остаток лимита
    кампании (None = без лимита): скидочных штук не больше него (иначе чекаут падал бы
    на `claim_units` вместо того, чтобы дать скидку на оставшиеся штуки)."""
    parts = _split(cond, percent, base, qty)
    if cap is None:
        return parts
    cap = max(int(cap), 0)
    out, left = [], cap
    for units, price, disc in parts:
        if not disc:
            out.append((units, price, False))
            continue
        take = min(units, left)
        left -= take
        if take:
            out.append((take, price, True))
        if units - take:
            out.append((units - take, Decimal(str(base)), False))
    return _collapse(out)


def _collapse(parts):
    """Слить одинаковые недисконтные куски (после обрезки лимитом)."""
    plain = sum(u for u, _p, d in parts if not d)
    disc = [p for p in parts if p[2]]
    base = next((p for _u, p, d in parts if not d), None)
    return ([(plain, base, False)] if plain else []) + disc


def _split(cond, percent, base, qty) -> list[tuple[int, Decimal, bool]]:
    base = Decimal(str(base))
    qty = int(qty)
    plain = [(qty, base, False)]
    cond = price_conditions.normalize(cond) if isinstance(cond, dict) else None
    if not cond or qty < 1:
        return plain
    kind, n = cond["kind"], cond["n"]
    if kind == price_conditions.NTH:
        reduced = _reduced(base, percent)
        k = qty // n
        if reduced is None or k == 0:
            return plain
        return _merge([(qty - k, base, False), (k, reduced, True)])
    if kind == price_conditions.X_FOR_Y:
        free = (qty // n) * (n - cond["pay"])
        if free == 0:
            return plain
        return _merge([(qty - free, base, False), (free, Decimal("0.00"), True)])
    if kind == price_conditions.MIN_QTY:
        reduced = _reduced(base, percent)
        if reduced is None or qty < n:
            return plain
        return [(qty, reduced, True)]
    return plain


def _merge(parts):
    return [p for p in parts if p[0] > 0]


def savings(parts, base) -> Decimal:
    """Выгода разбивки относительно base × qty (для подписи корзины)."""
    base = Decimal(str(base))
    return sum(((base - price) * units for units, price, disc in parts if disc), Decimal("0"))


def deal_map(product_ids, *, now=None) -> dict:
    """{product_id: [Promotion]} — активные условные акции на товары (не mystery,
    в окне `target_rules`). Один запрос."""
    from .models import Promotion
    from .price_layer import rules_match

    ids = list(product_ids)
    if not ids:
        return {}
    now = now or timezone.now()
    out: dict = {}
    for promo in (
        Promotion.objects.filter(Promotion.on_sale_q(), product_id__in=ids)
        .exclude(discount_style="mystery")
        .order_by("created_at", "pk")
    ):
        if not promo.price_condition or not rules_match(promo.target_rules, now):
            continue
        out.setdefault(promo.product_id, []).append(promo)
    return out


def best_split(promos, product, variant, qty):
    """(promo, parts) с наибольшей выгодой для строки или None. Вариант со своей ценой
    акцию не получает (как `promo_line_price`)."""
    if not promos or product is None:
        return None
    if variant is not None and getattr(variant, "price", None) is not None:
        return None
    base = Decimal(str(product.base_price))
    best = None
    for promo in promos:
        parts = split_units(
            promo.price_condition, promo.discount_percent, base, qty, promo.available_quantity
        )
        gain = savings(parts, base)
        if gain > 0 and (best is None or gain > best[2]):
            best = (promo, parts, gain)
    return (best[0], best[1]) if best else None
