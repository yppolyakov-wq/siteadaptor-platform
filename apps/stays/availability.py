"""Доступность юнитов по датам (Track E / E1).

``range_available`` — пер-ночная проверка занятости (активные брони + блоки <
quantity). Источник истины при создании — services.book_stay (вызывает эту
функцию под блокировкой строки юнита); здесь же — UI-подсказка для витрины/
кабинета (E2/E3). ``free_units`` — подбор свободных юнитов на диапазон.
"""

import calendar
from datetime import date, timedelta

from apps.core import status_registry

from .models import StayBooking, StayUnit, UnitBlock


def nights_between(arrival, departure) -> list:
    """Список дат-ночей ``[arrival, departure)`` (день выезда не входит)."""
    out, day = [], arrival
    while day < departure:
        out.append(day)
        day += timedelta(days=1)
    return out


def range_available(unit, arrival, departure, *, exclude_pk=None, needed=1) -> bool:
    """Есть ли на КАЖДУЮ ночь ``[arrival, departure)`` место для ``needed`` номеров.

    Считает занятость по ночам в памяти (как booking.free_slots): активные брони
    юнита (каждая занимает свои ``rooms`` номеров, G5), пересекающие диапазон, +
    блоки. Под блокировкой строки юнита (её ставит services.book_stay) это и есть
    атомарная anti-overbook-гарантия. ``needed`` — сколько номеров нужно (мульти-
    бронь): свободно, если quantity − занятость ≥ needed на каждую ночь.
    """
    nights = nights_between(arrival, departure)
    if not nights:
        return False
    last_night = nights[-1]

    stays = StayBooking.objects.filter(
        unit=unit,
        status__in=status_registry.active_statuses_for("stay"),
        arrival__lt=departure,
        departure__gt=arrival,
    )
    if exclude_pk is not None:
        stays = stays.exclude(pk=exclude_pk)
    stays = list(stays.values_list("arrival", "departure", "rooms"))

    blocks = list(
        UnitBlock.objects.filter(
            unit=unit, start_date__lte=last_night, end_date__gte=arrival
        ).values_list("start_date", "end_date")
    )

    for night in nights:
        occupied = sum(rooms for s_arr, s_dep, rooms in stays if s_arr <= night < s_dep)
        occupied += sum(1 for b_start, b_end in blocks if b_start <= night <= b_end)
        if occupied + needed > unit.quantity:
            return False
    return True


def free_units(arrival, departure, *, guests=1) -> list:
    """Активные юниты, свободные на весь диапазон и вмещающие ``guests`` гостей."""
    nights = (departure - arrival).days
    return [
        unit
        for unit in StayUnit.objects.filter(is_active=True, max_guests__gte=guests)
        if nights >= unit.min_nights and range_available(unit, arrival, departure)
    ]


def occupancy_grid(units, start_day, num_days):
    """Календарь загрузки для кабинета (E2): ``(days, rows)``.

    ``days`` — список дат окна; ``rows`` — список ``(unit, cells)``, где cell =
    ``{day, free, blocked}`` (free = quantity − занятость ночи, blocked — есть
    блокировка). Один запрос броней + блоков на юнит, занятость считаем в памяти.
    """
    end_day = start_day + timedelta(days=num_days)
    days = [start_day + timedelta(days=i) for i in range(num_days)]
    rows = []
    for unit in units:
        stays = list(
            StayBooking.objects.filter(
                unit=unit,
                status__in=status_registry.active_statuses_for("stay"),
                arrival__lt=end_day,
                departure__gt=start_day,
            ).values_list("arrival", "departure", "rooms")
        )
        blocks = list(
            UnitBlock.objects.filter(
                unit=unit, start_date__lt=end_day, end_date__gte=start_day
            ).values_list("start_date", "end_date")
        )
        cells = []
        for day in days:
            occupied = sum(rooms for s_arr, s_dep, rooms in stays if s_arr <= day < s_dep)
            blocked = any(b_start <= day <= b_end for b_start, b_end in blocks)
            occupied += sum(1 for b_start, b_end in blocks if b_start <= day <= b_end)
            cells.append({"day": day, "free": max(0, unit.quantity - occupied), "blocked": blocked})
        rows.append((unit, cells))
    return days, rows


def month_availability(unit, year, month, *, today=None) -> list[dict]:
    """Доступность номера на КАЛЕНДАРНЫЙ месяц для витрины (визуальный календарь, C1).

    Список по дням месяца: ``{date, in_past, free, is_free}``. ``free`` = quantity −
    занятость ночи (активные брони × rooms + блоки), как в ``occupancy_grid`` (один
    проход по броням/блокам — переиспользуем его). ``is_free`` — свободно И не в
    прошлом (день нельзя выбрать как заезд, если он прошёл). ``today`` — «сегодня»
    (по умолчанию ``timezone.localdate()``; считаем через локаль, как RV3).
    """
    from django.utils import timezone

    if today is None:
        today = timezone.localdate()
    first = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    _days, rows = occupancy_grid([unit], first, days_in_month)
    _u, cells = rows[0]
    out = []
    for cell in cells:
        in_past = cell["day"] < today
        out.append(
            {
                "date": cell["day"],
                "in_past": in_past,
                "free": cell["free"],
                "is_free": cell["free"] > 0 and not in_past,
            }
        )
    return out
