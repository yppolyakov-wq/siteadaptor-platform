"""U-D3: append-only склад-леджер движений остатка.

Решение D1 (unified-sellable-entity-decisions): леджер append-only РЯДОМ со
счётчиком `Product.stock_quantity` — счётчик остаётся истиной, леджер даёт
историю движений и реконсиляцию (не заменяет атомарные декременты движков).

`record_movement` идемпотентен по (source, source_ref, kind) для событийных
движений (заказ/заявка) — образец `finance.record_revenue`; ручные приёмки/
корректировки — без дедупа.
"""

from django.db import models

from apps.core.models import TimestampedModel


class StockLocation(TimestampedModel):
    """Склад-2 E2 (Мультисклад): локация/Standort. Ленивая активация — пока локаций
    нет, весь мультисклад-UI скрыт и поведение прежнее. NULL-движения леджера читаются
    как «основной склад» (default), т.е. история до E2 валидна без бэкфилла."""

    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)  # основной (NULL-леджер = он)
    note = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return self.name


class StockMovement(TimestampedModel):
    """Одно движение остатка товара/варианта. delta знаковый: +приход / −расход."""

    KIND_RECEIPT = "receipt"  # Wareneingang (ручная приёмка +N)
    KIND_SALE = "sale"  # списание при заказе Click&Collect
    KIND_ADJUSTMENT = "adjustment"  # ручная корректировка ±N / стартовый баланс
    KIND_RETURN = "return"  # возврат остатка при отмене/возврате заказа
    KIND_STOCKTAKE = "stocktake"  # инвентаризация (корректировка до факта)
    KIND_COMMIT = "commit"  # расход материалов при выполнении заявки (Handwerker)
    # Склад-2 E2 (Мультисклад): переброс между локациями — пара движений Σ=0,
    # счётчик (итого) НЕ двигается, меняется только локационная разбивка.
    KIND_TRANSFER_OUT = "transfer_out"
    KIND_TRANSFER_IN = "transfer_in"
    KINDS = [
        (KIND_RECEIPT, "Wareneingang"),
        (KIND_SALE, "Verkauf"),
        (KIND_ADJUSTMENT, "Korrektur"),
        (KIND_RETURN, "Rückgabe"),
        (KIND_STOCKTAKE, "Inventur"),
        (KIND_COMMIT, "Materialverbrauch"),
        (KIND_TRANSFER_OUT, "Umlagerung (ab)"),
        (KIND_TRANSFER_IN, "Umlagerung (zu)"),
    ]

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="stock_movements"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    kind = models.CharField(max_length=20, choices=KINDS)
    delta = models.IntegerField(help_text="Signed: +Zugang / −Abgang")
    # E2: локация движения; NULL = основной склад (вся история до E2 валидна без
    # бэкфилла). Баланс per-location выводится из леджера (счётчик остаётся ИТОГО).
    location = models.ForeignKey(
        "inventory.StockLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )
    # Откуда движение: order/job/manual/stocktake (+ source_ref — id документа/
    # позиции, ключ идемпотентности как у finance.RevenueEntry).
    source = models.CharField(max_length=20, blank=True)
    source_ref = models.CharField(max_length=64, blank=True)
    note = models.CharField(max_length=200, blank=True)
    actor = models.CharField(max_length=150, blank=True)  # username (для ручных)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "created_at"], name="stockmove_product_idx"),
            models.Index(fields=["source", "source_ref"], name="stockmove_source_idx"),
        ]
        constraints = [
            # Событийные движения идемпотентны по (source, source_ref, kind);
            # ручные (source_ref="") — вне ограничения (условный UNIQUE).
            models.UniqueConstraint(
                fields=["source", "source_ref", "kind"],
                condition=~models.Q(source_ref=""),
                name="stockmove_source_ref_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.delta:+d}"


class Lot(TimestampedModel):
    """Склад-2 E1 (Chargen/MHD): партия товара/варианта с остатком и сроком годности.

    Разбивка ПОВЕРХ счётчика (Вариант A, план sklad-2 §3): `Σ Lot.qty_remaining`
    сходится со `stock_quantity` сущности (реконсиляция, как леджер↔счётчик). Партии
    существуют только когда владелец включил `site_config["lots_enabled"]` и оприходовал
    по партиям; товар без партий → поведение остатка как раньше (чистый счётчик).

    FEFO (First-Expired-First-Out): при расходе гасим партии по возрастанию `mhd`
    (ближайший срок первым; партии без даты — последними). Порядок Meta это отражает.
    """

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="lots")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="lots",
    )
    lot_code = models.CharField(max_length=64, blank=True)  # Chargennummer (опц.)
    mhd = models.DateField(null=True, blank=True)  # Mindesthaltbarkeitsdatum / срок годности
    qty_received = models.PositiveIntegerField(default=0)  # приход партии
    qty_remaining = models.IntegerField(default=0)  # текущий остаток партии (гасится FEFO)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        # FEFO-порядок: сперва с датой по возрастанию, партии без MHD — в хвост
        # (F("mhd").asc(nulls_last=True) в запросах расхода; ordering — для UI-списка).
        ordering = ["mhd", "created_at"]
        indexes = [
            models.Index(fields=["product", "mhd"], name="lot_product_mhd_idx"),
            models.Index(fields=["variant", "mhd"], name="lot_variant_mhd_idx"),
        ]

    def __str__(self):
        code = self.lot_code or "—"
        return f"Charge {code} · {self.qty_remaining}/{self.qty_received}"

    @property
    def is_expired(self) -> bool:
        """Партия просрочена (MHD в прошлом). Без даты — никогда."""
        from django.utils import timezone

        return self.mhd is not None and self.mhd < timezone.localdate()

    def days_left(self):
        """Дней до MHD (может быть отрицательным); None без даты."""
        from django.utils import timezone

        return (self.mhd - timezone.localdate()).days if self.mhd is not None else None


class Lieferant(TimestampedModel):
    """Склад-2 E3 (Закупки/M12): поставщик. Аддитивно; приёмка по Bestellung двигает
    счётчик/леджер существующим складским путём (D1 цел)."""

    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    customer_number = models.CharField(max_length=64, blank=True)  # наш № у поставщика
    default_lead_days = models.PositiveIntegerField(null=True, blank=True)  # срок поставки
    note = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Bestellung(TimestampedModel):
    """Склад-2 E3: закупочный заказ (Purchase Order). Планирование — счётчик НЕ трогает
    до приёмки; приёмка строк идёт существующим складским путём."""

    STATUS_DRAFT = "draft"  # Entwurf — собираем позиции
    STATUS_ORDERED = "ordered"  # bestellt — отправлен поставщику
    STATUS_RECEIVED = "received"  # empfangen — принят полностью
    STATUS_CANCELLED = "cancelled"  # storniert
    STATUSES = [
        (STATUS_DRAFT, "Entwurf"),
        (STATUS_ORDERED, "Bestellt"),
        (STATUS_RECEIVED, "Empfangen"),
        (STATUS_CANCELLED, "Storniert"),
    ]

    supplier = models.ForeignKey(
        Lieferant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bestellungen",
    )
    reference = models.CharField(max_length=12, unique=True)  # "BE-XXXXXX"
    status = models.CharField(max_length=12, choices=STATUSES, default=STATUS_DRAFT)
    note = models.CharField(max_length=300, blank=True)
    ordered_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    actor = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="po_status_idx")]

    def __str__(self):
        return self.reference

    @property
    def total_cost(self):
        """Σ строк (Menge × EK) — для отображения. Decimal."""
        from decimal import Decimal

        return sum((p.line_total for p in self.positions.all()), Decimal("0"))

    @property
    def is_fully_received(self) -> bool:
        lines = list(self.positions.all())
        return bool(lines) and all(p.is_fully_received for p in lines)


class BestellPosition(TimestampedModel):
    """Склад-2 E3: строка закупочного заказа. Сущность = товар без вариантов | вариант
    (как в остальном складе). `qty_received` — сколько принято (частичные приёмки)."""

    bestellung = models.ForeignKey(Bestellung, on_delete=models.CASCADE, related_name="positions")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="po_positions"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="po_positions",
    )
    qty = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # EK-снимок
    qty_received = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        label = self.variant.label if self.variant_id else ""
        return f"{self.product} {label} × {self.qty}".strip()

    @property
    def line_total(self):
        return self.unit_cost * self.qty

    @property
    def is_fully_received(self) -> bool:
        return self.qty_received >= self.qty

    @property
    def qty_open(self) -> int:
        """Ещё не принято по строке (для частичной приёмки)."""
        return max(0, self.qty - self.qty_received)
