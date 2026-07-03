"""Событие/ретрит с платным билетом и ростером участников (A6, TENANT).

Event — мероприятие на дату с вместимостью и ценой за место; Ticket — билет
клиента (несколько мест + анкета). Анти-овердрафт мест — атомарно под блокировкой
строки Event (services.book_ticket, зеркало anti-oversell). Оплата — Stripe
Connect (как P2.5/E4, A6c), выручка — в finance. Переиспуем Customer/notifications/
реестр модулей. Покрывает A6: Konzert/Workshop/Yoga/Retreat/Tour с билетами.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import I18nMixin, TimestampedModel
from apps.promotions.models import Customer

# R8: дефолтный текст отказа от ответственности (если организатор не задал свой).
DEFAULT_WAIVER_TEXT = (
    "Ich nehme freiwillig und auf eigene Verantwortung teil. Mir ist bewusst, dass "
    "Yoga, Meditation und körperliche Übungen Risiken bergen. Ich bestätige, "
    "gesundheitlich zur Teilnahme in der Lage zu sein, und habe relevante "
    "Einschränkungen mitgeteilt. Der Veranstalter haftet nicht für Schäden, die "
    "nicht auf grobe Fahrlässigkeit oder Vorsatz zurückzuführen sind."
)


class Event(I18nMixin, TimestampedModel):
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
    # i18n (двуязычная витрина): переводы заголовка/описания {"de":..,"en":..}.
    # Пусто = одноязычно (фолбэк на плоские title/description). Витрина читает
    # title_text/description_text; кабинет/админка правят плоские поля.
    title_i18n = models.JSONField(default=dict, blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    location = models.CharField(max_length=200, blank=True)
    # RT2: онлайн/Zoom-событие. is_online → витрина показывает «Online», скрывает карту/
    # адрес; online_url (ссылка на Zoom/Meet/видео) показывается участнику ПОСЛЕ брони
    # (на странице подтверждения + в письме), не публично — чтобы не утекал доступ.
    is_online = models.BooleanField(default=False)
    online_url = models.URLField(blank=True)
    # R2 таксономия для каталога/фильтров/агрегатора (пресеты — apps/events/taxonomy.py).
    city = models.CharField(max_length=100, blank=True)  # для фильтра «Stadt» + гео-агрегатор
    # R6: координаты места (для карты на витрине; пусто = фолбэк на гео тенанта).
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    category = models.CharField(max_length=30, blank=True)  # направление/тема (yoga/meditation…)
    level = models.CharField(max_length=20, blank=True)  # требуемый уровень подготовки
    language = models.CharField(max_length=10, blank=True)  # язык проведения (контент-тег)
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
    # R4: онлайн-предоплата в % от суммы (0 = оплата полностью; 1..99 = депозит,
    # остаток на месте/по счёту; 100 = полная). Дорогой ретрит — бронь депозитом.
    deposit_percent = models.PositiveSmallIntegerField(default=0)
    # R8: требовать подпись отказа от ответственности (Waiver) при брони + текст
    # условий (пусто = дефолтный шаблон). Снимок текста — в TicketWaiver.
    waiver_required = models.BooleanField(default=False)
    waiver_text = models.TextField(blank=True)
    # R12: политика отмены билета (зеркало stays.RatePlan). flexible — бесплатная
    # самоотмена гостем до `free_cancel_days` дней до начала (возврат онлайн-оплаты
    # через Stripe Connect); non_refundable — отмена без возврата.
    CANCEL_FLEXIBLE = "flexible"
    CANCEL_NONREF = "non_refundable"
    CANCELLATIONS = [
        (CANCEL_FLEXIBLE, "Kostenlose Stornierung"),
        (CANCEL_NONREF, "Nicht erstattbar"),
    ]
    cancellation = models.CharField(max_length=20, choices=CANCELLATIONS, default=CANCEL_FLEXIBLE)
    # Бесплатная отмена до N дней до начала (для flexible; 0 = до дня начала).
    free_cancel_days = models.PositiveSmallIntegerField(default=0)
    # R10: рассрочка (Ratenzahlung) — гость платит билет частями (Stripe мандат).
    INSTALLMENT_UNTIL_EVENT = "until_event"
    INSTALLMENT_FIXED = "fixed"
    INSTALLMENT_MODES = [
        (INSTALLMENT_UNTIL_EVENT, "Bis zur Veranstaltung"),  # депозит + равные до старта
        (INSTALLMENT_FIXED, "Feste Monatsraten"),  # фикс. число помесячно
    ]
    allow_installments = models.BooleanField(default=False)
    installment_mode = models.CharField(
        max_length=20, choices=INSTALLMENT_MODES, default=INSTALLMENT_UNTIL_EVENT
    )
    installment_count = models.PositiveSmallIntegerField(default=3)  # всего долей (вкл. первую)
    installment_min_cents = models.PositiveIntegerField(default=0)  # мин. сумма к рассрочке
    installment_lead_days = models.PositiveSmallIntegerField(default=14)  # послед. доля до старта
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
    # R5 проживание: многодневный ретрит может предлагать выбор номера через
    # архетип «Отель» (apps.stays). offers_accommodation включает шаг выбора;
    # accommodation_units — курируемый набор типов номеров на даты ретрита
    # [starts_at; ends_at). Бронь номера привязывается к билету (Ticket.stay_booking),
    # оплачивается вместе с билетом (StayBooking.payment_state=none), инвентарь —
    # реальный анти-овербукинг stays.
    offers_accommodation = models.BooleanField(default=False)
    accommodation_units = models.ManyToManyField(
        "stays.StayUnit", blank=True, related_name="retreat_events"
    )
    # R3: ведущие/преподаватели (структурная сущность) — курируемый набор. Дополняет
    # свободные hosts в details-лендинге; даёт фильтр каталога и страницы учителей.
    teachers = models.ManyToManyField("Teacher", blank=True, related_name="events")
    # RT3: recurring-серия — общий id у всех повторов (еженедельно/раз в 2 недели/
    # ежемесячно). Пусто = одиночное событие. Группирует копии для управления.
    series_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["status", "starts_at"], name="event_status_starts_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def title_text(self) -> str:
        """i18n-заголовок для витрины: перевод текущей локали, фолбэк на плоский title."""
        return self.get_i18n("title_i18n") or self.title

    @property
    def description_text(self) -> str:
        """i18n-описание для витрины: перевод текущей локали, фолбэк на плоское описание."""
        return self.get_i18n("description_i18n") or self.description

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
    def landing_testimonials(self) -> list:
        """R13: отзывы лендинга для шаблона — с фото и звёздами рейтинга.

        К каждому отзыву добавляет `stars` (★…☆ по rating 1..5, 0 = без оценки)."""
        out = []
        for t in self.landing.get("testimonials", []):
            try:
                rating = max(0, min(5, int(t.get("rating") or 0)))
            except (TypeError, ValueError):
                rating = 0
            out.append({**t, "rating": rating, "stars": "★" * rating + "☆" * (5 - rating)})
        return out

    @property
    def tier_list(self) -> list:
        """Нормализованные тиры [{label, price_cents}] (см. details.normalize_tiers)."""
        from . import details

        return details.normalize_tiers(self.tiers)

    @property
    def has_tiers(self) -> bool:
        return bool(self.tier_list)

    def tier_sold_map(self) -> dict:
        """{tier_label: проданных мест} активных билетов (R11, один запрос)."""
        rows = (
            self.tickets.filter(status__in=Ticket.ACTIVE_STATUSES)
            .values("tier_label")
            .annotate(n=models.Sum("quantity"))
        )
        return {r["tier_label"]: r["n"] or 0 for r in rows}

    def tier_seats_left(self, label, sold_map=None):
        """Свободные места тира или None при безлимите (capacity тира = 0, R11)."""
        tier = next((t for t in self.tier_list if t["label"] == label), None)
        cap = (tier or {}).get("capacity") or 0
        if not cap:
            return None
        sold = (sold_map if sold_map is not None else self.tier_sold_map()).get(label, 0)
        return max(cap - sold, 0)

    @property
    def tiers_display(self) -> list:
        """Тиры для шаблона: [{label, price_cents, price_eur, capacity, seats_left,
        sold_out, is_default}]. seats_left=None при безлимите тира; is_default —
        первый доступный тир (для предвыбора в форме, R11)."""
        sold_map = self.tier_sold_map() if any(t.get("capacity") for t in self.tier_list) else {}
        out = []
        default_set = False
        for t in self.tier_list:
            left = self.tier_seats_left(t["label"], sold_map)
            sold_out = left is not None and left <= 0
            is_default = not sold_out and not default_set
            if is_default:
                default_set = True
            out.append(
                {
                    **t,
                    "price_eur": Decimal(t["price_cents"]) / 100,
                    "seats_left": left,
                    "sold_out": sold_out,
                    "is_default": is_default,
                }
            )
        return out

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
        if left is not None and left <= 0:
            return True
        # R11: все ценовые тиры с лимитом распроданы (а безлимитных тиров нет) →
        # купить нечего, показываем лист ожидания.
        tiers = self.tier_list
        if tiers and all(t.get("capacity") for t in tiers):
            sold_map = self.tier_sold_map()
            return all((self.tier_seats_left(t["label"], sold_map) or 0) <= 0 for t in tiers)
        return False

    @property
    def reg_fields(self) -> list:
        """Включённые пресет-поля анкеты (см. apps/events/registration.py)."""
        from . import registration

        return registration.active(self.registration_fields)

    @property
    def category_label(self) -> str:
        from . import taxonomy

        return taxonomy.category_label(self.category)

    @property
    def level_label(self) -> str:
        from . import taxonomy

        return taxonomy.level_label(self.level)

    @property
    def language_label(self) -> str:
        from . import taxonomy

        return taxonomy.language_label(self.language)

    @property
    def duration_kind(self) -> str:
        from . import taxonomy

        return taxonomy.duration_kind(self.starts_at, self.ends_at)

    @property
    def duration_label(self) -> str:
        from . import taxonomy

        return taxonomy.duration_label(self.duration_kind)

    @property
    def cancellation_label(self) -> str:
        return self.get_cancellation_display()

    @property
    def is_refundable(self) -> bool:
        """R12: тариф допускает возврат при своевременной отмене (flexible)."""
        return self.cancellation == self.CANCEL_FLEXIBLE

    @property
    def effective_waiver_text(self) -> str:
        """Текст waiver: заданный организатором, иначе дефолтный шаблон (R8)."""
        return (self.waiver_text or "").strip() or DEFAULT_WAIVER_TEXT

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
    # R5: привязанная бронь проживания (выбранный тип номера на даты ретрита).
    # SET_NULL — бронь можно удалить; accommodation_cents — снимок цены номера
    # (входит в total_cents, оплачивается вместе с билетом).
    stay_booking = models.ForeignKey(
        "stays.StayBooking",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_tickets",
    )
    accommodation_cents = models.PositiveIntegerField(default=0)
    # R4: применённый подарочный/промо-код (Voucher) — снимок кода и скидки (центы).
    # Скидка вычитается из суммы к оплате (payable_cents); снимок переживает ваучер.
    voucher_code = models.CharField(max_length=12, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)
    # R4: снимок онлайн-депозита (центы) при частичной оплате (Event.deposit_percent);
    # 0 = оплата полностью. Остаток (payable − deposit) — на месте/по счёту.
    deposit_cents = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    # R9: drip-письма — по одному на билет (idempotent + БД-дедуп Notification).
    reminder_sent_at = models.DateTimeField(null=True, blank=True)  # за N дней до события
    post_event_sent_at = models.DateTimeField(null=True, blank=True)  # после события
    # RT1: Check-in по QR — момент входа гостя (статус → attended). Пусто = не пришёл.
    checked_in_at = models.DateTimeField(null=True, blank=True)

    PAYMENT_NONE = "none"
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_DEPOSIT = "deposit"  # R4: депозит оплачен, остаток на месте
    PAYMENT_INSTALLMENT = "installment"  # R10: рассрочка активна (часть долей оплачена)
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_NONE, "None"),
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_DEPOSIT, "Deposit paid"),
        (PAYMENT_INSTALLMENT, "Installment plan"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]
    payment_state = models.CharField(max_length=12, choices=PAYMENT_STATES, default=PAYMENT_NONE)
    # B2.3: напоминание о незавершённой оплате билета — дедуп «одно на билет».
    payment_reminder_sent_at = models.DateTimeField(null=True, blank=True)
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
        return self.price_cents * self.quantity + self.extras_cents + self.accommodation_cents

    @property
    def payable_cents(self) -> int:
        """К оплате итого (R4): брутто минус скидка ваучера (не уходит в минус)."""
        return max(0, self.total_cents - self.discount_cents)

    @property
    def amount_due_now_cents(self) -> int:
        """Сумма онлайн-оплаты сейчас (R4): депозит, если задан, иначе вся payable."""
        return self.deposit_cents if self.deposit_cents else self.payable_cents

    @property
    def balance_cents(self) -> int:
        """Остаток после онлайн-депозита (на месте); 0 при полной оплате."""
        return max(0, self.payable_cents - self.deposit_cents) if self.deposit_cents else 0

    @property
    def total_eur(self):
        return Decimal(self.total_cents) / 100

    @property
    def payable_eur(self):
        return Decimal(self.payable_cents) / 100

    @property
    def discount_eur(self):
        return Decimal(self.discount_cents) / 100

    @property
    def amount_due_now_eur(self):
        return Decimal(self.amount_due_now_cents) / 100

    @property
    def balance_eur(self):
        return Decimal(self.balance_cents) / 100


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


class Teacher(TimestampedModel):
    """R3: ведущий/преподаватель ретрита (фото, био, соцсети). Связь M2M с Event;
    даёт фильтр каталога по преподавателю и страницы учителей на витрине."""

    name = models.CharField(max_length=120)
    title = models.CharField(max_length=160, blank=True)  # «Yogalehrerin & Coach»
    bio = models.TextField(blank=True)
    photo_url = models.URLField(max_length=500, blank=True)
    website = models.URLField(max_length=500, blank=True)
    instagram = models.CharField(max_length=120, blank=True)  # handle или URL
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def instagram_url(self) -> str:
        """Полный URL Instagram из handle или готовой ссылки (пусто = нет)."""
        ig = (self.instagram or "").strip()
        if not ig:
            return ""
        if ig.startswith("http"):
            return ig
        return f"https://instagram.com/{ig.lstrip('@')}"

    def upcoming_events(self):
        """Опубликованные будущие события этого преподавателя (для страницы)."""
        from django.utils import timezone

        return self.events.filter(
            status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
        ).order_by("starts_at")


class TicketWaiver(TimestampedModel):
    """R8: подписанный отказ от ответственности + Gesundheits-Selbstauskunft к билету.

    Простая e-подпись (eIDAS «einfache», как stays.GuestRegistration): печатное
    Ф.И.О. + отметка времени и IP. `waiver_text_snapshot` — снимок условий на момент
    подписи (юридический след, переживает правку шаблона события). Не авто-чистится
    (срок исковой давности), в отличие от BMG-Meldeschein."""

    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="waiver")
    waiver_text_snapshot = models.TextField()
    health_confirmed = models.BooleanField(default=False)  # «здоров/раскрыл противопоказания»
    signed_name = models.CharField(max_length=200)
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Waiver {self.ticket.reference_code}"


class InstallmentPlan(TimestampedModel):
    """R10: план рассрочки билета — гость платит частями (Stripe мандат).

    Первая доля списывается при оформлении (on-session, сохраняет PaymentMethod),
    остальные — off-session по графику (beat). Деньги идут бизнесу (Connect, как
    остальные платежи событий). status: active → completed (всё оплачено) |
    failed (исчерпаны попытки списания) | cancelled (билет отменён → стоп списаний).
    """

    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="installment_plan")
    total_cents = models.PositiveIntegerField(default=0)  # сумма к рассрочке (снимок)
    count = models.PositiveSmallIntegerField(default=0)  # число долей
    status = models.CharField(max_length=12, choices=STATUSES, default=STATUS_ACTIVE)
    # Сохранённый мандат для off-session списаний (заполняется в R10b).
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_payment_method_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Plan {self.ticket.reference_code} ×{self.count}"

    @property
    def paid_cents(self) -> int:
        return sum(
            c.amount_cents for c in self.charges.all() if c.status == InstallmentCharge.STATUS_PAID
        )

    @property
    def remaining_cents(self) -> int:
        return max(0, self.total_cents - self.paid_cents)

    @property
    def paid_count(self) -> int:
        return sum(1 for c in self.charges.all() if c.status == InstallmentCharge.STATUS_PAID)


class InstallmentCharge(TimestampedModel):
    """R10: одна доля графика рассрочки (идемпотентное off-session списание).

    sequence 1 = первая доля (on-session при оформлении), далее — по `due_date`
    через beat. attempts/last_error — для ретраев и эскалации (без авто-отмены)."""

    STATUS_SCHEDULED = "scheduled"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_REFUNDED = "refunded"
    STATUSES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    plan = models.ForeignKey(InstallmentPlan, on_delete=models.CASCADE, related_name="charges")
    sequence = models.PositiveSmallIntegerField()  # 1..count
    due_date = models.DateField()
    amount_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUSES, default=STATUS_SCHEDULED)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "sequence"], name="uniq_plan_sequence")
        ]

    def __str__(self):
        return f"Charge {self.plan_id} #{self.sequence} ({self.status})"


class BlogPost(TimestampedModel):
    """RT4: запись блога/новостей бизнеса (TENANT). Лёгкий контент-тип: новости
    ретрита, статьи, анонсы. Публичный список /blog/ + детальная /blog/<slug>/."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    excerpt = models.CharField(max_length=300, blank=True)  # короткий анонс (в списке)
    body = models.TextField(blank=True)  # текст (line-breaks → абзацы на витрине)
    cover = models.JSONField(default=dict, blank=True)  # FileRef-конверт обложки
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["is_published", "published_at"], name="blogpost_pub_idx")]

    def __str__(self):
        return self.title

    @property
    def cover_url(self) -> str:
        return self.cover.get("url", "") if isinstance(self.cover, dict) else ""
