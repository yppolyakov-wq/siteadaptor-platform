"""Событие/ретрит с платным билетом и ростером участников (A6, TENANT).

Event — мероприятие на дату с вместимостью и ценой за место; Ticket — билет
клиента (несколько мест + анкета). Анти-овердрафт мест — атомарно под блокировкой
строки Event (services.book_ticket, зеркало anti-oversell). Оплата — Stripe
Connect (как P2.5/E4, A6c), выручка — в finance. Переиспуем Customer/notifications/
реестр модулей. Покрывает A6: Konzert/Workshop/Yoga/Retreat/Tour с билетами.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Event(TimestampedModel):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    # 0 = без лимита мест; иначе анти-овердрафт пускает, пока продано < capacity.
    capacity = models.PositiveIntegerField(default=0)
    price_cents = models.PositiveIntegerField(default=0)  # за одно место (брутто)
    # Анкета участника: список вопросов (метки). Ответы — в Ticket.answers.
    questions = models.JSONField(default=list, blank=True)
    # A6: программа ретрита/мероприятия — список строк-пунктов (агенда). Показ
    # на странице события; пусто = блок скрыт.
    program = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_DRAFT)
    # Даже после оплаты держать билет pending до ручного подтверждения.
    require_manual_confirm = models.BooleanField(default=False)
    # Фото места/мероприятия: FileRef-список (как catalog.Product.images).
    images = models.JSONField(default=list, blank=True)
    # A6 ценовые тиры билета: [{label, price_cents}] (Frühbucher/Standard/Kind).
    # Пусто = единая цена price_cents. Вместимость общая (per-tier — позже).
    tiers = models.JSONField(default=list, blank=True)
    # R1 структурированная анкета: список включённых пресет-полей (см.
    # apps/events/registration.py) — страна/ДР/экстренный контакт/питание/опыт…
    # Ответы — в Ticket.answers по ключу поля. Пусто = только свободные questions.
    registration_fields = models.JSONField(default=list, blank=True)
    # Развёрнутый «ретрит-лендинг»: опциональные блоки (для кого, идея, что
    # входит, проживание, питание, ведущие, что взять, отзывы …). Схема и
    # санитайз — apps/events/details.py. Пусто = старая короткая страница.
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["status", "starts_at"], name="event_status_starts_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == self.STATUS_PUBLISHED

    @property
    def image_url(self) -> str:
        """URL обложки (primary или первое фото); пусто, если фото нет."""
        if not self.images:
            return ""
        primary = next((i for i in self.images if i.get("is_primary")), self.images[0])
        return primary.get("url", "")

    @property
    def landing(self) -> dict:
        """Нормализованные блоки ретрит-лендинга (см. apps/events/details.py)."""
        from . import details

        return details.normalize(self.details)

    @property
    def tier_list(self) -> list:
        """Нормализованные тиры [{label, price_cents}] (см. details.normalize_tiers)."""
        from . import details

        return details.normalize_tiers(self.tiers)

    @property
    def has_tiers(self) -> bool:
        return bool(self.tier_list)

    @property
    def tiers_display(self) -> list:
        """Тиры с ценой в евро для шаблона: [{label, price_cents, price_eur}]."""
        return [{**t, "price_eur": Decimal(t["price_cents"]) / 100} for t in self.tier_list]

    def price_for_tier(self, label):
        """Цена выбранного тира (центы); без тиров / без совпадения → price_cents."""
        if label:
            for t in self.tier_list:
                if t["label"] == label:
                    return t["price_cents"]
        return self.price_cents

    @property
    def from_price_cents(self) -> int:
        """Минимальная цена (для «ab X €» на витрине): мин. тир или price_cents."""
        prices = [t["price_cents"] for t in self.tier_list]
        return min(prices) if prices else self.price_cents

    @property
    def from_price_eur(self):
        return Decimal(self.from_price_cents) / 100

    @property
    def price_eur(self):
        return Decimal(self.price_cents) / 100

    @property
    def seats_sold(self) -> int:
        agg = self.tickets.filter(status__in=Ticket.ACTIVE_STATUSES).aggregate(
            n=models.Sum("quantity")
        )
        return agg["n"] or 0

    @property
    def seats_left(self):
        """Свободные места или None при безлимите (capacity=0)."""
        if not self.capacity:
            return None
        return max(self.capacity - self.seats_sold, 0)

    @property
    def is_sold_out(self) -> bool:
        left = self.seats_left
        return left is not None and left <= 0

    @property
    def reg_fields(self) -> list:
        """Включённые пресет-поля анкеты (см. apps/events/registration.py)."""
        from . import registration

        return registration.active(self.registration_fields)

    @property
    def waitlist_pending_count(self) -> int:
        """Сколько в листе ожидания ещё не уведомлены (для кабинета)."""
        return self.waitlist.filter(notified=False).count()


class Ticket(TimestampedModel):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_ATTENDED = "attended"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_ATTENDED, "Attended"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    # Занимают места (для анти-овердрафта). Отмена освобождает.
    ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_ATTENDED)

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="tickets")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="event_tickets")
    reference_code = models.CharField(max_length=12, unique=True)  # "E-XXXXXX"
    quantity = models.PositiveSmallIntegerField(default=1)  # мест в билете
    price_cents = models.PositiveIntegerField(default=0)  # снимок цены за место
    tier_label = models.CharField(max_length=120, blank=True)  # A6: снимок тира
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    answers = models.JSONField(default=dict, blank=True)  # ответы на анкету события
    # #7: снимок выбранных Extras [{label, price_cents}] — разово на билет, сумма
    # входит в total_cents (выручку).
    extras = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)

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
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_NONE)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["event", "status"], name="ticket_event_status_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} ×{self.quantity}"

    @property
    def extras_cents(self) -> int:
        """Сумма выбранных Extras (#7), центы (разово на билет)."""
        return sum(int(e.get("price_cents", 0)) for e in (self.extras or []))

    @property
    def total_cents(self) -> int:
        return self.price_cents * self.quantity + self.extras_cents

    @property
    def total_eur(self):
        return Decimal(self.total_cents) / 100


class EventWaitlistEntry(TimestampedModel):
    """Лист ожидания на распроданное событие (R1, зеркало promotions.WaitlistEntry).

    Контакт берём с согласия для одного уведомления о наличии (DSGVO). Когда
    место освобождается (отмена билета), `notify_event_waitlist` шлёт письмо и
    ставит `notified=True` (одно уведомление на запись).
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="waitlist")
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    party_size = models.PositiveSmallIntegerField(default=1)  # сколько мест хотят
    notified = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "email"], name="uniq_event_waitlist_email")
        ]

    def __str__(self):
        return f"{self.email} → {self.event_id}"
