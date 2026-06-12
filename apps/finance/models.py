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
    SOURCE_MANUAL = "manual"
    SOURCES = [
        (SOURCE_ORDER, "Order"),
        (SOURCE_RESERVATION, "Reservation"),
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
