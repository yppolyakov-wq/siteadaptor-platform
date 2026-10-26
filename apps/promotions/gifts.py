"""KA-12 PR-4: «Gratis-Artikel ab Bestellwert» — подарок в заказ от суммы товаров.

Акция-подарок: цель — товар-подарок, порог — `metadata["gift_min_order"]` (строка «30.00»),
без миграции. Цену товара она НЕ меняет (в `price_layer` исключена): подарок появляется
отдельной строкой 0 € в корзине и в `create_order` одной функцией (`pick`) — «показано =
списано». Лимит кампании — штука подарка; кончился (или нет на складе) — заказ без подарка,
а не отказ: подарок — бонус, а не предмет покупки."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import Promotion

KEY = "gift_min_order"


def threshold(promo) -> Decimal | None:
    meta = promo.metadata if isinstance(getattr(promo, "metadata", None), dict) else {}
    raw = meta.get(KEY)
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value > 0 else None


def is_gift(promo) -> bool:
    return threshold(promo) is not None


def _candidates():
    from .price_layer import rules_match

    now = timezone.now()
    out = []
    for promo in (
        Promotion.objects.filter(
            Promotion.on_sale_q(), product__isnull=False, metadata__has_key=KEY
        )
        .select_related("product")
        .order_by("created_at", "pk")
    ):
        limit = threshold(promo)
        product = promo.product
        if limit is None or product is None or not product.is_active:
            continue
        if product.stock_quantity is not None and product.stock_quantity < 1:
            continue
        # Ревью PR-4: «Heute ausverkauft» и товар с вариантами (какой вариант дарить?)
        # подарком не бывают — корзина не обещает того, чего заказ не добавит.
        if product.is_sold_out_today or product.has_variants:
            continue
        if not rules_match(promo.target_rules, now):
            continue
        out.append((limit, promo))
    out.sort(key=lambda pair: (pair[0], str(pair[1].pk)))
    return out


def pick(subtotal) -> tuple:
    """→ (подарок | None, ближайший следующий подарок | None, сколько не хватает | None).
    При нескольких достигнутых — с самым высоким порогом (самый «дорогой» бонус)."""
    subtotal = Decimal(str(subtotal or 0))
    reached, upcoming = None, None
    for limit, promo in _candidates():
        if limit <= subtotal:
            reached = promo
        elif upcoming is None:
            upcoming = (promo, limit - subtotal)
    if upcoming is None:
        return reached, None, None
    return reached, upcoming[0], upcoming[1]
