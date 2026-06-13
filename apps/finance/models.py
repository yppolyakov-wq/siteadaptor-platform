"""Light-Finance (Track D / D4, TENANT): журнал выручки.

v1 — только доходы (расходы/себестоимость — позже): записи создаются хуками
«заказ выдан» (OrderSM picked_up) и «бронь выдана» (ReservationSM fulfilled)
идемпотентно, плюс вручную в кабинете. Счета (Invoice + PDF) — D4b,
DATEV/CSV-экспорт — D4c. НЕ бухучёт: журнал — рабочая запись владельца.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class RevenueEntry(TimestampedModel):
    SOURCE_ORDER = "order"
    SOURCE_RESERVATION = "reservation"
    SOURCE_STAY = "stay"
    SOURCE_MANUAL = "manual"
    SOURCES = [
        (SOURCE_ORDER, "Order"),
        (SOURCE_RESERVATION, "Reservation"),
        (SOURCE_STAY, "Stay"),
        (SOURCE_MANUAL, "Manual"),
    ]
    # Ставки НДС DE: 19 стандарт, 7 еда/печать, 0 — §19 Kleinunternehmer и пр.
    VAT_RATES = [Decimal("19.00"), Decimal("7.00"), Decimal("0.00")]

    source = models.CharField(max_length=20, choices=SOURCES, default=SOURCE_MANUAL)
    # id источника (Order/Reservation) — идемпотентность хуков: один документ
    # даёт ровно одну запись выручки, сколько бы раз хук ни сработал.
    source_ref = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # брутто
    currency = models.CharField(max_length=3, default="EUR")
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("19.00"))
    date = models.DateField(default=timezone.localdate)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="revenue_entries"
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref"],
                condition=~models.Q(source_ref=""),
                name="revenue_source_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="revenue_date_idx"),
        ]

    def __str__(self):
        return f"{self.date} {self.amount} {self.currency} ({self.get_source_display()})"


class InvoiceCounter(models.Model):
    """Последовательная нумерация счетов per-tenant (требование DE, GoBD).

    Одна строка на схему; номер выдаётся под select_for_update в момент
    issue (черновики без номера → в нумерации нет дыр от удалённых драфтов).
    """

    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"InvoiceCounter({self.last_number})"


class Invoice(TimestampedModel):
    """Rechnung (D4b): снимок позиций + суммы; issued — иммутабелен.

    Сторно (cancelled) сохраняет номер — дыр в нумерации нет, документ
    остаётся в журнале. Полный бухучёт сознательно не делаем (ТЗ D4).
    """

    STATUS_DRAFT = "draft"
    STATUS_ISSUED = "issued"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_DRAFT, "Entwurf"),
        (STATUS_ISSUED, "Gestellt"),
        (STATUS_PAID, "Bezahlt"),
        (STATUS_CANCELLED, "Storniert"),
    ]

    number = models.PositiveIntegerField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_DRAFT)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    # Получатель снимком (Pflichtangabe §14 UStG; CRM-клиент может меняться).
    recipient = models.TextField(blank=True)
    # Позиции снимком: [{"text": str, "qty": int, "unit_price": str(Decimal)}].
    lines = models.JSONField(default=list)
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("19.00"))
    net = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gross = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    issued_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number_display

    @property
    def number_display(self) -> str:
        return f"RE-{self.number:05d}" if self.number else "Entwurf"

    @property
    def is_editable(self) -> bool:
        return self.status == self.STATUS_DRAFT
