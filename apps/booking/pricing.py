"""HF-5: цена услуги на конкретную дату (сезонные тарифы).

Приоритет: `ServiceSeasonRate` (диапазон дат) → базовая цена услуги. Зеркало
`stays.pricing.nightly_price_cents`; отдельный модуль, чтобы цена считалась в
ОДНОМ месте — им пользуются и витрина (показ), и приём брони (что списываем).
"""


def price_cents_for(service, day, seasons=None) -> int:
    """Цена услуги на день `day` в центах (базовая, если сезона нет)."""
    if day is None:
        return service.price_cents
    seasons = service.season_rates.all() if seasons is None else seasons
    for rate in seasons:
        if rate.start_date <= day <= rate.end_date:
            return rate.price_cents
    return service.price_cents


def season_label_for(service, day, seasons=None) -> str:
    """Подпись сезона для дня («Feiertage») или "" — для честного показа цены."""
    if day is None:
        return ""
    seasons = service.season_rates.all() if seasons is None else seasons
    for rate in seasons:
        if rate.start_date <= day <= rate.end_date:
            return rate.label
    return ""
