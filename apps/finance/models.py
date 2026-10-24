"""Light-Finance (Track D / D4, TENANT): журнал выручки.

v1 — только доходы (расходы/себестоимость — позже): записи создаются хуками
«заказ выдан» (OrderSM picked_up) и «бронь выдана» (ReservationSM fulfilled)
идемпотентно, плюс вручную в кабинете. Счета (Invoice + PDF) — D4b,
DATEV/CSV-экспорт — D4c. НЕ бухучёт: журнал — рабочая запись владельца.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class RevenueEntry(TimestampedModel):
    SOURCE_ORDER = "order"
    SOURCE_RESERVATION = "reservation"
    SOURCE_STAY = "stay"
    SOURCE_BOOKING = "booking"
    SOURCE_EVENT = "event"
    # MX-7: цифровые Вещи — их деньги в журнал не попадали ВООБЩЕ (перепись v2 §1).
    SOURCE_GIFT = "gift"
    SOURCE_PASS = "pass"
    SOURCE_MANUAL = "manual"
    SOURCE_JOB = "job"  # KA-D2: заявка/мастерская — при выставлении счёта
    SOURCES = [
        (SOURCE_ORDER, _("Order")),
        (SOURCE_RESERVATION, _("Reservation")),
        (SOURCE_STAY, _("Stay")),
        (SOURCE_BOOKING, _("Booking")),
        (SOURCE_EVENT, _("Event")),
        (SOURCE_GIFT, _("Geschenkgutschein")),
        (SOURCE_PASS, _("Mehrfachkarte")),
        (SOURCE_MANUAL, _("Manual")),
        (SOURCE_JOB, _("Auftrag")),
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
        (STATUS_DRAFT, _("Entwurf")),
        (STATUS_ISSUED, _("Gestellt")),
        (STATUS_PAID, _("Bezahlt")),
        (STATUS_CANCELLED, _("Storniert")),
    ]

    number = models.PositiveIntegerField(null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=STATUS_DRAFT)
    # I18N-7b/2: язык документа фиксируется ПРИ ВЫСТАВЛЕНИИ и живёт со счётом.
    # Иначе повторное скачивание тем же владельцем на другом языке кабинета дало
    # бы другой документ под тем же номером — это ломает GoBD-неизменяемость.
    # Пусто = язык бизнеса (Tenant.default_locale) на момент печати (легаси-счета).
    language = models.CharField(max_length=10, blank=True)
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
    # SH-23b (Р-1/Р-2): счёт юрлицу на чекауте. `due_date` — срок оплаты
    # (Zahlungsziel, по умолчанию 14 дней), `payment_terms_days` — снимок этого
    # срока на момент выпуска (настройку бизнеса потом меняют), `deal_kind`/
    # `deal_id` — из какой сделки счёт (Offene Posten и Mahnwesen ведут к ней),
    # `sent_at` — когда письмо со счётом ушло клиенту (дедуп повторной отправки).
    due_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(null=True, blank=True)
    deal_kind = models.CharField(max_length=20, blank=True)
    deal_id = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    # ERP-3 Mahnwesen v1: ступень напоминания (0=нет, 1=Zahlungserinnerung,
    # 2/3=Mahnung) + когда отправляли (дедуп «не чаще раза в день»).
    mahn_level = models.PositiveSmallIntegerField(default=0)
    mahned_at = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    # KA-H10: Leistungsdatum/-zeitraum (§ 14 Abs. 4 Nr. 6 UStG). Пусто у легаси-
    # счетов — их PDF не меняется (GoBD); при выставлении без даты — день выставления.
    service_date = models.DateField(null=True, blank=True)
    service_date_end = models.DateField(null=True, blank=True)
    # KA-H10: уже получено до счёта (Anzahlung, Wertgutschein, предоплата брони) —
    # «Offene Posten» и Mahnung ждут ОСТАТОК, а не всю сумму.
    prepaid_cents = models.PositiveIntegerField(default=0)
    # KA-12 E1.1 (GoBD): отмена выставленного счёта = отдельный документ
    # «Stornorechnung» со СВОИМ номером из того же счётчика и суммами со знаком
    # минус; оригинал не меняется. One-to-one — не больше одного сторно на счёт.
    KIND_INVOICE = "invoice"
    KIND_STORNO = "storno"
    # KA-12 B2-7b: частичная корректура выставленного счёта (Minderung, ошибка в
    # сумме) — свой номер, суммы со знаком минус, ссылка на оригинал (§ 31 UStDV).
    # В кабинете — «Gutschrift», в PDF — «Rechnungskorrektur» (решение G-1).
    KIND_CREDIT = "credit"
    # KA-12 B2-8b: счёт на предоплату (§ 14 Abs. 5 UStG) — свой номер, НЕ выручка
    # (MC-D1) и НЕ счёт сделки; итоговый счёт вычтет его (`InvoiceDeduction`, B2-8c).
    KIND_ADVANCE = "advance"
    KINDS = [
        (KIND_INVOICE, _("Rechnung")),
        (KIND_STORNO, _("Stornorechnung")),
        (KIND_CREDIT, _("Gutschrift")),
        (KIND_ADVANCE, _("Anzahlungsrechnung")),
    ]
    kind = models.CharField(max_length=10, choices=KINDS, default=KIND_INVOICE)
    cancels = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="storno_doc"
    )
    corrects = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="corrections"
    )
    # Ключ идемпотентности корректуры (повтор Minderung/клика — тот же документ).
    correction_key = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(kind="invoice", cancels__isnull=True, corrects__isnull=True)
                    | models.Q(kind="storno", cancels__isnull=False, corrects__isnull=True)
                    | models.Q(kind="credit", cancels__isnull=True, corrects__isnull=False)
                    | models.Q(kind="advance", cancels__isnull=True, corrects__isnull=True)
                ),
                name="finance_invoice_kind_links",
            ),
            # B2-8b: одна живая предоплата на сделку (T-3 вариант A; этапы — снять).
            models.UniqueConstraint(
                fields=["deal_kind", "deal_id"],
                condition=models.Q(kind="advance") & ~models.Q(status="cancelled"),
                name="finance_invoice_one_live_advance",
            ),
            models.UniqueConstraint(
                fields=["correction_key"],
                condition=~models.Q(correction_key=""),
                name="finance_invoice_correction_key_uniq",
            ),
        ]

    @property
    def is_storno(self) -> bool:
        return self.kind == self.KIND_STORNO

    @property
    def storno_doc_id_safe(self):
        """pk Stornorechnung к этому счёту или None (обратная one-to-one без исключения)."""
        doc = Invoice.objects.filter(cancels=self).only("pk").first() if self.pk else None
        return doc.pk if doc else None

    @property
    def is_credit(self) -> bool:
        return self.kind == self.KIND_CREDIT

    @property
    def is_advance(self) -> bool:
        return self.kind == self.KIND_ADVANCE

    @property
    def credited_amount(self) -> Decimal:
        """KA-12 B2-7b: сумма выставленных корректур (положительная). Списки
        аннотируют `credited` (`with_credited`) — без запроса на строку."""
        if self.kind != self.KIND_INVOICE or not self.pk:
            return Decimal("0")
        if hasattr(self, "credited"):
            return -Decimal(self.credited or 0)
        total = self.corrections.exclude(status=self.STATUS_DRAFT).aggregate(s=models.Sum("gross"))[
            "s"
        ]
        return -Decimal(total or 0)

    @property
    def corrected_gross(self) -> Decimal:
        """Брутто после корректур — столько стоит сделка по документам."""
        return Decimal(self.gross) - self.credited_amount

    @property
    def open_amount(self):
        """KA-H10: к оплате = брутто − корректуры − уже получено (не меньше 0)."""
        return max(self.corrected_gross - Decimal(self.prepaid_cents) / 100, Decimal("0"))

    def __str__(self):
        return self.number_display

    @property
    def number_display(self) -> str:
        """Номер счёта или «черновик» (I18N-7b: подпись переводится — она попадает
        и в PDF, и в кабинет; сам номер RE-00001 языконезависим)."""
        if self.number:
            return f"RE-{self.number:05d}"
        return str(_("Draft"))

    @property
    def is_editable(self) -> bool:
        return self.status == self.STATUS_DRAFT


def with_credited(qs):
    """KA-12 B2-7b: аннотировать `credited` (Σ брутто корректур, ≤ 0) одним
    запросом — `open_amount`/`corrected_gross` в списках без запроса на строку."""
    from django.db.models import DecimalField, Q, Sum, Value
    from django.db.models.functions import Coalesce

    return qs.annotate(
        credited=Coalesce(
            Sum("corrections__gross", filter=~Q(corrections__status=Invoice.STATUS_DRAFT)),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )


class InvoiceDeduction(TimestampedModel):
    """KA-12 B2-8b/c: вычет предоплаты в итоговом счёте — снимок по ставкам
    (§ 14 Abs. 5 S. 2 UStG). Строки пишет выпуск итогового счёта (B2-8c); пока
    строка есть, предоплату нельзя сторнировать. N этапов — N строк (T-3)."""

    final = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="deductions")
    advance = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="deducted_in")
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2)
    net = models.DecimalField(max_digits=10, decimal_places=2)
    vat = models.DecimalField(max_digits=10, decimal_places=2)
    gross = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["final", "advance", "vat_rate"], name="finance_deduction_uniq"
            ),
        ]

    def __str__(self):
        return f"{self.final_id} − {self.advance_id} @{self.vat_rate}"


# MT-5: журнал расходов — зеркало RevenueEntry в отдельном модуле; импорт нужен,
# чтобы Django зарегистрировал модель этого приложения.


class BankTransaction(TimestampedModel):
    """ERP-2: строка импортированной банковской выписки (CSV) для сверки.

    `import_hash` — дедуп повторного импорта того же файла/периода (уникален).
    `matched_*` — к какой сделке/счёту привязан платёж (строки, не FK: kind
    живут в разных аппах — прецедент DealLink/ExpenseEntry.ref_*). Подтверждение
    сопоставления ставит оплату сделки ШТАТНЫМ полем payment_state / InvoiceSM.
    """

    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # знак банка
    currency = models.CharField(max_length=3, default="EUR")
    purpose = models.CharField(max_length=500, blank=True)  # Verwendungszweck
    counterparty = models.CharField(max_length=200, blank=True)
    import_hash = models.CharField(max_length=32, unique=True)
    matched_kind = models.CharField(max_length=20, blank=True)  # kind | "invoice"
    matched_id = models.CharField(max_length=64, blank=True)
    matched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["matched_kind", "date"], name="banktx_matched_idx")]

    def __str__(self):
        return f"{self.date} {self.amount} {self.currency} · {self.purpose[:40]}"


from .expenses import ExpenseEntry  # noqa: E402,F401
