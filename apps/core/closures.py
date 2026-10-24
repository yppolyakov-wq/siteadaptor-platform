"""KA-12 E4.1a: Betriebsferien — закрытие всего бизнеса на дни (отпуск, праздники).

Единственная точка чтения: `booking.ClosedDate` с `resource=None` («весь бизнес»).
Таблица есть в каждой схеме тенанта независимо от модуля booking; запись уже её
читала, теперь — и самовывоз, «открыто сейчас», баннер витрины.

Чтения межсхемно не работают (таблица в схеме тенанта): в public и для «чужого»
тенанта — пусто. Сбой чтения не роняет страницу (лог + «не закрыто»).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import connection

logger = logging.getLogger(__name__)

#: Сколько дней вперёд ищем ближайшее закрытие для баннера.
HORIZON_DAYS = 60
#: Максимальная длина диапазона одной формы.
MAX_RANGE_DAYS = 366


def _own_schema(tenant=None) -> bool:
    """Читать можно только в схеме этого тенанта (таблица — TENANT-приложения).
    В public она есть лишь там, где booking объявлен общим (тестовые настройки)."""
    from django.conf import settings

    schema = connection.schema_name or "public"
    if tenant is not None and getattr(tenant, "schema_name", schema) != schema:
        return False
    if schema == "public":
        return "apps.booking" in getattr(settings, "SHARED_APPS", ())
    return True


def closed_days(start: date, end: date, tenant=None) -> dict:
    """{день: причина} закрытий бизнеса в [start, end] (включительно)."""
    if not _own_schema(tenant) or end < start:
        return {}
    try:
        from apps.booking.models import ClosedDate

        return dict(
            ClosedDate.objects.filter(
                resource__isnull=True, date__gte=start, date__lte=end
            ).values_list("date", "reason")
        )
    except Exception:  # noqa: BLE001 — витрина важнее баннера
        logger.exception("closures: read failed")
        return {}


def is_closed(day: date, tenant=None) -> bool:
    return day in closed_days(day, day, tenant)


def current_or_next(today: date, tenant=None, horizon: int = HORIZON_DAYS):
    """Ближайший сплошной диапазон закрытия, который идёт сейчас или начнётся в
    горизонте: {"von", "bis", "reason", "now"} или None."""
    days = closed_days(today, today + timedelta(days=horizon), tenant)
    if not days:
        return None
    von = min(days)
    bis = von
    while bis + timedelta(days=1) in days:
        bis += timedelta(days=1)
    if bis == today + timedelta(days=horizon):
        # Хвост за горизонтом — дочитать конец диапазона.
        tail = closed_days(bis + timedelta(days=1), bis + timedelta(days=MAX_RANGE_DAYS), tenant)
        while bis + timedelta(days=1) in tail:
            bis += timedelta(days=1)
    return {"von": von, "bis": bis, "reason": days[von], "now": von <= today}


def _span(von: date, bis: date) -> list[date]:
    return [von + timedelta(days=i) for i in range((bis - von).days + 1)]


def valid_range(von, bis) -> bool:
    return von is not None and bis is not None and von <= bis and (bis - von).days <= MAX_RANGE_DAYS


def set_range(von: date, bis: date, *, reason: str = "", resource=None) -> int:
    """Закрыть диапазон (идемпотентно). Возвращает число новых дней."""
    from apps.booking.models import ClosedDate

    span = _span(von, bis)
    existing = set(
        ClosedDate.objects.filter(date__in=span, resource=resource).values_list("date", flat=True)
    )
    new = [
        ClosedDate(date=d, resource=resource, reason=(reason or "")[:120])
        for d in span
        if d not in existing
    ]
    ClosedDate.objects.bulk_create(new)
    _bump()
    return len(new)


def clear_range(von: date, bis: date, *, resource=None) -> int:
    from apps.booking.models import ClosedDate

    deleted, _ = ClosedDate.objects.filter(date__in=_span(von, bis), resource=resource).delete()
    _bump()
    return deleted


def _bump() -> None:
    """Баннер и слоты витрины — из кэша страниц; без сброса закрытие увидели бы поздно."""
    try:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(connection.schema_name)
    except Exception:  # noqa: BLE001
        logger.exception("closures: cache bump failed")
