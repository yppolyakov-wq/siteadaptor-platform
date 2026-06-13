"""Click & Collect / заказы-lite (Track D / D2, TENANT).

Клиент собирает товары витрины (/sortiment/) в корзину-сессию и оформляет
самовывоз; владелец ведёт заказ по FSM (state_machine.OrderSM). v1 сознательно
без жёсткого остатка (предзаказ) и без онлайн-оплаты (payment_state вручную,
оплата в магазине) — решения ТЗ docs/track-d-business-os-spec.md §D2.

UUID-pk и смена статусов только FSM-хуками — задел на будущий SHARED-граф
заказов (маркетплейс/дропшип пристёгиваются событиями без переделки).
"""

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Order(TimestampedModel):
    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_READY = "ready"
    STATUS_PICKED_UP = "picked_up"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_NEW, "New"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_READY, "Ready for pickup"),
        (STATUS_PICKED_UP, "Picked up"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]

    # PROTECT, как у Reservation: клиента с заказами нельзя удалить молча
    # (DSGVO-стирание анонимизирует Customer, не удаляя записи).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    reference_code = models.CharField(max_length=12, unique=True)  # "O-XXXXXX"
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_NEW)
    # Желаемое время самовывоза (свободный выбор клиента); слоты/календарь — D3.
    pickup_slot = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    source_channel = models.CharField(max_length=50, blank=True)
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_UNPAID)
    stripe_payment_intent = models.CharField(max_length=200, blank=True)  # P2.5c: для refund
    # Снимок суммы на момент заказа — цены каталога могут меняться.
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="order_status_created_idx"),
        ]

    def __str__(self):
        return self.reference_code


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="order_items"
    )
    qty = models.PositiveIntegerField(default=1)
    # Снимки цены/названия: заказ показывает то, что видел клиент.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    title_snapshot = models.CharField(max_length=200)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.qty}× {self.title_snapshot}"

    @property
    def line_total(self):
        return self.unit_price * self.qty
