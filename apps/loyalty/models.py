"""Лояльность и ваучеры (TENANT-схема).

Выделено из `apps.promotions` (2026-06-22, рефактор перегруженного ядра): штампы и
промокоды живут отдельным приложением. `Customer` остаётся общей идентичностью в
`promotions` — модели лояльности ссылаются на неё кросс-приложенчески.

Важно: `db_table` сохранены прежними (`promotions_*`) — перенос моделей выполнен
через `SeparateDatabaseAndState` (только состояние Django, без DDL): таблицы
физически созданы историческими миграциями promotions и не пересоздаются, поэтому
существующие данные тенантов не затрагиваются, а свежие схемы (CI/новый бизнес)
получают те же таблицы. Имя оставлено `promotions_*`, чтобы не делать RENAME на
всех схемах.
"""

import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import TimestampedModel


class Voucher(TimestampedModel):
    """Ваучер/промокод: код, который владелец раздаёт и гасит при выдаче.

    max_uses=0 — безлимит. Гашение атомарно (см. promotions.services.redeem_voucher).
    """

    code = models.CharField(max_length=12, unique=True)
    label = models.CharField(max_length=120)  # что даёт ваучер ("−10 %", "Gratis Kaffee")
    max_uses = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # D1: ваучер, выданный конкретному клиенту (опц.) — для карточки 360° в CRM.
    # SET_NULL: код переживает удаление клиента (остаётся валидным как артефакт
    # бизнеса, не PII). null = обычный раздаточный код без привязки.
    customer = models.ForeignKey(
        "promotions.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vouchers",
    )
    # Промокод на онлайн-заказе (A4): структурная скидка. Применяется на
    # чекауте Click&Collect, если задана (percent ИЛИ cents). Оба пустые =
    # обычный «ручной» ваучер (label-метка, гасится сотрудником, как раньше).
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    discount_cents = models.PositiveIntegerField(null=True, blank=True)
    min_order_cents = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        db_table = "promotions_voucher"

    def __str__(self):
        return self.code

    @property
    def uses_left(self):
        """Сколько осталось гашений (None — безлимит)."""
        if not self.max_uses:
            return None
        return max(0, self.max_uses - self.used_count)

    @property
    def is_redeemable(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return not (self.max_uses and self.used_count >= self.max_uses)

    @property
    def has_order_discount(self) -> bool:
        """Несёт ли ваучер скидку для онлайн-заказа (А4-промокод)."""
        return bool(self.discount_percent) or bool(self.discount_cents)

    def discount_for(self, subtotal_cents: int) -> int:
        """Скидка в центах для суммы заказа (0, если не применима/не достигнут мин).

        percent → %·subtotal; cents → фикс. Капается суммой заказа (не уходит в
        минус). Сам факт погашения/лимиты — отдельно (services.redeem_voucher).
        """
        if not self.has_order_discount or not self.is_redeemable:
            return 0
        if subtotal_cents < (self.min_order_cents or 0):
            return 0
        if self.discount_percent:
            value = subtotal_cents * int(self.discount_percent) // 100
        else:
            value = int(self.discount_cents or 0)
        return max(0, min(value, subtotal_cents))


class GiftVoucher(TimestampedModel):
    """Подарочный сертификат (G1): покупается онлайн, после оплаты выпускается
    `Voucher` (фикс-сумма, 1 использование), который гасится как обычный промокод
    (H4a — поле промокода в брони). Здесь — только покупка/выпуск/доставка кода."""

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_STATES = [(PAYMENT_PENDING, "Pending"), (PAYMENT_PAID, "Paid")]

    buyer_name = models.CharField(max_length=120)
    buyer_email = models.EmailField()
    recipient_name = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=300, blank=True)
    amount_cents = models.PositiveIntegerField()
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_PENDING)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)
    # Выпущенный код (после оплаты). SET_NULL: код-артефакт переживает удаление записи.
    voucher = models.ForeignKey(
        "loyalty.Voucher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gift_purchase",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Gutschein {self.amount_eur} € · {self.buyer_email}"

    @property
    def amount_eur(self) -> float:
        return self.amount_cents / 100


class LoyaltyProgram(TimestampedModel):
    """Программа лояльности (штампы): N штампов → награда."""

    label = models.CharField(max_length=120)  # "Kaffee-Karte"
    stamps_required = models.PositiveSmallIntegerField(default=10)
    reward_label = models.CharField(max_length=120)  # "Gratis Kaffee"
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "promotions_loyaltyprogram"

    def __str__(self):
        return self.label


class LoyaltyCard(TimestampedModel):
    """Карта клиента в программе. token — для QR/скана при начислении."""

    program = models.ForeignKey(LoyaltyProgram, on_delete=models.CASCADE, related_name="cards")
    customer = models.ForeignKey(
        "promotions.Customer", on_delete=models.CASCADE, related_name="loyalty_cards"
    )
    stamps = models.PositiveIntegerField(default=0)
    rewards_earned = models.PositiveIntegerField(default=0)
    token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "promotions_loyaltycard"
        constraints = [
            models.UniqueConstraint(
                fields=["program", "customer"], name="uniq_loyaltycard_program_customer"
            )
        ]

    def __str__(self):
        return (
            f"{self.customer_id} · {self.program_id}: {self.stamps}/{self.program.stamps_required}"
        )


class StampEvent(TimestampedModel):
    """Лог начисления штампа (аудит + анти-дабл по кулдауну)."""

    card = models.ForeignKey(LoyaltyCard, on_delete=models.CASCADE, related_name="events")

    class Meta:
        ordering = ["-created_at"]
        db_table = "promotions_stampevent"
