"""Доступность юнитов по датам (Track E / E1).

``range_available`` — пер-ночная проверка занятости (активные брони + блоки <
quantity). Источник истины при создании — services.book_stay (вызывает эту
функцию под блокировкой строки юнита); здесь же — UI-подсказка для витрины/
кабинета (E2/E3). ``free_units`` — подбор свободных юнитов на диапазон.
"""

from datetime import timedelta

from .models import StayBooking, StayUnit, UnitBlock


def nights_between(arrival, departure) -> list:
    """Список дат-ночей ``[arrival, departure)`` (день выезда не входит)."""
    out, day = [], arrival
    while day < departure:
        out.append(day)
        day += timedelta(days=1)
    return out


def range_available(unit, arrival, departure, *, exclude_pk=None) -> bool:
    """Есть ли на КАЖДУЮ ночь ``[arrival, departure)`` свободный из quantity юнитов.

    Считает занятость по ночам в памяти (как booking.free_slots): активные брони
    юнита, пересекающие диапазон, + блоки. Под блокировкой строки юнита (её ставит
    services.book_stay) это и есть атомарная anti-overbook-гарантия.
    """
    nights = nights_between(arrival, departure)
    if not nights:
        return False
    last_night = nights[-1]

    stays = StayBooking.objects.filter(
        unit=unit,
        status__in=StayBooking.ACTIVE_STATUSES,
        arrival__lt=departure,
        departure__gt=arrival,
    )
    if exclude_pk is not None:
        stays = stays.exclude(pk=exclude_pk)
    stays = list(stays.values_list("arrival", "departure"))

    blocks = list(
        UnitBlock.objects.filter(
            unit=unit, start_date__lte=last_night, end_date__gte=arrival
        ).values_list("start_date", "end_date")
    )

    for night in nights:
        occupied = sum(1 for s_arr, s_dep in stays if s_arr <= night < s_dep)
        occupied += sum(1 for b_start, b_end in blocks if b_start <= night <= b_end)
        if occupied >= unit.quantity:
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
