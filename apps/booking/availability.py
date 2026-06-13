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


def free_slots_with_spots(
    resource, day, duration_minutes=None
) -> list[tuple[datetime, datetime, int]]:
    """[(start, end, spots_left), …] свободных слотов с остатком мест (G9).

    spots_left = capacity − активные пересечения; включаем только слоты, где есть
    место (spots_left > 0). Для групповых курсов (capacity>1) витрина показывает
    «N Plätze frei». duration_minutes (G10): длина слота = длительность услуги.
    """
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
        ).values_list("start", "end", "party_size")
    )
    by_party = resource.counts_party_size  # G9: места = сумма party_size
    result = []
    for start, end in grid:
        taken = sum(
            (party if by_party else 1)
            for b_start, b_end, party in bookings
            if b_start < end and b_end > start
        )
        if taken < resource.capacity:
            result.append((start, end, resource.capacity - taken))
    return result


def free_slots(resource, day, duration_minutes=None) -> list[tuple[datetime, datetime]]:
    """[(start, end), …] свободных слотов (тонкая обёртка над free_slots_with_spots)."""
    return [(s, e) for s, e, _spots in free_slots_with_spots(resource, day, duration_minutes)]


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
