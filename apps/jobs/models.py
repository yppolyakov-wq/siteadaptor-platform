"""Aufträge & Angebote / смета для Handwerker (G6, TENANT).

Цикл ремесленника (выездной сервис) принципиально иной, чем розница/бронь:
**Anfrage → Angebot (Kostenvoranschlag) → Auftrag → Rechnung.** Одна модель Job
ведёт заявку через весь жизненный цикл (как Order/StayBooking); смета = позиции
JobLine. Переиспользуем Customer (CRM), PDF + Invoice из apps.finance,
notifications, реестр модулей. Без онлайн-оплаты (Handwerker платят по счёту).
"""

import uuid
from decimal import Decimal

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Job(TimestampedModel):
    STATUS_NEW = "new"  # Anfrage eingegangen
    STATUS_QUOTED = "quoted"  # Angebot gesendet
    STATUS_ACCEPTED = "accepted"  # beauftragt / angenommen
    STATUS_DONE = "done"  # erledigt
    STATUS_INVOICED = "invoiced"  # abgerechnet
    STATUS_DECLINED = "declined"  # abgelehnt
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_NEW, "Anfrage"),
        (STATUS_QUOTED, "Angebot gesendet"),
        (STATUS_ACCEPTED, "Beauftragt"),
        (STATUS_DONE, "Erledigt"),
        (STATUS_INVOICED, "Abgerechnet"),
        (STATUS_DECLINED, "Abgelehnt"),
        (STATUS_CANCELLED, "Storniert"),
    ]

    # PROTECT, как у Reservation/Order: клиента с заявками не удалить молча
    # (DSGVO-стирание анонимизирует Customer, не удаляя записи).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="jobs")
    reference_code = models.CharField(max_length=12, unique=True)  # "A-XXXXXX"
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    site_address = models.TextField(blank=True)  # адрес работ (может ≠ адрес клиента)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_NEW)
    source_channel = models.CharField(max_length=50, blank=True)
    # Публичная Angebot-страница: клиент принимает/отклоняет смету онлайн (F3).
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    valid_until = models.DateField(null=True, blank=True)  # Angebot gültig bis

    # Снимок сумм сметы (брутто-расчёт из JobLine; §19 Kleinunternehmer → vat 0).
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("19.00"))
    net = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gross = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    quoted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    # Связанный счёт (apps.finance.Invoice в той же схеме) — без жёсткого FK.
    invoice_id = models.UUIDField(null=True, blank=True)
    # G11: остаток за расходники (Teile из каталога) списан — один раз, при
    # переходе в done (erledigt). Гард идемпотентности (как у заказов R3).
    stock_committed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="job_status_created_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.title}"


class JobLine(TimestampedModel):
    """Позиция сметы (Angebot): текст, количество, цена за единицу нетто.

    qty — Decimal (A7a): дробные часы/единицы Handwerker (3,5 Std). Суммы сметы и
    Rechnung считаются одним finance.compute_totals (qty как Decimal) — совпадают."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)  # порядок отображения
    text = models.CharField(max_length=300)
    qty = models.DecimalField(max_digits=7, decimal_places=2, default=1)  # дробное (A7a)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # нетто за ед.

    # G11: расходник (Teile) из каталога — null = свободная строка (Arbeit/работа).
    # SET_NULL: удаление товара не трогает смету (text/unit_price — снимок). При
    # erledigt списывается остаток только по строкам с привязкой и учётом склада.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_lines",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_lines",
    )

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return f"{self.text} ×{self.qty}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.qty
