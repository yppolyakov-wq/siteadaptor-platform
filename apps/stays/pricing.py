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


def occupancy_adjust(cents, occupancy_pct, rules) -> int:
    """PMS-D: ±Y % к цене ночи по правилу с МАКСИМАЛЬНЫМ подходящим порогом.

    rules — из StaySettings.clean_occupancy_rules(); occupancy_pct 0..100
    (None → без изменений). Правила не суммируются (предсказуемо, паттерн G4)."""
    if occupancy_pct is None:
        return cents
    best = None
    for rule in rules:
        if occupancy_pct >= rule["occupancy"] and (
            best is None or rule["occupancy"] > best["occupancy"]
        ):
            best = rule
    if best is None:
        return cents
    return max(0, round(cents * (100 + best["percent"]) / 100))


def quote_total_cents(
    unit, arrival, departure, rate_plan=None, *, occupancy_by_day=None, occupancy_rules=None
) -> int:
    """Итог за диапазон с учётом сезон/выходных тарифов и тарифа-плана (сумма по ночам).

    PMS-D: occupancy_by_day ({date: 0..100}) + occupancy_rules включают ручную
    динамическую цену ПО НОЧАМ; оба None/пусто — итог байт-в-байт прежний
    (все существующие вызовы не меняются; включает только витрина stays)."""
    seasons = list(unit.season_rates.all())
    total = 0
    for day in nights_between(arrival, departure):
        cents = apply_rate_plan(nightly_price_cents(unit, day, seasons), rate_plan)
        if occupancy_rules and occupancy_by_day is not None:
            cents = occupancy_adjust(cents, occupancy_by_day.get(day), occupancy_rules)
        total += cents
    return total


def gap_discount(unit, arrival, departure, settings, today=None) -> tuple[int, str]:
    """Lücken-Deal (план gap-deal-plan-2026-07-28): (percent, label) | (0, "").

    Промежуток = свободный отрезок ночей (free > 0 в семантике
    range_available), зажатый ПОЛНОСТЬЮ занятыми/блокированными ночами с
    обеих сторон, длиной ≤ gap_max_nights; диапазон гостя должен лежать в нём
    целиком. Передний край «сегодня» границей НЕ считается (иначе всё близкое
    дисконтилось бы)."""
    from datetime import timedelta

    max_nights = int(getattr(settings, "gap_max_nights", 0) or 0)
    if max_nights <= 0:
        return 0, ""
    nights = (departure - arrival).days
    if nights <= 0 or nights > max_nights:
        return 0, ""
    if today is None:
        from django.utils import timezone

        today = timezone.localdate()
    from . import availability

    scan_lo = arrival - timedelta(days=max_nights)
    scan_hi = departure + timedelta(days=max_nights)
    occ = availability.occupancy_by_day(unit, scan_lo, scan_hi)

    def _free(day) -> bool:
        return occ.get(day, 0) < 100

    for day in (arrival + timedelta(days=i) for i in range(nights)):
        if not _free(day):  # запрошенные ночи должны быть свободны
            return 0, ""
    lo = arrival
    while lo > scan_lo and _free(lo - timedelta(days=1)):
        lo -= timedelta(days=1)
    hi = departure
    while hi < scan_hi and _free(hi):
        hi += timedelta(days=1)
    bounded_left = lo > scan_lo and not _free(lo - timedelta(days=1))
    bounded_right = hi < scan_hi and not _free(hi)
    if not (bounded_left and bounded_right):
        return 0, ""
    if lo <= today:  # отрезок упирается в «сегодня» — не люка между бронями
        return 0, ""
    if (hi - lo).days > max_nights:
        return 0, ""
    percent = max(1, min(int(getattr(settings, "gap_discount_percent", 0) or 0), 70))
    return percent, f"Lücken-Deal −{percent}%"


def auto_discount(
    lodging_cents, nights, arrival, today=None, settings=None, *, unit=None, departure=None
) -> tuple[int, str]:
    """G4: авто-скидка на проживание (LOS / Frühbucher / Last-Minute), много правил.

    Возвращает (discount_cents, label). Из всех подходящих правил берём максимальный
    процент (предсказуемо, не суммируем). Считается от ``lodging_cents`` (проживание
    без Extras/Kurtaxe). ``arrival`` + ``today`` дают срок до заезда. Промокод (H4a)
    применяется отдельно, поверх этой скидки.

    Lücken-Deal: при переданных ``unit``+``departure`` скидка короткого
    промежутка между бронями участвует обычным кандидатом (без них — поведение
    байт-в-байт прежнее)."""
    if settings is None:
        from .models import StaySettings

        settings = StaySettings.load()
    if today is None:
        from django.utils import timezone

        today = timezone.localdate()
    from .models import StaySettings

    lead = (arrival - today).days  # дней до заезда
    candidates = []  # (percent, label)
    for rule in settings.clean_auto_rules():
        kind, threshold, percent = rule["kind"], rule["threshold"], rule["percent"]
        if kind == StaySettings.KIND_LOS and nights >= threshold:
            candidates.append((percent, f"−{percent}% ab {threshold} Nächten"))
        elif kind == StaySettings.KIND_EARLY and lead >= threshold:
            candidates.append((percent, f"Frühbucher −{percent}%"))
        elif kind == StaySettings.KIND_LAST and 0 <= lead <= threshold:
            candidates.append((percent, f"Last-Minute −{percent}%"))
    if unit is not None and departure is not None:
        gap_percent, gap_label = gap_discount(unit, arrival, departure, settings, today=today)
        if gap_percent:
            candidates.append((gap_percent, gap_label))
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
