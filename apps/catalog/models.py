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
    gtin = models.CharField(max_length=14, blank=True)  # A1: EAN/GTIN (штрихкод) для фидов
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

    # Маркетинговый бейдж на витрине (T1): «Tagesgericht», «Neu», «Beliebt».
    # Пусто = без бейджа. is_featured (популярные на главной) — отдельно.
    BADGE_CHOICES = [
        ("", "—"),
        ("tagesgericht", "Tagesgericht"),
        ("neu", "Neu"),
        ("beliebt", "Beliebt"),
        ("empfehlung", "Empfehlung"),
    ]
    badge = models.CharField(max_length=20, blank=True, choices=BADGE_CHOICES)

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
    def badge_label(self) -> str:
        """Человекочитаемый бейдж («Tagesgericht») или '' если не задан."""
        return dict(self.BADGE_CHOICES).get(self.badge, "") if self.badge else ""

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
    def modifier_groups_active(self):
        """Активные группы модификаторов (Gastro-Extras, A4) с активными опциями."""
        return self.modifier_groups.filter(is_active=True)

    @property
    def has_modifiers(self) -> bool:
        return any(g.active_options for g in self.modifier_groups_active)

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
    gtin = models.CharField(max_length=14, blank=True)  # A1: EAN/GTIN варианта
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


class ModifierGroup(TimestampedModel):
    """Группа модификаторов блюда (A4 Gastro): «Größe», «Beilage», «Extras».

    Привязана к товару (блюду). min_select/max_select задают правило выбора:
    min>=1 — обязательная; max==1 — одиночный выбор (radio); max>1 — до N
    (checkbox); max==0 — без верхнего предела. Валидируется на витрине при заказе
    (A4b). Цена опций — надбавка к цене позиции.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="modifier_groups")
    name = models.CharField(max_length=100)  # «Größe», «Extras»
    min_select = models.PositiveIntegerField(default=0)
    max_select = models.PositiveIntegerField(default=1)  # 0 = без предела
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.product} · {self.name}"

    @property
    def active_options(self):
        return list(self.options.filter(is_active=True))

    @property
    def is_required(self) -> bool:
        return self.min_select >= 1

    @property
    def is_multi(self) -> bool:
        """Множественный выбор (checkbox) против одиночного (radio)."""
        return self.max_select != 1


class ModifierOption(TimestampedModel):
    """Опция группы модификаторов: «Pommes (+2,50)», «Groß (+1,00)».

    price_delta — надбавка к цене позиции (Decimal евро, как остальной каталог);
    0 = без надбавки. Снимок (label + delta) уходит в заказ при оформлении (A4b).
    """

    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=100)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} (+{self.price_delta})"


class Combo(SoftDeleteMixin):
    """Комбо-набор (A4 Gastro): несколько позиций по фикс-цене (Menü/Deal).

    Состав — группы выбора (ComboGroup): фиксированная позиция = группа с одной
    опцией; выбор = группа с несколькими («выбери напиток/гарнир»). Итоговая
    цена = price + Σ надбавок выбранных опций (ComboOption.price_delta).
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name

    @property
    def groups_active(self):
        return [g for g in self.groups.all() if g.is_active]


class ComboGroup(TimestampedModel):
    """Группа выбора внутри комбо: «Getränk» (выбери 1), «Hauptgericht» (фикс)."""

    combo = models.ForeignKey(Combo, on_delete=models.CASCADE, related_name="groups")
    label = models.CharField(max_length=100)
    min_select = models.PositiveSmallIntegerField(default=1)
    max_select = models.PositiveSmallIntegerField(default=1)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.label

    @property
    def is_required(self) -> bool:
        return self.min_select >= 1

    @property
    def is_multi(self) -> bool:
        return self.max_select != 1

    @property
    def options_active(self):
        return [
            o for o in self.options.all() if o.is_active and o.product_id and o.product.is_active
        ]


class ComboOption(TimestampedModel):
    """Опция группы комбо: товар-выбор + опц. надбавка («Groß +1,00»)."""

    group = models.ForeignKey(ComboGroup, on_delete=models.CASCADE, related_name="options")
    # SET_NULL: комбо переживает удаление товара (мёртвая опция отфильтровывается).
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.product} (+{self.price_delta})"
