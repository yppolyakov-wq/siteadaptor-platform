"""Цена за ночь с учётом сезонных/выходных тарифов (A5a) и тарифа-плана (H1).

Приоритет посуточной базы: SeasonRate (диапазон дат) → выходная цена (Fr/Sa, если
задана) → базовая цена юнита. Поверх базы — модификатор RatePlan (процент + надбавка
за ночь). quote_total суммирует по ночам [arrival, departure).
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


def apply_rate_plan(base_cents, rate_plan) -> int:
    """Наложить тариф (H1) на посуточную базу: процент, затем надбавка за ночь.
    ``rate_plan`` — RatePlan или duck-объект с ``percent_adjust``/``surcharge_cents``
    (снимок при переносе); None → база без изменений. Не уходит ниже нуля."""
    if rate_plan is None:
        return base_cents
    percent = getattr(rate_plan, "percent_adjust", 0) or 0
    surcharge = getattr(rate_plan, "surcharge_cents", 0) or 0
    adjusted = round(base_cents * (100 + percent) / 100) + surcharge
    return max(0, adjusted)


def quote_total_cents(unit, arrival, departure, rate_plan=None) -> int:
    """Итог за диапазон с учётом сезон/выходных тарифов и тарифа-плана (сумма по ночам)."""
    seasons = list(unit.season_rates.all())
    return sum(
        apply_rate_plan(nightly_price_cents(unit, day, seasons), rate_plan)
        for day in nights_between(arrival, departure)
    )


def auto_discount(lodging_cents, nights, arrival, today=None, settings=None) -> tuple[int, str]:
    """G4: авто-скидка на проживание (LOS / Frühbucher / Last-Minute).

    Возвращает (discount_cents, label). Скидки НЕ суммируются — берём максимальную
    применимую (предсказуемо, без переусердствования). Считается от ``lodging_cents``
    (проживание без Extras/Kurtaxe). ``arrival`` + ``today`` дают срок до заезда.
    Промокод (H4a) применяется отдельно, поверх этой скидки.
    """
    if settings is None:
        from .models import StaySettings

        settings = StaySettings.load()
    if today is None:
        from django.utils import timezone

        today = timezone.localdate()
    lead = (arrival - today).days  # дней до заезда
    candidates = []  # (percent, label)
    los_n = getattr(settings, "los_min_nights", 0) or 0
    los_p = getattr(settings, "los_discount_percent", 0) or 0
    if los_n and los_p and nights >= los_n:
        candidates.append((los_p, f"−{los_p}% ab {los_n} Nächten"))
    eb_d = getattr(settings, "early_bird_days", 0) or 0
    eb_p = getattr(settings, "early_bird_percent", 0) or 0
    if eb_d and eb_p and lead >= eb_d:
        candidates.append((eb_p, f"Frühbucher −{eb_p}%"))
    lm_d = getattr(settings, "last_minute_days", 0) or 0
    lm_p = getattr(settings, "last_minute_percent", 0) or 0
    if lm_d and lm_p and 0 <= lead <= lm_d:
        candidates.append((lm_p, f"Last-Minute −{lm_p}%"))
    if not candidates:
        return 0, ""
    percent, label = max(candidates, key=lambda c: c[0])
    return round(max(0, lodging_cents) * percent / 100), label


def prepayment_cents(total_cents, rate_plan) -> int:
    """G7: сумма онлайн-предоплаты по тарифу (% от итога). 0 — тариф без предоплаты."""
    pct = (getattr(rate_plan, "prepayment_percent", 0) or 0) if rate_plan is not None else 0
    return round(max(0, total_cents) * pct / 100) if pct > 0 else 0


def kurtaxe_total_cents(adults, nights, settings=None) -> int:
    """Kurtaxe за бронь (H9): adults × ночи × ставка. Дети бесплатно (по умолчанию).
    settings — StaySettings (грузим, если не передан); 0/выключено → 0."""
    if settings is None:
        from .models import StaySettings

        settings = StaySettings.load()
    rate = getattr(settings, "kurtaxe_cents", 0) or 0
    return max(0, int(adults)) * max(0, int(nights)) * rate
