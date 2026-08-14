"""Расходы (MT-5) — зеркало журнала выручки; кусок давно запланированного M13.

До сих пор `apps/finance` вёл только доходы («v1 — только доходы» в его
докстринге). Тур это обнажил: без закупки (отели, транспорт, пермиты) нельзя
сказать, сколько заработала поездка. Модель сделана ЗЕРКАЛОМ `RevenueEntry` —
та же идемпотентность по `(source, source_ref)`, та же форма записи, — поэтому
маржа считается одинаково для любого архетипа, а не только для туров.

Валюта: EUR обязателен (по нему считаем), оригинал (INR/NPR) хранится рядом
справочно — решение владельца §0b.6.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel


class ExpenseEntry(TimestampedModel):
    SOURCE_SUPPLIER = "supplier_booking"  # оплата поставщику по книге логистики
    SOURCE_PURCHASE = "purchase"  # закупка товара (склад)
    SOURCE_MANUAL = "manual"
    SOURCES = [
        (SOURCE_SUPPLIER, _("Anbieter-Buchung")),
        (SOURCE_PURCHASE, _("Einkauf")),
        (SOURCE_MANUAL, _("Manuell")),
    ]

    CATEGORY_ACCOMMODATION = "accommodation"
    CATEGORY_TRANSPORT = "transport"
    CATEGORY_FEES = "fees"
    CATEGORY_STAFF = "staff"
    CATEGORY_GOODS = "goods"
    CATEGORY_OTHER = "other"
    CATEGORIES = [
        (CATEGORY_ACCOMMODATION, _("Unterkunft")),
        (CATEGORY_TRANSPORT, _("Transport")),
        (CATEGORY_FEES, _("Gebühren / Permits")),
        (CATEGORY_STAFF, _("Personal vor Ort")),
        (CATEGORY_GOODS, _("Wareneinkauf")),
        (CATEGORY_OTHER, _("Sonstiges")),
    ]

    source = models.CharField(max_length=20, choices=SOURCES, default=SOURCE_MANUAL)
    # Идемпотентность: один документ = одна запись расхода, сколько бы раз хук
    # ни сработал (тот же приём, что у RevenueEntry).
    source_ref = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # брутто, EUR
    currency = models.CharField(max_length=3, default="EUR")
    # Оригинальная валюта расхода (INR/NPR) — справочно, в расчёты не идёт.
    original_currency = models.CharField(max_length=3, blank=True)
    original_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    category = models.CharField(max_length=20, choices=CATEGORIES, default=CATEGORY_OTHER)
    date = models.DateField(default=timezone.localdate)
    # Привязка к поездке — чтобы посчитать маржу конкретного заезда.
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expense_entries",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref"],
                condition=~models.Q(source_ref=""),
                name="expense_source_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="expense_date_idx"),
            models.Index(fields=["event"], name="expense_event_idx"),
        ]

    def __str__(self):
        return f"{self.date} −{self.amount} {self.currency} ({self.get_category_display()})"
