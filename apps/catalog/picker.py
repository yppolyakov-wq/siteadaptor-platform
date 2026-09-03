"""Пикер позиций каталога для строк сметы/заказа (извлечено из jobs.views, SH-B).

QF-1 сделал пикер для сметы Handwerker; SH-2 (фидбэк владельца 2026-08-20)
попросил ту же кнопку «добавить позицию» в ЗАКАЗЕ. Реализация одна — иначе два
списка «что можно добавить» разъедутся (у заявки услуги есть, у заказа нет).
"""

from decimal import Decimal

from django.utils.translation import gettext as _


def _primary_url(product) -> str:
    """SH-21: URL главного фото товара ('' без фото) — у Product нет image_url."""
    img = product.primary_image
    return (img.get("url", "") or "") if isinstance(img, dict) else ""


def _catalog_parts(tenant=None, include_combos=False):
    """G11: активные позиции для пикера строки сметы (value/label + остаток).

    value кодирует вид: ``p:<pk>`` товар без вариантов, ``v:<pk>`` вариант,
    ``s:<pk>`` услуга (QF-1: владелец добавляет в смету «товар/услугу»; у услуги
    нет склада и FK — в строку едет снимок названия и цены, как у свободной),
    ``k:<pk>`` комбо-набор (VF-9b, фидбэк «товар или комбо просто выбираем из
    каталога»: FK у строки нет — снимок имени/цены, как у услуги; only-jobs —
    приёмник заказа префикса ``k:`` не знает, поэтому за флагом).
    Остаток в подписи — int (локаль-стабильно), только при учёте склада."""
    from apps.catalog.models import Product

    parts = []
    for p in Product.objects.filter(is_active=True).prefetch_related("variants"):
        variants = [v for v in p.variants.all() if v.is_active]
        if variants:
            for v in variants:
                label = f"{p.name_text} · {v.label}"
                title = label
                sku = v.sku or p.sku
                if sku:  # SH-20: артикул в подписи пикера (title — без него: им заполняется текст строки)
                    label += f" · {sku}"
                if v.stock_quantity is not None:
                    label += _(" (Lager: %(n)s)") % {"n": v.stock_quantity}
                parts.append(
                    {
                        "value": f"v:{v.pk}",
                        "label": label,
                        "price": v.price_value,
                        "title": title,
                        "sku": sku,
                        "image": v.image_url or _primary_url(p),  # SH-21: миниатюра в пикере
                    }
                )
        else:
            label = p.name_text
            if p.sku:
                label += f" · {p.sku}"
            if p.stock_quantity is not None:
                label += _(" (Lager: %(n)s)") % {"n": p.stock_quantity}
            parts.append(
                {
                    "value": f"p:{p.pk}",
                    "label": label,
                    "price": p.base_price,
                    "title": p.name_text,
                    "sku": p.sku,
                    "image": _primary_url(p),
                }
            )
    # Комбо-наборы (Menü-Sets кейтеринга и т.п.) — по флагу вызывающего.
    if include_combos:
        from apps.catalog.models import Combo

        for combo in Combo.objects.filter(is_active=True):
            parts.append(
                {
                    "value": f"k:{combo.pk}",
                    "label": str(combo),
                    "price": combo.price,
                    "title": str(combo),
                    "image": combo.primary_image_url,
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
                    "image": getattr(svc, "image_url", "") or "",
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
    """QF-1: (название, цена, ставка НДС) выбранной услуги или (None, None, None).

    У строки сметы нет FK на услугу (склад/леджер её не касаются) — в смету едет
    СНИМОК: правка каталога услуг не переписывает отправленную смету."""
    kind, _, pk = (raw or "").partition(":")
    if kind != "s" or not pk:
        return None, None, None
    from apps.booking.models import Service

    svc = Service.objects.filter(pk=pk, is_active=True).first()
    if svc is None:
        return None, None, None
    # VAT-2: ставка едет тем же снимком, что имя и цена — иначе услуга в смете и
    # в заказе молча считалась бы по 19 %, даже если в её карточке стоит 7 %.
    return str(svc), Decimal(svc.price_cents) / 100, svc.vat_rate


def _combo_snapshot(raw):
    """VF-9b: (название, цена, ставка НДС) выбранного набора или (None, None, None).

    Как у услуги: FK на комбо у строки сметы нет (склад/леджер набора считает
    только заказ) — в смету едет СНИМОК имени и базовой цены."""
    kind, _, pk = (raw or "").partition(":")
    if kind != "k" or not pk:
        return None, None, None
    from apps.catalog.models import Combo

    combo = Combo.objects.filter(pk=pk, is_active=True).first()
    if combo is None:
        return None, None, None
    return str(combo), combo.price, getattr(combo, "vat_rate", None)
