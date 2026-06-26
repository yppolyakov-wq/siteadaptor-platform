"""Booking-календарь / запись по времени (Track D / D3, TENANT).

Запись = интервал времени на ресурсе (стол/мастер/комната/услуга), в отличие от
количественного резерва акций (promotions.Reservation). Анти-двойное-бронирование
— атомарная проверка пересечений интервалов под блокировкой ресурса
(services.book, зеркало anti-oversell). Расписание — недельные правила
(AvailabilityRule) + точечные исключения (ClosedDate).
"""

from django.db import models
from django.utils import timezone

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
    # G9: считать вместимость по сумме party_size (групповой курс: «ich + 3
    # Freunde» = 4 места), а не по числу броней. False (умолч.) — стол/мастер/зал,
    # где бронь = 1 единица, party_size информативен (не ломаем рестораны).
    counts_party_size = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # P2.5b: депозит за запись (центы; 0 = без депозита). Анти-no-show.
    deposit_cents = models.PositiveIntegerField(default=0)
    # Анти-фрод: даже после оплаты держать бронь pending до ручного подтверждения
    # бизнесом (по умолчанию оплата сразу авто-подтверждает).
    require_manual_confirm = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Service(TimestampedModel):
    """Услуга с ценой и длительностью (G10): «Ölwechsel — 30 мин, 49 €».

    Бизнес-уровень: бронируется на любом свободном ресурсе под её длительность
    (привязка к конкретным мастерам/постам — отложено). Цена → выручка при
    выполнении (fulfilled); депозит — как у Resource (анти-no-show, P2.5b)."""

    name = models.CharField(max_length=120)
    # A3: описание услуги («что входит») — богатая карточка на витрине; пусто = не показываем.
    description = models.TextField(blank=True)
    # A3: фото услуги (FileRef-конверт {url, alt, …}, как обложка) — богатая карточка;
    # пусто = карточка без фото (как раньше).
    image = models.JSONField(default=dict, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    price_cents = models.PositiveIntegerField(default=0)
    deposit_cents = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100

    @property
    def image_url(self) -> str:
        """A3: URL фото услуги (или ''), безопасно к не-dict значению."""
        return self.image.get("url", "") if isinstance(self.image, dict) else ""


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


class Pass(TimestampedModel):
    """Mehrfachkarte / 10er-Karte (G9): пакет визитов клиента.

    Владелец выпускает карту (продажа офлайн/на стойке), клиент гасит по коду
    онлайн при записи или владелец вручную в кабинете. Один кредит = один визит;
    списание атомарно (services.redeem_pass). Привязка к курсу/услуге — отложено
    (карта общая)."""

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="passes")
    label = models.CharField(max_length=120, default="Mehrfachkarte")
    code = models.CharField(max_length=12, unique=True)  # "K-XXXXXX"
    credits_total = models.PositiveSmallIntegerField(default=10)
    credits_used = models.PositiveSmallIntegerField(default=0)
    valid_until = models.DateField(null=True, blank=True)  # пусто = бессрочно
    is_active = models.BooleanField(default=True)
    # A3: карта может быть привязана к конкретной услуге/курсу (null = любая).
    service = models.ForeignKey(
        "Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="passes"
    )
    # A3: онлайн-продажа (Stripe) — id платежа для идемпотентности выпуска.
    stripe_payment_intent = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label} {self.code} ({self.credits_left}/{self.credits_total})"

    @property
    def credits_left(self) -> int:
        return max(0, self.credits_total - self.credits_used)

    @property
    def is_valid(self) -> bool:
        if not self.is_active or self.credits_left <= 0:
            return False
        return self.valid_until is None or self.valid_until >= timezone.localdate()


class PassPlan(TimestampedModel):
    """A3: покупаемый онлайн тариф Mehrfachkarte (бизнес задаёт в кабинете).

    Покупка через Stripe Connect выпускает клиенту Pass с этими параметрами
    (credits/срок/привязка к услуге)."""

    label = models.CharField(max_length=120, default="Mehrfachkarte")
    credits = models.PositiveSmallIntegerField(default=10)
    price_cents = models.PositiveIntegerField(default=0)
    valid_days = models.PositiveSmallIntegerField(default=0)  # 0 = бессрочно
    service = models.ForeignKey(
        "Service", on_delete=models.SET_NULL, null=True, blank=True, related_name="pass_plans"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_cents", "label"]

    def __str__(self):
        return f"{self.label} ({self.credits}× / {self.price_cents / 100:.2f})"

    @property
    def price_eur(self):
        from decimal import Decimal

        return Decimal(self.price_cents) / 100


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
    # G10: услуга (опц.) — null = общая бронь по времени (стол/комната). SET_NULL:
    # удаление услуги не трогает брони, снимок цены остаётся.
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )
    price_cents = models.PositiveIntegerField(default=0)  # снимок цены услуги
    # G9: Mehrfachkarte, которой оплачен визит (SET_NULL — карту можно аннулировать,
    # бронь остаётся). null = обычная оплата/депозит/без карты.
    card = models.ForeignKey(
        "Pass", on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )
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

    # P2.5b: онлайн-депозит через Stripe Connect (деньги → бизнесу напрямую).
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
    deposit_cents = models.PositiveIntegerField(default=0)  # снимок с ресурса
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_NONE)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # для refund
    # #7: снимок выбранных Extras [{label, price_cents}] — сумма входит в total_cents
    # (выручку), переживает изменение/удаление Extra.
    extras = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["start"]
        indexes = [
            # Поиск пересечений по ресурсу/интервалу и календарь-вид.
            models.Index(fields=["resource", "start"], name="booking_resource_start_idx"),
            models.Index(fields=["status", "start"], name="booking_status_start_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.resource} {self.start:%d.%m %H:%M}"

    @property
    def price_eur(self) -> float:
        return self.price_cents / 100

    @property
    def extras_cents(self) -> int:
        """Сумма выбранных Extras (#7), центы."""
        return sum(int(e.get("price_cents", 0)) for e in (self.extras or []))

    @property
    def total_cents(self) -> int:
        """Итого = цена услуги + Extras (выручка/отображение)."""
        return self.price_cents + self.extras_cents

    @property
    def total_eur(self) -> float:
        return self.total_cents / 100
