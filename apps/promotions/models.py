"""Акции и резервирование (TENANT-схема).

Спецификация: phase1-plan-additions.md §3 + паттерны:
- state-machine.md — смена статусов только через PromotionSM/ReservationSM
- anti-oversell.md — атомарное списание остатка (см. services.py)

Прямые присваивания obj.status = ... запрещены — двигаем через FSM.
"""

from django.db import models

from apps.core.models import I18nMixin, SoftDeleteMixin, TimestampedModel


class Customer(TimestampedModel):
    """Покупатель. Создаётся при первой брони, переиспользуется по email."""

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)

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
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # null = без лимита (для discount); для reservation задаёт остаток
    available_quantity = models.IntegerField(null=True, blank=True)
    max_per_customer = models.PositiveSmallIntegerField(default=1)

    # настройки брони
    reservation_ttl_hours = models.PositiveIntegerField(default=24)
    auto_confirm = models.BooleanField(default=False)

    status = models.CharField(max_length=20, default="draft", db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

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

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="resv_status_expires_idx"),
            models.Index(fields=["promotion", "status"], name="resv_promo_status_idx"),
        ]

    def __str__(self):
        return self.reference_code
