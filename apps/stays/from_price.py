"""Честная «ab … € / Nacht» номера для каталога города (2026-11-09).

Раньше портал показывал базовую цену номера (`StayUnit.price_cents`) — мимо тарифов,
цен по дням (NightRate), сезонов, стоп-продаж, правил продаж и занятости: «ab 79 €»
могла обещать цену, которой нет ни на одну дату (PAngV), или быть выше реальной.

Здесь — минимум цены ЗА НОЧЬ среди заездов ближайших ``HORIZON_DAYS`` дней, которые
реально можно забронировать онлайн (1 гость, 1 номер, минимальный срок), посчитанный
ТЕМ ЖЕ расчётом, что «ab» витрины отеля (`pricing.from_price_cents`). Ничего не
забронировать → None: портал показывает номер без цены, а не устаревшую цифру.

Дешёвый фильтр в памяти (сетка занятости — два запроса на окно) отсекает заведомо
занятые заезды ДО полного расчёта; решающие проверки — те же функции, что у брони
(`restrictions.violation`, `availability.range_available`).
"""

from datetime import timedelta

from django.utils import timezone

HORIZON_DAYS = 60
MAX_NIGHTS = 30  # правило «минимум N ночей» длиннее — заезд не считаем (защита цикла)


def lowest_nightly_cents(unit, *, today=None, horizon: int = HORIZON_DAYS) -> int | None:
    """Наименьшая цена за ночь (центы, округление ВВЕРХ — цену не занижаем) или None."""
    from .models import StaySettings

    with StaySettings.memo():  # одна строка настроек на весь расчёт
        return _lowest(unit, today=today, horizon=horizon)


def _lowest(unit, *, today, horizon):
    from . import availability, pricing, restrictions
    from . import rate_plans as rate_plans_mod

    if not unit.is_active or unit.max_guests < 1:
        return None
    today = today or timezone.localdate()
    plans = rate_plans_mod.plans_for(unit, rate_plans_mod.active_plans())
    _days, rows = availability.occupancy_grid([unit], today, horizon + MAX_NIGHTS)
    free = {cell["day"]: cell["free"] for cell in rows[0][1]} if rows else {}
    base_nights = max(1, unit.min_nights)
    best = None
    for offset in range(horizon):
        arrival = today + timedelta(days=offset)
        nights = base_nights
        if any(free.get(arrival + timedelta(days=k), 0) < 1 for k in range(nights)):
            continue
        hit = restrictions.violation(unit, arrival, arrival + timedelta(days=nights), today=today)
        if hit and hit[0] == "rule_min_nights" and hit[1] and nights < hit[1] <= MAX_NIGHTS:
            nights = hit[1]
            if any(free.get(arrival + timedelta(days=k), 0) < 1 for k in range(nights)):
                continue
            hit = restrictions.violation(
                unit, arrival, arrival + timedelta(days=nights), today=today
            )
        if hit:
            continue
        departure = arrival + timedelta(days=nights)
        if not availability.range_available(unit, arrival, departure):
            continue
        total = pricing.from_price_cents(unit, arrival, departure, plans)
        per_night = -(-total // nights)
        if best is None or per_night < best:
            best = per_night
    return best
