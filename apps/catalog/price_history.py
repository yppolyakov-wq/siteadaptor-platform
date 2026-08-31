"""§11 PAngV (M1 Boutique): история цен — запись при изменении + 30-дневный минимум.

Зачёркнутая Sale-цена по §11 PAngV обязана сопровождаться низшей ценой последних
30 дней. Сигналы post_save Product/ProductVariant (apps.py) пишут `PriceLog`
только при изменении цены (сравнение с последней записью — без старых снапшотов);
`lowest_price_30d` отдаёт минимум за окно или None (нет данных — строка не
показывается, честнее промолчать, чем угадать).
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone


def log_price_if_changed(product, price, variant=None) -> None:
    """Дописать PriceLog, если цена отличается от последней записи (append-only)."""
    from apps.catalog.models import PriceLog

    if price is None:
        return
    last = (
        PriceLog.objects.filter(product=product, variant=variant)
        .order_by("-created_at")
        .values_list("price", flat=True)
        .first()
    )
    if last is not None and last == price:
        return
    PriceLog.objects.create(product=product, variant=variant, price=price)


def lowest_price_30d(product, days: int = 30) -> Decimal | None:
    """Минимальная зафиксированная цена товара за окно (по базовой цене, без
    вариантов) или None, если записей нет. Учитывает и цену, действовавшую НА
    НАЧАЛО окна (последняя запись до его старта) — иначе стабильная старая цена
    «выпадала» бы из минимума."""
    from django.db.models import Min

    from apps.catalog.models import PriceLog

    since = timezone.now() - timedelta(days=days)
    qs = PriceLog.objects.filter(product=product, variant__isnull=True)
    in_window = qs.filter(created_at__gte=since).aggregate(m=Min("price"))["m"]
    before = (
        qs.filter(created_at__lt=since)
        .order_by("-created_at")
        .values_list("price", flat=True)
        .first()
    )
    candidates = [p for p in (in_window, before) if p is not None]
    return min(candidates) if candidates else None


def _on_product_save(sender, instance, **kwargs):
    """post_save Product → лог базовой цены (receiver модульного уровня — weak-
    ссылка сигнала не должна собираться GC, урок M1)."""
    log_price_if_changed(instance, instance.base_price)


def _on_variant_save(sender, instance, **kwargs):
    if instance.price is not None:
        log_price_if_changed(instance.product, instance.price, variant=instance)


def lowest_price_30d_bulk(product_ids, days: int = 30) -> dict:
    """SF-3: §11 PAngV для КАРТОЧЕК — минимум за окно батчем (без N+1).

    Семантика 1:1 с lowest_price_30d: Min по окну + цена, действовавшая на
    начало окна (последняя запись до старта). Возврат {product_id: Decimal};
    товары без записей в словарь не попадают (строка честно молчит)."""
    from django.db.models import Min

    from apps.catalog.models import PriceLog

    ids = [pk for pk in set(product_ids) if pk]
    if not ids:
        return {}
    since = timezone.now() - timedelta(days=days)
    base = PriceLog.objects.filter(product_id__in=ids, variant__isnull=True)
    out: dict = {}
    for row in base.filter(created_at__gte=since).values("product_id").annotate(m=Min("price")):
        out[row["product_id"]] = row["m"]
    before = (
        base.filter(created_at__lt=since)
        .order_by("product_id", "-created_at")
        .distinct("product_id")
        .values_list("product_id", "price")
    )
    for pid, price in before:
        cur = out.get(pid)
        out[pid] = price if cur is None else min(cur, price)
    return out
