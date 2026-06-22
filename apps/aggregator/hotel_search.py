"""H8b: живой поиск по датам для агрегатора отелей.

Доступность живёт в TENANT-схемах, а портал/листинги — в public. Для поиска по
датам идём в схему каждого отеля города и считаем дешевейший свободный номер на
диапазон (анти-овербукинг + тарифы H1). Результат кешируем (Redis, короткий TTL),
чтобы обход схем не повторялся на каждый запрос. Малые объёмы города делают это
дешёвым; при росте — материализованный календарь доступности (отдельный шаг).
"""

from datetime import date

from django.core.cache import cache
from django_tenants.utils import schema_context

CACHE_TTL = 300  # сек — терпимая задержка доступности на портале


def parse_date(raw):
    try:
        return date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


def hotel_availability(tenant_schema, von, bis, guests) -> tuple[bool, int]:
    """(available, from_cents) для отеля на диапазон: дешевейший свободный номер,
    вмещающий ``guests``. Учитывает min_nights, занятость (range_available) и
    тарифы H1 (cheapest). Кеш по (схема, von, bis, guests)."""
    key = f"hotelavail:{tenant_schema}:{von.isoformat()}:{bis.isoformat()}:{guests}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    result = (False, 0)
    nights = (bis - von).days
    if nights >= 1:
        from apps.stays import availability, pricing
        from apps.stays.models import RatePlan, StayUnit

        best = None
        with schema_context(tenant_schema):
            rate_plans = list(RatePlan.objects.filter(is_active=True))
            for unit in StayUnit.objects.filter(is_active=True, max_guests__gte=guests):
                if nights < unit.min_nights:
                    continue
                if not availability.range_available(unit, von, bis):
                    continue
                if rate_plans:
                    cents = min(
                        pricing.quote_total_cents(unit, von, bis, rate_plan=rp) for rp in rate_plans
                    )
                else:
                    cents = pricing.quote_total_cents(unit, von, bis)
                best = cents if best is None else min(best, cents)
        if best is not None:
            result = (True, best)

    cache.set(key, result, CACHE_TTL)
    return result
