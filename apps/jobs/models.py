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
from django.utils.translation import gettext_lazy as _

from apps.core.models import I18nMixin, TimestampedModel
from apps.promotions.models import Customer


class Job(I18nMixin, TimestampedModel):
    STATUS_NEW = "new"  # Anfrage eingegangen
    STATUS_QUOTED = "quoted"  # Angebot gesendet
    STATUS_ACCEPTED = "accepted"  # beauftragt / angenommen
    STATUS_DONE = "done"  # erledigt
    STATUS_INVOICED = "invoiced"  # abgerechnet
    STATUS_DECLINED = "declined"  # abgelehnt
    STATUS_CANCELLED = "cancelled"
    STATUSES = [
        (STATUS_NEW, _("Anfrage")),
        (STATUS_QUOTED, _("Angebot gesendet")),
        (STATUS_ACCEPTED, _("Beauftragt")),
        (STATUS_DONE, _("Erledigt")),
        (STATUS_INVOICED, _("Abgerechnet")),
        (STATUS_DECLINED, _("Abgelehnt")),
        (STATUS_CANCELLED, _("Storniert")),
    ]

    # PROTECT, как у Reservation/Order: клиента с заявками не удалить молча
    # (DSGVO-стирание анонимизирует Customer, не удаляя записи).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="jobs")
    reference_code = models.CharField(max_length=12, unique=True)  # "A-XXXXXX"
    # DC-4 (ТЗ владельца 2026-08-25): внешний номер сделки — номер кассы, портала
    # или бумажной книги; вводится вручную и ищется поиском сделок. Машинные
    # ключи импорта (external_ref у брони номера) этим полем НЕ подменяются.
    external_code = models.CharField(max_length=50, blank=True, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # I18N-12: перевод ПОКАЗА демо-заявок в кабинете (реальные заявки клиентов
    # остаются как есть — оверлей заполняет только демо-сидер).
    title_i18n = models.JSONField(default=dict, blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    site_address = models.TextField(blank=True)  # адрес работ (может ≠ адрес клиента)
    site_plz = models.CharField(max_length=10, blank=True)  # A7: PLZ объекта (Einzugsgebiet-чек)
    # A9 Werkstatt: автомобиль клиента — свободный текст марки/модели («VW Golf 1.6 TDI»).
    vehicle = models.CharField(max_length=120, blank=True)
    # A9 Werkstatt: структурные данные авто — Kennzeichen + HSN/TSN (Schlüsselnummern
    # из Zulassungsbescheinigung). Помогают мастерской точно определить запчасти.
    vehicle_plate = models.CharField(max_length=15, blank=True)  # Kennzeichen «M-AB 1234»
    vehicle_hsn = models.CharField(max_length=4, blank=True)  # Herstellerschlüsselnummer
    vehicle_tsn = models.CharField(max_length=3, blank=True)  # Typschlüsselnummer
    # AF-1: событийная заявка (Catering/Partyservice) — поля видны на форме только
    # при site_config["anfrage"] (per-tenant, presence-minimal); event_type хранит
    # значение из настроенного владельцем списка (валидация fail-closed во вьюхе).
    event_date = models.DateField(null=True, blank=True)  # Wunschdatum
    guest_count = models.PositiveIntegerField(null=True, blank=True)  # Anzahl Personen
    event_type = models.CharField(max_length=100, blank=True)  # Art der Veranstaltung
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_NEW)
    source_channel = models.CharField(max_length=50, blank=True)
    # Публичная Angebot-страница: клиент принимает/отклоняет смету онлайн (F3).
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    valid_until = models.DateField(null=True, blank=True)  # Angebot gültig bis
    # I18N-7b/2: язык сметы (Angebot) — выбирается владельцем и хранится, чтобы
    # клиент повторно скачал ТОТ ЖЕ документ. Пусто = язык бизнеса.
    language = models.CharField(max_length=10, blank=True)
    # A9: следующий TÜV/Service — дата, когда напомнить клиенту (Werkstatt-ретеншн).
    # Beat шлёт письмо за SERVICE_REMINDER_LEAD_DAYS до даты; sent_at — дедуп (одно
    # напоминание на дату; смена даты в кабинете сбрасывает sent_at → новое напоминание).
    service_due_date = models.DateField(null=True, blank=True)
    service_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # Снимок сумм сметы (брутто-расчёт из JobLine; §19 Kleinunternehmer → vat 0).
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("19.00"))
    net = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gross = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    # B1.6: Gutschein/промокод при принятии Angebot — Wertgutschein юридически
    # Zahlungsmittel: gross/счёт НЕ меняем, скидка уменьшает «zu zahlen».
    # Списание — spend_voucher при accept; отмена возвращает (хук JobSM).
    voucher_code = models.CharField(max_length=40, blank=True)
    discount_cents = models.PositiveIntegerField(default=0)

    quoted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    # Связанный счёт (apps.finance.Invoice в той же схеме) — без жёсткого FK.
    invoice_id = models.UUIDField(null=True, blank=True)
    # G11: остаток за расходники (Teile из каталога) списан — один раз, при
    # переходе в done (erledigt). Гард идемпотентности (как у заказов R3).
    stock_committed = models.BooleanField(default=False)

    # A7c: онлайн-Anzahlung за смету (Stripe Connect, зеркало P2.5b booking).
    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PAID = "paid"
    PAYMENT_REFUNDED = "refunded"
    PAYMENT_STATES = [
        (PAYMENT_UNPAID, _("Unpaid")),
        (PAYMENT_PAID, _("Paid")),
        (PAYMENT_REFUNDED, _("Refunded")),
    ]
    deposit_cents = models.PositiveIntegerField(default=0)  # 0 = без Anzahlung
    payment_state = models.CharField(max_length=10, choices=PAYMENT_STATES, default=PAYMENT_UNPAID)
    stripe_payment_intent = models.CharField(max_length=64, blank=True)

    # A7d: выездной Termin (apps.booking) для заявки — мастер видит запись из сметы.
    # SET_NULL: удаление брони не трогает заявку.
    booking = models.ForeignKey(
        "booking.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="job_status_created_idx"),
        ]

    def __str__(self):
        return f"{self.reference_code} {self.title}"

    def title_localized(self, locale: str | None = None) -> str:
        """I18N-12: показ темы заявки на локали (демо-записи кабинета)."""
        return self.get_overlay("title", "title_i18n", locale)

    def description_localized(self, locale: str | None = None) -> str:
        """I18N-12: показ описания заявки на локали."""
        return self.get_overlay("description", "description_i18n", locale)

    @property
    def discount_eur(self):
        """B1.6: скидка Gutschein в евро (Decimal)."""
        from decimal import Decimal

        return Decimal(self.discount_cents) / 100

    @property
    def payable_gross(self):
        """B1.6: «zu zahlen» = брутто − Gutschein (счёт остаётся на gross)."""
        return max(self.gross - self.discount_eur, 0)

    def plan_calc(self):
        """ERP-6: плановая калькуляция сметы (ТОЛЬКО кабинет).

        {cost, margin, pct, partial} по строкам с известной ставкой
        (cost = Σ qty × cost_rate; margin = netto − cost; partial = есть
        строки без ставки, т.е. итог занижает себестоимость). None, если
        ставка не задана ни у одной строки — блок не показывается."""
        from decimal import Decimal

        lines = list(self.lines.all())
        priced = [ln for ln in lines if ln.cost_rate is not None]
        if not priced:
            return None
        cost = sum((ln.qty * ln.cost_rate for ln in priced), Decimal("0"))
        margin = self.net - cost
        pct = (margin / self.net * 100) if self.net else None
        return {
            "cost": cost,
            "margin": margin,
            "pct": pct,
            "partial": len(priced) < len(lines),
        }


class JobLine(I18nMixin, TimestampedModel):
    """Позиция сметы (Angebot): текст, количество, цена за единицу нетто.

    qty — Decimal (A7a): дробные часы/единицы Handwerker (3,5 Std). Суммы сметы и
    Rechnung считаются одним finance.compute_totals (qty как Decimal) — совпадают."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)  # порядок отображения
    text = models.CharField(max_length=300)
    text_i18n = models.JSONField(default=dict, blank=True)  # I18N-12 (демо-сметы)
    qty = models.DecimalField(max_digits=7, decimal_places=2, default=1)  # дробное (A7a)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # нетто за ед.
    # ERP-6: ПЛАНОВАЯ себестоимость за единицу строки (интерн, в публичную смету
    # и PDF не попадает): для работ — ставка €/Std., для Teile — снимок EK детали
    # на момент составления (философия снимков ERP-1). None = ставка неизвестна.
    cost_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

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

    def text_localized(self, locale: str | None = None) -> str:
        """I18N-12: показ строки сметы на локали (демо)."""
        return self.get_overlay("text", "text_i18n", locale)

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.qty


class JobPhoto(TimestampedModel):
    """Фото к заявке (A7b): клиент прикладывает на /anfrage/, мастер видит их в
    кабинете при подготовке сметы (повреждение/объём работ)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="job_photos/%Y/%m/")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Photo {self.pk} for {self.job_id}"
