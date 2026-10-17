"""В5 V5-5: обращение/сделка на витрине бизнеса → строка статистики каталога города.

Пишем только если человек пришёл из каталога города (канал `portal`/`entdecken`,
см. `apps.core.attribution`). Карточка строки:
1. `cl` из ссылки портала — если это листинг ЭТОГО бизнеса (чужой отбрасывается);
2. иначе — листинг самого объекта сделки (акция, услуга, номер, событие, товар);
3. иначе — строка «бизнес целиком» (тот же ключ, что у просмотра профиля, V5-2).

Запись — после коммита и fail-safe: учёт никогда не ломает сделку.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BUSINESS_KEY = ("business", "business")


def _schema(request) -> str:
    tenant = getattr(request, "tenant", None)
    schema = getattr(tenant, "schema_name", "") or ""
    return "" if schema == "public" else schema


def _order_key(order):
    products, combos = set(), set()
    for item in order.items.all():
        if item.product_id:
            products.add(item.product_id)
        elif item.combo_id:
            combos.add(item.combo_id)
    if len(products) == 1 and not combos:
        return ("product", str(next(iter(products))))
    if len(combos) == 1 and not products:
        return ("menu", str(next(iter(combos))))
    return None


def _event_key(event):
    from .tasks import _event_group_ref

    return ("event", _event_group_ref(event) or str(event.pk))


_REF_KINDS = {"product": "product", "stay": "stay", "service": "service", "promotion": "promotion"}


def object_key(kind: str, obj):
    """(listing_kind, source_ref) листинга, который продаёт этот объект, или None."""
    if kind in ("reservation", "coupon"):
        return ("promotion", str(obj.promotion_id))
    if kind == "promo_order":
        return ("promotion", str(obj.pk))
    if kind == "booking":
        return ("service", str(obj.service_id)) if obj.service_id else None
    if kind == "stay":
        return ("stay", str(obj.unit_id))
    if kind == "ticket":
        return _event_key(obj.event)
    if kind == "order":
        return _order_key(obj)
    if kind == "conversation":
        ref_kind, ref_id = (obj.ref_kind or ""), (obj.ref_id or "")
        if not ref_id:
            return None
        if ref_kind in _REF_KINDS:
            return (_REF_KINDS[ref_kind], ref_id)
        if ref_kind == "tour":
            return ("event", f"tour:{ref_id}")
        if ref_kind == "event":
            from apps.events.models import Event

            event = Event.objects.filter(pk=ref_id).first()
            return _event_key(event) if event else None
    return None


def _target(request, attribution, kind, obj):
    """Листинг-цель (или None — тогда строка бизнеса). Схема — только из request.tenant."""
    from .models import AggregatorListing

    schema = _schema(request)
    rows = AggregatorListing.objects.filter(tenant_schema=schema)
    if attribution.listing:
        # только карточка, которую портал сейчас показывает (скрытая/истёкшая — нет)
        listing = rows.public().filter(pk=attribution.listing).first()
        if listing is not None:
            return listing
    key = object_key(kind, obj)
    if key:
        return rows.filter(listing_kind=key[0], source_ref=key[1]).first()
    return None


def _write(request, attribution, action, kind, obj, once_key):
    from . import portal_stats

    schema = _schema(request)
    if not schema:
        return
    tenant = request.tenant
    listing = _target(request, attribution, kind, obj)
    if listing is not None:
        portal_stats.record(
            request,
            action=action,
            channel=attribution.channel,
            listings=[listing],
            once_key=once_key,
        )
    else:
        portal_stats.record(
            request,
            action=action,
            channel=attribution.channel,
            tenant_schema=schema,
            kind=BUSINESS_KEY[0],
            ref=BUSINESS_KEY[1],
            is_demo=bool(getattr(tenant, "is_demo", False)),
            once_key=once_key,
        )


def count(request, action: str, kind: str, obj, *, attribution=None, once_key: str = "") -> None:
    """Засчитать обращение/сделку из каталога города. Зовётся ПОСЛЕ создания объекта;
    сама запись — после коммита. Никогда не бросает."""
    try:
        from django.db import transaction

        from apps.core import attribution as attr

        from .models import PortalStat

        found = attribution if attribution is not None else attr.resolve(request)
        if found.channel not in PortalStat.CHANNEL_CODES or obj is None:
            return
        key = once_key or f"{kind}:{obj.pk}"
        transaction.on_commit(lambda: _safe_write(request, found, action, kind, obj, key))
    except Exception as exc:  # noqa: BLE001 — учёт не смеет ломать сделку
        logger.warning("portal conversion count failed: %s", type(exc).__name__)


def _safe_write(request, found, action, kind, obj, key) -> None:
    try:
        _write(request, found, action, kind, obj, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("portal conversion write failed: %s", type(exc).__name__)
