"""Свободные слоты ресурса на день (Track D / D3b).

Сетка из недельных правил (AvailabilityRule: окно + шаг), минус исключения
(ClosedDate), минус заполненные интервалы (активные брони >= capacity), минус
прошедшее время на сегодня. Источник истины при создании — services.book
(атомарная проверка); слоты здесь — UI-подсказка, гонку закрывает сервис.
"""

from datetime import datetime, timedelta

from django.db import connection
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import MAX_BUFFER_MINUTES, Booking, ClosedDate

# Общий горизонт записи на витрине (услуга может задать свой `max_days_ahead`).
DEFAULT_HORIZON_DAYS = 30
# Скан «ближайшего свободного» не дальше этого (каждый день = запросы по пулу).
NEXT_FREE_SCAN_DAYS = 60

#: KA-12 E4.1b: шаг сетки, когда окно взято из часов работы бизнеса (у ресурса нет правил).
HOURS_FALLBACK_STEP = 30


def _business_hours(tenant=None) -> dict:
    from apps.tenants import openinghours

    tenant = tenant if tenant is not None else getattr(connection, "tenant", None)
    if tenant is not None and not hasattr(tenant, "opening_hours_structured"):
        # schema_context в Celery/команде даёт FakeTenant без часов — дочитать настоящий.
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(schema_name=connection.schema_name).first()
    return openinghours.normalize(getattr(tenant, "opening_hours_structured", None))


def day_windows(resource, day, tenant=None) -> list:
    """[(start_time, end_time, slot_minutes)] рабочих окон ресурса в день.

    О-4: правила ресурса сильнее; ресурс БЕЗ единого правила работает в часы бизнеса
    (раньше — ни одного слота, и витрина молча писала «keine freien Termine»)."""
    from apps.tenants import openinghours

    rules = list(resource.rules.all())
    if rules:
        return [
            (r.start_time, r.end_time, r.slot_minutes) for r in rules if r.weekday == day.weekday()
        ]
    rng = _business_hours(tenant).get(str(day.weekday()))
    if not rng:
        return []
    start, end = openinghours._parse_hhmm(rng[0]), openinghours._parse_hhmm(rng[1])
    return [(start, end, HOURS_FALLBACK_STEP)]


def within_hours(resource, start, end, tenant=None) -> bool:
    """Лежит ли [start, end] в рабочем окне ресурса (E4.3). Ни правил, ни часов — не
    знаем, значит не мешаем (True)."""
    if not resource.rules.exists() and not _business_hours(tenant):
        return True
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    if local_start.date() != local_end.date():
        return False
    return any(
        w_start <= local_start.time() and local_end.time() <= w_end
        for w_start, w_end, _step in day_windows(resource, local_start.date(), tenant)
    )


def is_closed(resource, day) -> bool:
    return (
        ClosedDate.objects.filter(date=day)
        .filter(Q(resource=resource) | Q(resource__isnull=True))
        .exists()
    )


def free_slots_with_spots(
    resource, day, duration_minutes=None, buffer_minutes=0, earliest=None
) -> list[tuple[datetime, datetime, int]]:
    """[(start, end, spots_left), …] свободных слотов с остатком мест (G9).

    spots_left = capacity − активные пересечения; включаем только слоты, где есть
    место (spots_left > 0). Для групповых курсов (capacity>1) витрина показывает
    «N Plätze frei». duration_minutes (G10): длина слота = длительность услуги.
    KA-12 E4.4a: buffer_minutes — после слота ресурс занят ещё столько (уборка);
    в часы работы обязан уложиться только сам визит. earliest — минимальный
    срок записи (раньше — не предлагаем).
    """
    if is_closed(resource, day):
        return []

    tz = timezone.get_current_timezone()
    now = timezone.now()
    if earliest is not None and earliest > now:
        now = earliest
    buffer = timedelta(minutes=int(buffer_minutes or 0))
    grid = []
    for w_start, w_end, slot_minutes in day_windows(resource, day):
        cursor = datetime.combine(day, w_start, tzinfo=tz)
        window_end = datetime.combine(day, w_end, tzinfo=tz)
        step = timedelta(minutes=slot_minutes)
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
    from apps.core import status_registry

    bookings = list(
        Booking.objects.filter(
            resource=resource,
            # FB-3 Вариант B: built-in ∪ кастом-active тенанта.
            status__in=status_registry.active_statuses_for("booking"),
            start__lt=day_end + buffer,
            end__gt=day_start - timedelta(minutes=MAX_BUFFER_MINUTES),
        )
        .annotate(busy_until=Coalesce("occupied_until", "end"))
        .filter(busy_until__gt=day_start)
        .values_list("start", "busy_until", "party_size")
    )
    by_party = resource.counts_party_size  # G9: места = сумма party_size
    result = []
    for start, end in grid:
        taken = sum(
            (party if by_party else 1)
            for b_start, b_end, party in bookings
            if b_start < end + buffer and b_end > start
        )
        if taken < resource.capacity:
            result.append((start, end, resource.capacity - taken))
    return result


def free_slots(
    resource, day, duration_minutes=None, buffer_minutes=0, earliest=None
) -> list[tuple[datetime, datetime]]:
    """[(start, end), …] свободных слотов (тонкая обёртка над free_slots_with_spots)."""
    return [
        (s, e)
        for s, e, _spots in free_slots_with_spots(
            resource, day, duration_minutes, buffer_minutes=buffer_minutes, earliest=earliest
        )
    ]


def booking_window(service):
    """KA-12 E4.4a: (earliest, last_day) записи на витрине — минимальный срок и
    горизонт услуги. None — без ограничения."""
    earliest = last_day = None
    lead = int(getattr(service, "min_lead_minutes", 0) or 0)
    if lead:
        earliest = timezone.now() + timedelta(minutes=lead)
    horizon = getattr(service, "max_days_ahead", None) or DEFAULT_HORIZON_DAYS
    last_day = timezone.localdate() + timedelta(days=int(horizon))
    return earliest, last_day


def service_slots(
    service, day, resource=None, duration_minutes=None, base_pool=None
) -> list[datetime]:
    """G10: объединённые свободные старты по ресурсам под услугу.

    Услуга бизнес-уровня — старт доступен, если ХОТЯ БЫ один ресурс свободен на
    [start, start+duration). Ресурс к старту назначается при брони (assign_resource).
    resource (#4) — ограничить выбранным мастером/ресурсом; None = любой.
    duration_minutes (HF-7) — переопределить длину: гость берёт услугу на НЕСКОЛЬКО
    единиц подряд («с 8:30 до 12:30»), тогда сюда приходит N × длительность."""

    length = duration_minutes or service.duration_minutes
    earliest, last_day = booking_window(service)
    if last_day is not None and day > last_day:
        return []
    pool = service_pool(service, resource, base=base_pool)
    buffer = getattr(service, "buffer_after_minutes", 0)
    starts = set()
    for r in pool:
        for start, _end in free_slots(
            r, day, duration_minutes=length, buffer_minutes=buffer, earliest=earliest
        ):
            starts.add(start)
    return sorted(starts)


def service_pool(service, resource=None, base=None) -> list:
    """KA-12 E4.2a: ресурсы, которые оказывают услугу.

    Навыков не задано — все активные (паритет со старыми услугами). Заданы — только
    активные из них; все выключены → пусто (fail-closed: владелец явно ограничил
    услугу, отпуск мастера не открывает её мастерам без квалификации).
    `resource` задан — только он, и только если он в пуле (чужой мастер → пусто).
    `base` — уже посчитанный пул (страница слотов зовёт по дню месяца — без N+1)."""
    pool = base if base is not None else _skill_pool(service)
    if resource is not None:
        return [r for r in pool if r.pk == resource.pk]
    return pool


def _skill_pool(service) -> list:
    from .models import Resource

    if service is not None and getattr(service, "pk", None):
        skills = list(service.resources.all())
        if skills:
            return [r for r in skills if r.is_active]
    return list(Resource.objects.filter(is_active=True))


def has_skill(service, resource) -> bool:
    """Ресурс оказывает услугу — по тому же пулу, что предлагает витрина."""
    if service is None or resource is None or not getattr(service, "pk", None):
        return True
    return any(r.pk == resource.pk for r in _skill_pool(service))


def next_free_slot(service, from_day=None, max_days=60, resource=None):
    """R3 «Nächster freier Termin»: ближайший свободный старт услуги, скан вперёд
    от `from_day` (вкл.) до `max_days` дней. Возвращает datetime первого старта
    или None (нет свободных в горизонте). Перехват уходящего клиента в момент
    отказа (день без слотов → «ближайший свободный: …»)."""
    start = from_day or timezone.localdate()
    base = _skill_pool(service)
    for i in range(min(max_days, NEXT_FREE_SCAN_DAYS) + 1):
        slots = service_slots(service, start + timedelta(days=i), resource=resource, base_pool=base)
        if slots:
            return slots[0]
    return None


def assign_resource(service, start, resource=None, duration_minutes=None):
    """G10: ресурс под услугу на [start, start+duration); None если занят.

    resource задан → проверяем только его (выбор конкретного мастера, #4); иначе
    первый свободный из активных. duration_minutes (HF-7) — длина брони, если гость
    взял несколько единиц подряд."""

    length = duration_minutes or service.duration_minutes
    end = start + timedelta(minutes=length)
    pool = service_pool(service, resource)
    earliest, _last_day = booking_window(service)
    buffer = getattr(service, "buffer_after_minutes", 0)
    for r in pool:
        if (start, end) in free_slots(
            r, start.date(), duration_minutes=length, buffer_minutes=buffer, earliest=earliest
        ):
            return r
    return None
