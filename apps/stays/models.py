"""Date-range-Buchung / Übernachtung (Track E / E1, TENANT).

Движок «по ночам» — параллель apps.booking (по времени суток). Бронь = диапазон
дат ``[arrival, departure)`` (ночь выезда снова свободна); инвентарь = StayUnit с
``quantity`` идентичных юнитов (Ferienwohnung = 1, «Doppelzimmer» = N). Анти-
овербукинг — атомарная пер-ночная проверка занятости под блокировкой строки юнита
(services.book_stay, зеркало anti-oversell/booking). Переиспользуем Customer,
Stripe-Connect-оплату (P2.5b/c), finance, notifications и реестр модулей.
"""

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class StayUnit(TimestampedModel):
    """Тип размещения. ``quantity`` — сколько идентичных юнитов этого типа
    доступно за ночь (анти-овербукинг пускает, пока занятость ночи < quantity).
    Ferienwohnung/Ferienhaus = 1, «Doppelzimmer ×3» = 3."""

    TYPE_ROOM = "room"
    TYPE_APARTMENT = "apartment"
    TYPE_HOUSE = "house"
    TYPE_BED = "bed"
    TYPE_PITCH = "pitch"
    TYPES = [
        (TYPE_ROOM, "Zimmer"),
        (TYPE_APARTMENT, "Ferienwohnung"),
        (TYPE_HOUSE, "Ferienhaus"),
        (TYPE_BED, "Bett (Schlafsaal)"),
        (TYPE_PITCH, "Stellplatz"),
    ]

    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=TYPES, default=TYPE_ROOM)
    description = models.TextField(blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)
    # Цена за ночь (центы, брутто; Stripe-native). Итого = ночи × price_cents.
    price_cents = models.PositiveIntegerField(default=0)
    # A5a: цена за ночь в Fr/Sa, если задана (0 = как обычная). Сезонные окна —
    # в SeasonRate (перебивают и базу, и выходные).
    weekend_price_cents = models.PositiveIntegerField(default=0)
    min_nights = models.PositiveSmallIntegerField(default=1)
    max_guests = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    # P2.5b-аналог: депозит за бронь (центы; 0 = без депозита). Анти-no-show.
    deposit_cents = models.PositiveIntegerField(default=0)
    # Даже после оплаты держать бронь pending до ручного подтверждения бизнесом.
    require_manual_confirm = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100

    @property
    def deposit_eur(self) -> float:
        return self.deposit_cents / 100

    @property
    def weekend_price_eur(self) -> float:
        return self.weekend_price_cents / 100


class SeasonRate(TimestampedModel):
    """Сезонный тариф юнита (A5a): цена за ночь на диапазон дат [start, end]
    включительно. Перебивает базовую и выходную цену. Окна не должны
    пересекаться (гард — на стороне кабинета); при пересечении берётся первое."""

    unit = models.ForeignKey(StayUnit, on_delete=models.CASCADE, related_name="season_rates")
    label = models.CharField(max_length=120, blank=True)  # «Hochsaison», «Weihnachten»
    start_date = models.DateField()
    end_date = models.DateField()  # включительно
    price_cents = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.unit}: {self.start_date}–{self.end_date}"

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100


class UnitBlock(TimestampedModel):
    """Блокировка дат юнита (ремонт/своё проживание/Wartung). Занимает ночи
    ``[start_date, end_date]`` ВКЛЮЧИТЕЛЬНО — считается как занятость при подборе
    (в отличие от брони, где departure — день выезда, уже свободный)."""

    unit = models.ForeignKey(StayUnit, on_delete=models.CASCADE, related_name="blocks")
    start_date = models.DateField()
    end_date = models.DateField()  # последняя заблокированная ночь (включительно)
    reason = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.unit}: {self.start_date}–{self.end_date}"


class StayBooking(TimestampedModel):
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
    # Статусы, занимающие ночи (пересечения считаем только по ним).
    ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED)

    unit = models.ForeignKey(StayUnit, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="stays")
    reference_code = models.CharField(max_length=12, unique=True)  # "S-XXXXXX"
    arrival = models.DateField()
    departure = models.DateField()
    guests = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    # Напоминание перед заездом (beat, E3): чтобы слать ровно одно.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    # Снимок цены за ночь (центы) на момент брони — цена юнита может меняться.
    price_cents = models.PositiveIntegerField(default=0)
    # Снимок ИТОГА (центы) — с учётом сезонных/выходных тарифов (A5a). Считается
    # в services.book_stay/move_stay (pricing.quote_total); finance берёт его.
    total_cents = models.PositiveIntegerField(default=0)

    # P2.5b/c reuse: депозит/предоплата через Stripe Connect (деньги → бизнесу).
    PAYMENT_NONE = "none"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_NONE, "None"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]
    deposit_cents = models.PositiveIntegerField(default=0)  # снимок с юнита
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_NONE)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # для refund

    class Meta:
        ordering = ["arrival"]
        indexes = [
            # Поиск пересечений по юниту/дате и календарь загрузки.
            models.Index(fields=["unit", "arrival"], name="stay_unit_arrival_idx"),
            models.Index(fields=["status", "arrival"], name="stay_status_arrival_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.unit} {self.arrival:%d.%m}–{self.departure:%d.%m}"

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days

    @property
    def total_eur(self):
        from decimal import Decimal

        return Decimal(self.total_cents) / 100
