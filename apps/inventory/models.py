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


class StockMovement(TimestampedModel):
    """Одно движение остатка товара/варианта. delta знаковый: +приход / −расход."""

    KIND_RECEIPT = "receipt"  # Wareneingang (ручная приёмка +N)
    KIND_SALE = "sale"  # списание при заказе Click&Collect
    KIND_ADJUSTMENT = "adjustment"  # ручная корректировка ±N / стартовый баланс
    KIND_RETURN = "return"  # возврат остатка при отмене/возврате заказа
    KIND_STOCKTAKE = "stocktake"  # инвентаризация (корректировка до факта)
    KIND_COMMIT = "commit"  # расход материалов при выполнении заявки (Handwerker)
    KINDS = [
        (KIND_RECEIPT, "Wareneingang"),
        (KIND_SALE, "Verkauf"),
        (KIND_ADJUSTMENT, "Korrektur"),
        (KIND_RETURN, "Rückgabe"),
        (KIND_STOCKTAKE, "Inventur"),
        (KIND_COMMIT, "Materialverbrauch"),
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
