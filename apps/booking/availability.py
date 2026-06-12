"""Свободные слоты ресурса на день (Track D / D3b).

Сетка из недельных правил (AvailabilityRule: окно + шаг), минус исключения
(ClosedDate), минус заполненные интервалы (активные брони >= capacity), минус
прошедшее время на сегодня. Источник истины при создании — services.book
(атомарная проверка); слоты здесь — UI-подсказка, гонку закрывает сервис.
"""

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Booking, ClosedDate


def is_closed(resource, day) -> bool:
    return (
        ClosedDate.objects.filter(date=day)
        .filter(Q(resource=resource) | Q(resource__isnull=True))
        .exists()
    )


def free_slots(resource, day) -> list[tuple[datetime, datetime]]:
    """[(start, end), …] свободных слотов ресурса на дату (aware, локальная TZ)."""
    if is_closed(resource, day):
        return []

    tz = timezone.get_current_timezone()
    now = timezone.now()
    grid = []
    for rule in resource.rules.filter(weekday=day.weekday()):
        cursor = datetime.combine(day, rule.start_time, tzinfo=tz)
        window_end = datetime.combine(day, rule.end_time, tzinfo=tz)
        step = timedelta(minutes=rule.slot_minutes)
        while cursor + step <= window_end:
            if cursor > now:  # прошедшие слоты сегодня не предлагаем
                grid.append((cursor, cursor + step))
            cursor += step

    if not grid:
        return []

    # Заполненность: активные брони дня одним запросом, пересечения считаем в памяти.
    day_start = min(start for start, _end in grid)
    day_end = max(end for _start, end in grid)
    bookings = list(
        Booking.objects.filter(
            resource=resource,
            status__in=Booking.ACTIVE_STATUSES,
            start__lt=day_end,
            end__gt=day_start,
        ).values_list("start", "end")
    )
    return [
        (start, end)
        for start, end in grid
        if sum(1 for b_start, b_end in bookings if b_start < end and b_end > start)
        < resource.capacity
    ]
