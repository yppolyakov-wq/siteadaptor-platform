"""Каталог: Category и Product (TENANT-схема).

Спецификация: phase1-implementation-guide.md, Часть 2 + дополнения:
- soft-delete (доп. 1.3) — patterns/soft-delete.md
- FileRef-envelope для images (доп. 2.2)
- i18n JSONField + metadata на runtime-моделях
"""

from django.db import models

from apps.core.models import I18nMixin, SoftDeleteMixin, TimestampedModel


class Category(SoftDeleteMixin, I18nMixin):
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
    )
    name = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    slug = models.SlugField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["sort_order", "slug"]
        constraints = [
            # slug уникален среди живых записей (soft-delete не должен мешать
            # переиспользовать slug; см. patterns/soft-delete.md).
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_category_slug_alive",
            )
        ]

    def __str__(self):
        return self.get_i18n("name") or self.slug


class Product(SoftDeleteMixin, I18nMixin):
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    name = models.JSONField(default=dict)
    description = models.JSONField(default=dict)

    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )

    # FileRef-envelope (доп. 2.2): список dict'ов
    # [{"id","url","alt":{de,en},"mime_type","size","is_primary","sort_order"}]
    images = models.JSONField(default=list, blank=True)

    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")

    # PAngV (R2): Grundpreis (€/kg|l). unit — единица контента, content_amount —
    # количество (250 г, 0.75 л). Stück/пусто → без Grundpreis (несчётные товары).
    UNIT_CHOICES = [
        ("", "Stück / —"),
        ("g", "Gramm"),
        ("kg", "Kilogramm"),
        ("ml", "Milliliter"),
        ("l", "Liter"),
    ]
    unit = models.CharField(max_length=4, blank=True, choices=UNIT_CHOICES)
    content_amount = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    stock_quantity = models.IntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    # Lebensmittel-Kennzeichnung (LMIV, R4): аллергены (коды из apps.catalog.food),
    # происхождение и список ингредиентов. Заполняется для еды; на витрине
    # показывается только при наличии.
    allergens = models.JSONField(default=list, blank=True)
    origin = models.CharField(max_length=120, blank=True)
    ingredients = models.TextField(blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"], name="product_active_idx"),
            models.Index(fields=["category"], name="product_category_idx"),
            models.Index(fields=["sku"], name="product_sku_idx"),
        ]

    def __str__(self):
        return self.get_i18n("name") or self.sku or str(self.pk)

    @property
    def name_text(self) -> str:
        return self.get_i18n("name")

    @property
    def description_text(self) -> str:
        return self.get_i18n("description")

    @property
    def primary_image(self) -> dict | None:
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        return imgs[0] if imgs else None

    @property
    def active_variants(self):
        return self.variants.filter(is_active=True)

    @property
    def has_variants(self) -> bool:
        return self.active_variants.exists()

    @property
    def in_stock(self) -> bool:
        """Доступен ли к заказу (R3). Untracked (null) → всегда True. С вариантами
        — есть ли хоть один доступный вариант."""
        if self.has_variants:
            return any(v.in_stock for v in self.active_variants)
        return self.stock_quantity is None or self.stock_quantity > 0

    @property
    def price_from(self):
        """Минимальная цена среди активных вариантов («ab X €») или base_price."""
        prices = [v.price_value for v in self.active_variants]
        return min(prices) if prices else self.base_price

    @property
    def grundpreis(self):
        """PAngV (value, ref) или None — для товара без вариантов."""
        from .pricing import grundpreis

        return grundpreis(self.base_price, self.unit, self.content_amount)

    @property
    def allergen_labels(self) -> list[str]:
        """Подписи аллергенов (DE) для витрины — из кодов self.allergens."""
        from .food import allergen_labels

        return allergen_labels(self.allergens)


class ProductVariant(TimestampedModel):
    """Вариант товара (R1): чай 100/250 г, размер одежды, фасовка.

    Один уровень (label) — мульти-измерения (цвет×размер) в v1 не делаем. Цена
    пустая → берётся Product.base_price. stock_quantity — на варианте (atomic-
    списание при заказе — R3). label уникален в пределах товара.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    label = models.CharField(max_length=100)  # «100 g», «M», «6er-Pack»
    sku = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # PAngV (R2): контент варианта для Grundpreis (чай 100 г vs 250 г); пусто →
    # берётся Product.content_amount. Единица (unit) — на товаре.
    content_amount = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    stock_quantity = models.IntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "label"], name="variant_product_label_uniq"),
        ]

    def __str__(self):
        return f"{self.product} · {self.label}"

    @property
    def price_value(self):
        """Цена варианта: своя или фолбэк на base_price товара."""
        return self.price if self.price is not None else self.product.base_price

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity is None or self.stock_quantity > 0

    @property
    def grundpreis(self):
        """PAngV (value, ref) или None: своя content_amount или товара; unit товара."""
        from .pricing import grundpreis

        content = (
            self.content_amount if self.content_amount is not None else self.product.content_amount
        )
        return grundpreis(self.price_value, self.product.unit, content)
