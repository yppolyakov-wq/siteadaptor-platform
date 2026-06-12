"""Booking-календарь / запись по времени (Track D / D3, TENANT).

Запись = интервал времени на ресурсе (стол/мастер/комната/услуга), в отличие от
количественного резерва акций (promotions.Reservation). Анти-двойное-бронирование
— атомарная проверка пересечений интервалов под блокировкой ресурса
(services.book, зеркало anti-oversell). Расписание — недельные правила
(AvailabilityRule) + точечные исключения (ClosedDate).
"""

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Resource(TimestampedModel):
    TYPE_TABLE = "table"
    TYPE_STAFF = "staff"
    TYPE_ROOM = "room"
    TYPE_SERVICE = "service"
    TYPES = [
        (TYPE_TABLE, "Table"),
        (TYPE_STAFF, "Staff"),
        (TYPE_ROOM, "Room"),
        (TYPE_SERVICE, "Service"),
    ]

    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=TYPES, default=TYPE_TABLE)
    # Сколько записей допустимо на один и тот же интервал (стол/мастер = 1,
    # зал/групповая услуга = N).
    capacity = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AvailabilityRule(TimestampedModel):
    """Недельное правило работы ресурса: weekday + окно + шаг слота."""

    WEEKDAYS = [
        (0, "Montag"),
        (1, "Dienstag"),
        (2, "Mittwoch"),
        (3, "Donnerstag"),
        (4, "Freitag"),
        (5, "Samstag"),
        (6, "Sonntag"),
    ]

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="rules")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)  # как date.weekday()
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveSmallIntegerField(default=30)

    class Meta:
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.resource}: {self.get_weekday_display()} {self.start_time}–{self.end_time}"


class ClosedDate(TimestampedModel):
    """Исключение из расписания: выходной/праздник (resource=None — весь бизнес)."""

    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="closed_dates", null=True, blank=True
    )
    date = models.DateField()
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} ({self.reason or 'geschlossen'})"


class Booking(TimestampedModel):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_NO_SHOW = "no_show"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_NO_SHOW, "No-show"),
    ]
    # Статусы, занимающие слот (пересечения считаем только по ним).
    ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED)

    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="bookings")
    reference_code = models.CharField(max_length=12, unique=True)  # "T-XXXXXX"
    start = models.DateTimeField()
    end = models.DateTimeField()
    party_size = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    # Напоминание (D3c, beat): чтобы слать ровно одно.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start"]
        indexes = [
            # Поиск пересечений по ресурсу/интервалу и календарь-вид.
            models.Index(fields=["resource", "start"], name="booking_resource_start_idx"),
            models.Index(fields=["status", "start"], name="booking_status_start_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.resource} {self.start:%d.%m %H:%M}"
