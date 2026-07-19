"""Click & Collect / заказы-lite (Track D / D2, TENANT).

Клиент собирает товары витрины (/sortiment/) в корзину-сессию и оформляет
самовывоз; владелец ведёт заказ по FSM (state_machine.OrderSM). v1 сознательно
без жёсткого остатка (предзаказ) и без онлайн-оплаты (payment_state вручную,
оплата в магазине) — решения ТЗ docs/track-d-business-os-spec.md §D2.

UUID-pk и смена статусов только FSM-хуками — задел на будущий SHARED-граф
заказов (маркетплейс/дропшип пристёгиваются событиями без переделки).
"""

import uuid

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Order(TimestampedModel):
    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_READY = "ready"
    STATUS_PICKED_UP = "picked_up"
    STATUS_SHIPPED = "shipped"  # G4: versandt (для доставки)
    STATUS_CANCELLED = "cancelled"
    STATUS_RETURNED = "returned"  # A2c: возврат после выдачи/отправки (Widerruf)
    STATUSES = [
        (STATUS_NEW, "New"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_READY, "Ready"),
        (STATUS_PICKED_UP, "Picked up"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_RETURNED, "Returned"),
    ]
    # G4: способ получения. pickup — самовывоз (как раньше); delivery — доставка.
    FULFILLMENT_PICKUP = "pickup"
    FULFILLMENT_DELIVERY = "delivery"
    FULFILLMENTS = [(FULFILLMENT_PICKUP, "Pickup"), (FULFILLMENT_DELIVERY, "Delivery")]
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]
    # E-7: СПОСОБ оплаты (платёжный микс DACH) — ортогонален payment_state.
    # "" = легаси-заказы до введения поля. Реестр расширяем (paypal/klarna/sepa —
    # нативные провайдеры позже, через Stripe payment_method_types уже сейчас).
    METHOD_ON_SITE = "on_site"  # Barzahlung bei Abholung/Lieferung
    METHOD_STRIPE = "stripe"  # Online-Zahlung (Stripe Checkout, P2.5c)
    METHOD_VORKASSE = "vorkasse"  # Überweisung/Vorkasse (реквизиты в письме)
    PAYMENT_METHODS = [
        (METHOD_ON_SITE, "Barzahlung bei Abholung"),
        (METHOD_STRIPE, "Online-Zahlung"),
        (METHOD_VORKASSE, "Vorkasse (Überweisung)"),
    ]

    # PROTECT, как у Reservation: клиента с заказами нельзя удалить молча
    # (DSGVO-стирание анонимизирует Customer, не удаляя записи).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    reference_code = models.CharField(max_length=12, unique=True)  # "O-XXXXXX"
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_NEW)
    # Желаемое время самовывоза (свободный выбор клиента); слоты/календарь — D3.
    pickup_slot = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    # T2a: номер стола для QR-заказа со стола (Dine-in). Пусто = самовывоз/доставка.
    table_number = models.CharField(max_length=20, blank=True)
    # Точка самовывоза (снимок, если у бизнеса их несколько). Пусто = единственный пункт.
    pickup_location = models.CharField(max_length=200, blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_UNPAID)
    # E-7: способ оплаты (см. PAYMENT_METHODS); "" = легаси до введения поля.
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHODS, blank=True, default=""
    )
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # P2.5c: для refund
    # Снимок суммы на момент заказа — цены каталога могут меняться.
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    # G4: доставка. fulfillment=pickup по умолчанию (обратная совместимость).
    fulfillment = models.CharField(max_length=10, choices=FULFILLMENTS, default=FULFILLMENT_PICKUP)
    shipping_address = models.TextField(blank=True)
    shipping_cents = models.PositiveIntegerField(default=0)  # снимок стоимости доставки
    # Промокод (A4): применённый код + скидка в центах (снимок, уже учтён в total).
    voucher_code = models.CharField(max_length=12, blank=True)
    # CM-6.4: post-purchase просьба об отзыве — дедуп «одно письмо на заказ».
    post_purchase_sent_at = models.DateTimeField(null=True, blank=True)
    # B2.1: напоминание о незавершённой Stripe-оплате — дедуп «одно на заказ».
    payment_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)
    tracking_code = models.CharField(max_length=100, blank=True)  # номер DHL/Hermes
    shipped_at = models.DateTimeField(null=True, blank=True)

    # Швы под маркетплейс/dropshipping (M11→M14/M15, master-plan §7) — ПАССИВНЫЕ,
    # логики наследования пока нет. parent_order — дочерний заказ в цепочке (в этой
    # же схеме; кросс-тенантную привязку добавим с модулем); supplier_tenant_schema —
    # схема бизнеса-поставщика, исполняющего заказ (кросс-тенантно, как у aggregator).
    parent_order = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="child_orders"
    )
    supplier_tenant_schema = models.CharField(max_length=63, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="order_status_created_idx"),
        ]

    def __str__(self):
        return self.reference_code

    @property
    def is_delivery(self) -> bool:
        return self.fulfillment == self.FULFILLMENT_DELIVERY

    @property
    def shipping_eur(self):
        from decimal import Decimal

        return Decimal(self.shipping_cents) / 100

    @property
    def discount_eur(self):
        from decimal import Decimal

        return Decimal(self.discount_cents) / 100


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # null = комбо-позиция (товара нет, есть combo). Иначе обычный товар.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Комбо-набор (A4): позиция-набор; состав — снимок в modifiers.
    combo = models.ForeignKey(
        "catalog.Combo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Вариант (R1): null = товар без вариантов. label — снимок (как title/price).
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    variant_label = models.CharField(max_length=100, blank=True)
    qty = models.PositiveIntegerField(default=1)
    # Снимки цены/названия: заказ показывает то, что видел клиент.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    title_snapshot = models.CharField(max_length=200)
    # Снимок выбранных модификаторов/Extras (A4b): [{"label","delta"}]. Надбавка
    # уже включена в unit_price; список — для отображения в заказе/письмах.
    modifiers = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.qty}× {self.title_snapshot}"

    @property
    def line_total(self):
        return self.unit_price * self.qty

    @property
    def modifiers_label(self) -> str:
        """«Pommes, Käse» — выбранные модификаторы для отображения (A4b)."""
        return ", ".join(m.get("label", "") for m in (self.modifiers or []))


class Offer(TimestampedModel):
    """LS-3 «Sofort-Angebot»: персональное предложение из чата (inbox).

    Живёт ОТДЕЛЬНО от заказа: непринятое предложение не засоряет канбан.
    Принятие конвертирует его в обычный Order (offers.accept_offer) — оплата/
    статусы/письма дальше идут существующими путями orders. jobs (смета
    Handwerker, свой цикл net/VAT/Rechnung) сознательно не обобщён — план
    docs/ls3-sofort-angebot-plan-2026-07-19.md §1.
    """

    STATUS_OPEN = "open"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED = "cancelled"  # владелец отозвал
    STATUSES = [
        (STATUS_OPEN, "Open"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Тред-источник (SET_NULL: удаление треда не трогает историю предложений).
    conversation = models.ForeignKey(
        "inbox.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offers",
    )
    # Снимок адресата на момент отправки; у анонимного треда может быть пусто —
    # тогда name/email спрашивает публичная страница при принятии.
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="offers"
    )
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    note = models.TextField(blank=True)  # личное сообщение на странице предложения
    valid_until = models.DateField(null=True, blank=True)  # пусто = бессрочно
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_OPEN)
    # Заказ, созданный при принятии (идемпотентность повторного POST).
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="offers"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Angebot {str(self.token)[:8]}"

    @property
    def total(self):
        from decimal import Decimal

        return sum((line.line_total for line in self.lines.all()), Decimal("0"))

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return bool(self.valid_until and self.valid_until < timezone.localdate())

    @property
    def is_open(self) -> bool:
        return self.status == self.STATUS_OPEN and not self.is_expired


class OfferLine(TimestampedModel):
    """Позиция предложения — снимок (цена/название заморожены при отправке).

    kind/ref_id — провенанс из пикера (product/service/stay/event/combo или
    ''=свободная строка); НЕ FK: источник может исчезнуть, предложение — нет.
    Цена БРУТТО как OrderItem.unit_price (PAngV) — без net/VAT-математики jobs.
    """

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=10, blank=True, default="")
    # str, не FK/int: pk источника бывает UUID (Product) — как Conversation.ref_id.
    ref_id = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=200)
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return f"{self.qty}× {self.title}"

    @property
    def line_total(self):
        return self.unit_price * self.qty
