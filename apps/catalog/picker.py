"""Пикер позиций каталога для строк сметы/заказа (извлечено из jobs.views, SH-B).

QF-1 сделал пикер для сметы Handwerker; SH-2 (фидбэк владельца 2026-08-20)
попросил ту же кнопку «добавить позицию» в ЗАКАЗЕ. Реализация одна — иначе два
списка «что можно добавить» разъедутся (у заявки услуги есть, у заказа нет).
"""

from decimal import Decimal


def _catalog_parts(tenant=None):
    """G11: активные позиции для пикера строки сметы (value/label + остаток).

    value кодирует вид: ``p:<pk>`` товар без вариантов, ``v:<pk>`` вариант,
    ``s:<pk>`` услуга (QF-1: владелец добавляет в смету «товар/услугу»; у услуги
    нет склада и FK — в строку едет снимок названия и цены, как у свободной).
    Остаток в подписи — int (локаль-стабильно), только при учёте склада."""
    from apps.catalog.models import Product

    parts = []
    for p in Product.objects.filter(is_active=True).prefetch_related("variants"):
        variants = [v for v in p.variants.all() if v.is_active]
        if variants:
            for v in variants:
                label = f"{p.name_text} · {v.label}"
                if v.stock_quantity is not None:
                    label += f" (Lager: {v.stock_quantity})"
                parts.append(
                    {"value": f"v:{v.pk}", "label": label, "price": v.price_value, "title": label}
                )
        else:
            label = p.name_text
            if p.stock_quantity is not None:
                label += f" (Lager: {p.stock_quantity})"
            parts.append(
                {
                    "value": f"p:{p.pk}",
                    "label": label,
                    "price": p.base_price,
                    "title": p.name_text,
                }
            )
    # Услуги — только если модуль записи активен (у кейтеринга/Handwerker их нет).
    if tenant is not None and tenant.is_module_active("booking"):
        from apps.booking.models import Service

        for svc in Service.objects.filter(is_active=True):
            parts.append(
                {
                    "value": f"s:{svc.pk}",
                    "label": str(svc),
                    "price": Decimal(svc.price_cents) / 100,
                    "title": str(svc),
                }
            )
    return parts


def _resolve_part(raw, products, variants):
    """value пикера → (product, variant) инстансы или (None, None).

    pk — UUID-строка (каталог на UUID-PK), словари ключим по str(pk).
    Услуга (``s:``) FK не имеет — её снимок берёт `_service_snapshot`."""
    kind, _, pk = (raw or "").partition(":")
    if not pk:
        return None, None
    if kind == "v":
        v = variants.get(pk)
        return (v.product if v else None), v
    if kind == "p":
        return products.get(pk), None
    return None, None


def _service_snapshot(raw):
    """QF-1: (название, цена) выбранной услуги или (None, None).

    У строки сметы нет FK на услугу (склад/леджер её не касаются) — в смету едет
    СНИМОК: правка каталога услуг не переписывает отправленную смету."""
    kind, _, pk = (raw or "").partition(":")
    if kind != "s" or not pk:
        return None, None
    from apps.booking.models import Service

    svc = Service.objects.filter(pk=pk, is_active=True).first()
    if svc is None:
        return None, None
    return str(svc), Decimal(svc.price_cents) / 100
