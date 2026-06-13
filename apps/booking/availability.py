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


def free_slots(resource, day, duration_minutes=None) -> list[tuple[datetime, datetime]]:
    """[(start, end), …] свободных слотов ресурса на дату (aware, локальная TZ).

    duration_minutes (G10): длина слота = длительность услуги, шаг = slot_minutes
    правила (старты каждые slot_minutes). None — длина = шаг (общая бронь, D3b)."""
    if is_closed(resource, day):
        return []

    tz = timezone.get_current_timezone()
    now = timezone.now()
    grid = []
    for rule in resource.rules.filter(weekday=day.weekday()):
        cursor = datetime.combine(day, rule.start_time, tzinfo=tz)
        window_end = datetime.combine(day, rule.end_time, tzinfo=tz)
        step = timedelta(minutes=rule.slot_minutes)
        length = timedelta(minutes=duration_minutes) if duration_minutes else step
        while cursor + length <= window_end:
            if cursor > now:  # прошедшие слоты сегодня не предлагаем
                grid.append((cursor, cursor + length))
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


def service_slots(service, day) -> list[datetime]:
    """G10: объединённые свободные старты по всем активным ресурсам под услугу.

    Услуга бизнес-уровня — старт доступен, если ХОТЯ БЫ один ресурс свободен на
    [start, start+duration). Ресурс к старту назначается при брони (assign_resource)."""
    from .models import Resource

    starts = set()
    for resource in Resource.objects.filter(is_active=True):
        for start, _end in free_slots(resource, day, duration_minutes=service.duration_minutes):
            starts.add(start)
    return sorted(starts)


def assign_resource(service, start):
    """G10: первый активный ресурс, свободный на [start, start+duration); или None."""
    from .models import Resource

    end = start + timedelta(minutes=service.duration_minutes)
    for resource in Resource.objects.filter(is_active=True):
        if (start, end) in free_slots(
            resource, start.date(), duration_minutes=service.duration_minutes
        ):
            return resource
    return None
