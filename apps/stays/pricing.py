"""Цена за ночь с учётом сезонных/выходных тарифов (A5a).

Приоритет: SeasonRate (диапазон дат) → выходная цена (Fr/Sa, если задана) →
базовая цена юнита. quote_total суммирует по ночам [arrival, departure).
"""

from .availability import nights_between

WEEKEND_WEEKDAYS = (4, 5)  # ночь пятницы и субботы (Mo=0 … So=6)


def nightly_price_cents(unit, day, seasons=None) -> int:
    seasons = unit.season_rates.all() if seasons is None else seasons
    for rate in seasons:
        if rate.start_date <= day <= rate.end_date:
            return rate.price_cents
    if day.weekday() in WEEKEND_WEEKDAYS and unit.weekend_price_cents:
        return unit.weekend_price_cents
    return unit.price_cents


def quote_total_cents(unit, arrival, departure) -> int:
    """Итог за диапазон с учётом тарифов (сумма по ночам)."""
    seasons = list(unit.season_rates.all())
    return sum(
        nightly_price_cents(unit, day, seasons) for day in nights_between(arrival, departure)
    )
