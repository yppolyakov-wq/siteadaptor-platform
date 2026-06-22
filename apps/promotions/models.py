"""Акции и резервирование (TENANT-схема).

Спецификация: phase1-plan-additions.md §3 + паттерны:
- state-machine.md — смена статусов только через PromotionSM/ReservationSM
- anti-oversell.md — атомарное списание остатка (см. services.py)

Прямые присваивания obj.status = ... запрещены — двигаем через FSM.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import I18nMixin, SoftDeleteMixin, TimestampedModel

_CENTS = Decimal("0.01")


class Customer(TimestampedModel):
    """Покупатель. Создаётся при первой брони, переиспользуется по email.

    CRM-минимум (Track C3): клиентов можно заводить и вручную (без брони),
    вешать теги и заметки (apps.crm) — «клиент» не привязан к товару/заказу.
    """

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)  # ["stammkunde", "vip", …]

    # CRM-lite (Track D / D1): откуда появилась запись и явное согласие на
    # маркетинг (UWG §7: рассылать можно только при opt-in; one-click отписка
    # unsubscribed — отдельный флаг и работает поверх).
    SOURCE_RESERVATION = "reservation"
    SOURCE_MANUAL = "manual"
    SOURCE_IMPORT = "import"
    SOURCE_ORDER = "order"  # Click & Collect (Track D / D2)
    CREATED_SOURCES = [
        (SOURCE_RESERVATION, "Reservation"),
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_IMPORT, "Import"),
        (SOURCE_ORDER, "Order"),
    ]
    created_source = models.CharField(
        max_length=20, choices=CREATED_SOURCES, default=SOURCE_RESERVATION
    )
    marketing_opt_in = models.BooleanField(default=False)

    # быстрая отписка от писем (one-click): токен в ссылке + флаг
    unsubscribed = models.BooleanField(default=False)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="customer_email_idx"),
        ]

    def __str__(self):
        return self.name or self.email or str(self.pk)


class Promotion(SoftDeleteMixin, I18nMixin):
    DISCOUNT = "discount"
    RESERVATION = "reservation"
    PROMO_TYPES = [(DISCOUNT, "Discount"), (RESERVATION, "Reservation")]

    title = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    description = models.JSONField(default=dict)

    product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="promotions",
    )

    promo_type = models.CharField(max_length=20, choices=PROMO_TYPES, default=RESERVATION)
    # Скидку владелец задаёт ЛИБО в %, ЛИБО новой ценой (price_override) —
    # остальное считаем (см. свойства old_price/new_price/discount_*).
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Старая (зачёркнутая) цена: если пусто — фолбэк на base_price товара.
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Картинки акции (FileRef-envelope, как у товара). Если пусто — фолбэк на фото товара.
    images = models.JSONField(default=list, blank=True)

    # null = без лимита (для discount); для reservation задаёт остаток
    available_quantity = models.IntegerField(null=True, blank=True)
    max_per_customer = models.PositiveSmallIntegerField(default=1)

    # настройки брони
    reservation_ttl_hours = models.PositiveIntegerField(default=24)
    auto_confirm = models.BooleanField(default=False)

    # витрина: показывать обратный отсчёт и зачёркивать старую цену
    show_countdown = models.BooleanField(default=False)
    strikethrough_old_price = models.BooleanField(default=True)

    # «Überraschungstüte» / анти-waste: сюрприз-пакет уценённых остатков (Track B2).
    # Поверх обычной брони — отдельная механика не нужна, только пресет + бейдж.
    is_surprise = models.BooleanField(default=False)

    # Авто-повтор акции (Track B3b): beat клонирует завершившуюся со сдвигом окна
    # на интервал. Наследник один (recurrence уходит к нему, у родителя гасится),
    # поэтому цепочка не ветвится.
    NO_RECUR, DAILY, WEEKLY = "", "daily", "weekly"
    RECURRENCE = [(NO_RECUR, "—"), (DAILY, "Täglich"), (WEEKLY, "Wöchentlich")]
    recurrence = models.CharField(max_length=10, choices=RECURRENCE, default=NO_RECUR, blank=True)

    # S6: группа/направление акции («Fastfood», «Fertiggerichte»…) — для отдельных
    # подразделов витрины (/aktionen/?gruppe=…) и целей меню (promo_group).
    # Свободный текст: набор групп определяет владелец, фильтр — по точному значению.
    group = models.CharField(max_length=50, blank=True, default="", db_index=True)

    status = models.CharField(max_length=20, default="draft", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    # аналитика: счётчик просмотров публичной страницы акции
    views = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # планировщик статусов (scheduled→active, active→ended) ходит по ним
            models.Index(fields=["status", "starts_at"], name="promo_status_starts_idx"),
            models.Index(fields=["status", "ends_at"], name="promo_status_ends_idx"),
        ]

    def __str__(self):
        return self.get_i18n("title") or str(self.pk)

    @property
    def title_text(self) -> str:
        return self.get_i18n("title")

    @property
    def description_text(self) -> str:
        return self.get_i18n("description")

    # --- цена и скидка --------------------------------------------------

    @staticmethod
    def _dec(value):
        return None if value is None else Decimal(str(value))

    @property
    def currency(self) -> str:
        return self.product.currency if self.product_id and self.product else "EUR"

    @property
    def old_price(self):
        """Старая цена: compare_at_price, иначе base_price товара, иначе None."""
        if self.compare_at_price is not None:
            return self._dec(self.compare_at_price)
        if self.product_id and self.product:
            return self._dec(self.product.base_price)
        return None

    @property
    def new_price(self):
        """Новая цена: price_override, иначе old_price со скидкой %, иначе old_price."""
        old = self.old_price
        if self.price_override is not None:
            return self._dec(self.price_override)
        if self.discount_percent and old is not None:
            factor = (Decimal(100) - Decimal(int(self.discount_percent))) / Decimal(100)
            return (old * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return old

    @property
    def has_discount(self) -> bool:
        old, new = self.old_price, self.new_price
        return old is not None and new is not None and new < old

    @property
    def discount_amount(self):
        if not self.has_discount:
            return None
        return (self.old_price - self.new_price).quantize(_CENTS)

    @property
    def discount_percent_display(self):
        """Целый процент скидки для бейджа (−XX %)."""
        if self.discount_percent:
            return int(self.discount_percent)
        if self.has_discount and self.old_price > 0:
            pct = (Decimal(1) - (self.new_price / self.old_price)) * Decimal(100)
            return int(pct.to_integral_value(rounding=ROUND_HALF_UP))
        return None

    # --- витрина: медиа и таймер ---------------------------------------

    @property
    def primary_image(self):
        """Главное фото акции; фолбэк на главное фото привязанного товара."""
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        if imgs:
            return imgs[0]
        if self.product_id and self.product:
            return self.product.primary_image
        return None

    @property
    def seconds_left(self):
        """Секунд до ends_at (для обратного отсчёта). None если конца нет."""
        if not self.ends_at:
            return None
        delta = (self.ends_at - timezone.now()).total_seconds()
        return int(delta) if delta > 0 else 0

    @property
    def is_sold_out(self) -> bool:
        """Лимитированная акция распродана (остаток 0)."""
        return self.available_quantity is not None and self.available_quantity <= 0


class Reservation(TimestampedModel):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="reservations")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="reservations")

    # короткий человекочитаемый код для выдачи (R-XXXXXX)
    reference_code = models.CharField(max_length=12, unique=True)
    quantity = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=20, default="pending", db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    note = models.TextField(blank=True)

    # канал привлечения (?ch= в ссылке/QR): instagram, flyer, schaufenster…
    source_channel = models.CharField(max_length=50, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="resv_status_expires_idx"),
            models.Index(fields=["promotion", "status"], name="resv_promo_status_idx"),
        ]

    def __str__(self):
        return self.reference_code


class WaitlistEntry(TimestampedModel):
    """Запись в лист ожидания, когда акция распродана.

    Контакт берём с согласия для одного уведомления о наличии (DSGVO).
    """

    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name="waitlist")
    name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    notified = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            # один email в листе ожидания на акцию
            models.UniqueConstraint(fields=["promotion", "email"], name="uniq_waitlist_promo_email")
        ]

    def __str__(self):
        return f"{self.email} → {self.promotion_id}"
