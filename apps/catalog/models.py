"""Каталог: Category и Product (TENANT-схема).

Спецификация: phase1-implementation-guide.md, Часть 2 + дополнения:
- soft-delete (доп. 1.3) — patterns/soft-delete.md
- FileRef-envelope для images (доп. 2.2)
- i18n JSONField + metadata на runtime-моделях
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import I18nMixin, SoftDeleteMixin, TimestampedModel, resolve_overlay

# Ф3: переводимые метки бейджа для витрины. BADGE_CHOICES на модели остаётся
# немецким (форма кабинета/БД/миграции не трогаем) — здесь тот же msgid, но
# lazy: на витрине резолвится в язык клиента (переводы в django.po).
BADGE_LABELS = {
    "tagesgericht": _("Tagesgericht"),
    "neu": _("Neu"),
    "beliebt": _("Beliebt"),
    "empfehlung": _("Empfehlung"),
}


class Category(SoftDeleteMixin, I18nMixin):
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
    )
    name = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    # H2-vision «категории с описанием»: i18n-описание, показывается на странице
    # каталога при выбранной категории (как интро раздела). Пусто → ничего.
    description = models.JSONField(default=dict, blank=True)  # {"de": "...", "en": "..."}
    slug = models.SlugField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # FB-6: фото категории/подкатегории (FileRef-конверт, как Product.images) —
    # плитка на витрине (секция «Categories», листинг) + управление в кабинете.
    images = models.JSONField(default=list, blank=True)
    # M2 Boutique: Größentabelle категории — строки «S | 86–90 | 70–74» (первая
    # строка = заголовки, ячейки через «|»); карточка товара показывает модалку
    # «📏 Größentabelle» при непустой таблице категории.
    size_table = models.TextField(blank=True)
    # I18N-10: перевод таблицы (заголовки «Größe/Brust/Taille» осмысленны для
    # покупателя). База — плоское поле; при отсутствии перевода показываем её.
    size_table_i18n = models.JSONField(default=dict, blank=True)

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

    @property
    def primary_image(self) -> dict | None:
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        return imgs[0] if imgs else None

    @property
    def image_url(self) -> str:
        """URL главного фото ('' если фото нет) — для плитки категории на витрине."""
        img = self.primary_image
        return img.get("url", "") if img else ""

    @property
    def landing_ready(self) -> bool:
        """DS-7a: есть ли контент для лендинга направления /bereich/<slug>/
        (описание с текстом или фото) — плитки ссылаются на лендинг только
        тогда (пустой лендинг хуже фильтра каталога)."""
        return any((self.description or {}).values()) or bool(self.images)

    @property
    def size_table_rows(self) -> list[list[str]]:
        """M2: разобранная Größentabelle — [[ячейки], …]; пусто при отсутствии.

        I18N-10: разбираем ЛОКАЛИЗОВАННЫЙ текст (перевод при наличии, иначе база)
        — таблица целиком показная, в учёте не участвует.
        """
        rows = []
        for line in (resolve_overlay(self.size_table, self.size_table_i18n) or "").splitlines():
            cells = [c.strip() for c in line.split("|")]
            if any(cells):
                rows.append(cells)
        return rows


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

    # M4-B Lookbook (план m4-boutique-plan-2026-07-30 §B): подборки владельца —
    # «Herbst-Looks», «Business». Товар может входить в несколько; на витрине это
    # фасет-чипы каталога (?kollektion=<slug>) и страница образа /lookbook/<slug>/.
    # Тот же M2M-паттерн, что у Service/StayUnit (UB3-2).
    collections = models.ManyToManyField(
        "collections.Collection", blank=True, related_name="products"
    )

    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")

    # PAngV (R2): Grundpreis (€/kg|l). unit — единица контента, content_amount —
    # количество (250 г, 0.75 л). Stück/пусто → без Grundpreis (несчётные товары).
    UNIT_CHOICES = [
        ("", _("Stück / —")),
        ("g", _("Gramm")),
        ("kg", _("Kilogramm")),
        ("ml", _("Milliliter")),
        ("l", _("Liter")),
    ]
    unit = models.CharField(max_length=4, blank=True, choices=UNIT_CHOICES)
    content_amount = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    stock_quantity = models.IntegerField(null=True, blank=True)

    # T5 (R2/R4): Einkauf & Bestellwesen. cost_price — Einkaufspreis netto
    # (Bestandswert/Marge). reorder_point/reorder_target — Meldebestand/Sollbestand
    # des Artikels (Bestellvorschlag; überschreibt den globalen Schwellwert). Alle
    # optional; None = nicht gepflegt (kein Wert/keine Empfehlung).
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reorder_point = models.IntegerField(null=True, blank=True)
    reorder_target = models.IntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    # Вид выбора вариантов на витрине (реестр option_styles.VARIANT_STYLES):
    # список / кнопки / цветные кружки / фото-плитки / строки / две оси.
    # Пусто = дефолт магазина (site_defaults.variant_style), а он пуст = список.
    variant_style = models.CharField(max_length=12, blank=True, default="")

    # Маркетинговый бейдж на витрине (T1): «Tagesgericht», «Neu», «Beliebt».
    # Пусто = без бейджа. is_featured (популярные на главной) — отдельно.
    BADGE_CHOICES = [
        ("", "—"),
        ("tagesgericht", _("Tagesgericht")),
        ("neu", _("Neu")),
        ("beliebt", _("Beliebt")),
        ("empfehlung", _("Empfehlung")),
    ]
    badge = models.CharField(max_length=20, blank=True, choices=BADGE_CHOICES)

    # Lebensmittel-Kennzeichnung (LMIV, R4): аллергены (коды из apps.catalog.food),
    # происхождение и список ингредиентов. Заполняется для еды; на витрине
    # показывается только при наличии.
    allergens = models.JSONField(default=list, blank=True)
    # E-2/LMZDV: kennzeichnungspflichtige Zusatzstoffe (коды из catalog.food.ADDITIVES).
    additives = models.JSONField(default=list, blank=True)
    # A4: диет-теги (vegan/vegetarisch/glutenfrei/…) — иконки на карточке + фильтр меню.
    # Коды из catalog.food.DIETS; на витрине показываются только при наличии.
    diets = models.JSONField(default=list, blank=True)
    # MEN-2: тип подачи (Gang) — коды из catalog.food.COURSES ("" = не задан).
    # Группирует блюда в «свободной сборке» меню и в PDF-Speisekarte.
    course = models.CharField(max_length=20, blank=True, default="")
    origin = models.CharField(max_length=120, blank=True)
    ingredients = models.TextField(blank=True)
    # Ф2 (per-language): переводы неосновных локалей для origin/ingredients (overlay —
    # база в плоском поле = LANGUAGE_CODE, переводы тут). Как name_i18n у Service/Combo.
    origin_i18n = models.JSONField(default=dict, blank=True)
    ingredients_i18n = models.JSONField(default=dict, blank=True)

    # M1 Boutique (Textilkennzeichnung EU 1007/2011, план mode-boutique-plan §3):
    # состав материала («95 % Baumwolle, 5 % Elasthan») — у одежды ОБЯЗАН стоять
    # на карточке до кнопки заказа (официальные названия волокон); care —
    # Pflegehinweise. Витрина показывает только при наличии; overlay-i18n как у
    # origin/ingredients (Ф2).
    material = models.CharField(max_length=255, blank=True)
    care = models.CharField(max_length=255, blank=True)
    material_i18n = models.JSONField(default=dict, blank=True)
    care_i18n = models.JSONField(default=dict, blank=True)

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
        """Человекочитаемый бейдж («Tagesgericht») или '' если не задан. Ф3:
        переводимая метка (BADGE_LABELS, lazy) — на витрине в языке клиента."""
        return BADGE_LABELS.get(self.badge, "") if self.badge else ""

    @property
    def name_text(self) -> str:
        return self.get_i18n("name")

    @property
    def description_text(self) -> str:
        return self.get_i18n("description")

    def origin_localized(self, locale: str | None = None) -> str:
        """Ф2: Herkunft на локали (перевод из origin_i18n, иначе базовое origin)."""
        return self.get_overlay("origin", "origin_i18n", locale)

    def ingredients_localized(self, locale: str | None = None) -> str:
        """Ф2: Zutaten на локали (перевод из ingredients_i18n, иначе базовое ingredients)."""
        return self.get_overlay("ingredients", "ingredients_i18n", locale)

    def material_localized(self, locale: str | None = None) -> str:
        """M1: состав материала на локали (Textilkennzeichnung)."""
        return self.get_overlay("material", "material_i18n", locale)

    def care_localized(self, locale: str | None = None) -> str:
        """M1: Pflegehinweise на локали."""
        return self.get_overlay("care", "care_i18n", locale)

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
    def stock_value(self):
        """T5: Bestandswert (Bestand × EK) товара без вариантов, или None
        (не учитывается / EK не задан). Вариантные товары считают Wert на вариантах."""
        if self.stock_quantity is None or self.cost_price is None:
            return None
        return self.cost_price * self.stock_quantity

    @property
    def margin_pct(self):
        """T5: Marge % = (VK − EK)/VK по base_price. None если нет EK или VK ≤ 0."""
        from .pricing import margin_pct

        return margin_pct(self.base_price, self.cost_price)

    def effective_reorder_point(self, global_threshold):
        """T5: Meldebestand артикула (reorder_point) или глобальный порог кабинета."""
        return self.reorder_point if self.reorder_point is not None else global_threshold

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

    @property
    def additive_labels(self) -> list[str]:
        """Подписи Zusatzstoffe (DE) для витрины — из кодов self.additives."""
        from .food import additive_labels

        return additive_labels(self.additives)

    @property
    def diet_badges(self) -> list[dict]:
        """A4: диет-теги [{code, label, icon}] для витрины — из кодов self.diets."""
        from .food import diet_badges

        return diet_badges(self.diets)


class ProductVariant(TimestampedModel):
    """Вариант товара (R1): чай 100/250 г, размер одежды, фасовка.

    Один уровень (label) — мульти-измерения (цвет×размер) в v1 не делаем. Цена
    пустая → берётся Product.base_price. stock_quantity — на варианте (atomic-
    списание при заказе — R3). label уникален в пределах товара.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    label = models.CharField(max_length=100)  # «100 g», «M», «6er-Pack», «S · Blau»
    # M4-A (план m4a-variant-axes-plan-2026-07-31): ОСИ варианта. Добавлены РЯДОМ
    # с label, а не вместо него: на label держатся склад-леджер, позиции заказа,
    # PDF, фид и CSV-импорт (match по (product,label)) — замена ключа переписала бы
    # пять подсистем. Обе оси пусты = поведение ровно как раньше.
    size = models.CharField(max_length=40, blank=True)  # «S», «38», «100 g»
    color = models.CharField(max_length=40, blank=True)  # «Blau», «Anthrazit»
    # I18N-10: переводы МЕТОК для показа на витрине (overlay-семантика L3: база —
    # в плоском поле, переводы неосновных локалей — здесь). Плоские поля остаются
    # ключами учёта: склад-леджер, позиции заказа, CSV-импорт (match по label /
    # (size,color)) и оси фасета читают ИХ, поэтому перевод не рвёт подсистемы.
    label_i18n = models.JSONField(default=dict, blank=True)
    size_i18n = models.JSONField(default=dict, blank=True)
    color_i18n = models.JSONField(default=dict, blank=True)
    # Фото варианта (FileRef-конверт как Product.images): при выборе подменяет
    # главное фото на витрине; галерея товара не трогается.
    images = models.JSONField(default=list, blank=True)
    sku = models.CharField(max_length=100, blank=True)
    gtin = models.CharField(max_length=14, blank=True)  # A1: EAN/GTIN варианта
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # PAngV (R2): контент варианта для Grundpreis (чай 100 г vs 250 г); пусто →
    # берётся Product.content_amount. Единица (unit) — на товаре.
    content_amount = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    stock_quantity = models.IntegerField(null=True, blank=True)
    # T5 (R2/R4): Einkaufspreis (Fallback → Product.cost_price) + Meldebestand/
    # Sollbestand des Varianten-Bestands.
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reorder_point = models.IntegerField(null=True, blank=True)
    reorder_target = models.IntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "label"], name="variant_product_label_uniq"),
        ]

    def __str__(self):
        return f"{self.product} · {self.label}"

    def axis_label(self) -> str:
        """Подпись из осей («S · Blau»); пусто, если ни одна ось не задана."""
        return " · ".join(p for p in (self.size, self.color) if p)

    # I18N-10: показ на языке посетителя. Учёт (склад/заказ/импорт/фасет) читает
    # ПЛОСКИЕ поля — эти свойства только для рендера витрины.
    @property
    def label_localized(self) -> str:
        """Метка на языке посетителя.

        Порядок: свой перевод метки → сборка из ПЕРЕВЕДЁННЫХ осей → плоский label.
        Второй шаг важен для одежды: метка «S · Blau» производна от осей (save()
        собирает её), отдельного перевода у неё нет — иначе на любой локали
        оставалось бы немецкое «Blau».
        """
        own = resolve_overlay(self.label, self.label_i18n)
        if own != self.label:
            return own
        from_axes = self.axis_label_localized
        if from_axes and from_axes != self.axis_label():
            return from_axes
        return self.label or ""

    @property
    def size_localized(self) -> str:
        return resolve_overlay(self.size, self.size_i18n)

    @property
    def color_localized(self) -> str:
        return resolve_overlay(self.color, self.color_i18n)

    @property
    def axis_label_localized(self) -> str:
        """Подпись из ПЕРЕВЕДЁННЫХ осей — для показа рядом с фото/в списке."""
        return " · ".join(p for p in (self.size_localized, self.color_localized) if p)

    def save(self, *args, **kwargs):
        """label — производный ключ: заполняем из осей ТОЛЬКО когда он пуст.
        Ручной label и старые варианты остаются как есть (их держат заказы/склад)."""
        if not (self.label or "").strip():
            self.label = self.axis_label()
        super().save(*args, **kwargs)

    @property
    def primary_image(self) -> dict | None:
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        return imgs[0] if imgs else None

    @property
    def image_url(self) -> str:
        """URL фото варианта ('' если нет) — подмена главного фото на витрине."""
        img = self.primary_image
        return img.get("url", "") if img else ""

    @property
    def price_value(self):
        """Цена варианта: своя или фолбэк на base_price товара."""
        return self.price if self.price is not None else self.product.base_price

    @property
    def cost_value(self):
        """T5: Einkaufspreis варианта — свой или фолбэк на Product.cost_price."""
        return self.cost_price if self.cost_price is not None else self.product.cost_price

    @property
    def stock_value(self):
        """T5: Bestandswert варианта (Bestand × EK) или None."""
        cost = self.cost_value
        if self.stock_quantity is None or cost is None:
            return None
        return cost * self.stock_quantity

    @property
    def margin_pct(self):
        """T5: Marge % = (VK − EK)/VK по price_value/cost_value. None если нет EK/VK≤0."""
        from .pricing import margin_pct

        return margin_pct(self.price_value, self.cost_value)

    def effective_reorder_point(self, global_threshold):
        """T5: Meldebestand варианта или глобальный порог кабинета."""
        return self.reorder_point if self.reorder_point is not None else global_threshold

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
    # I18N-10: перевод названия группы для витрины (база — в плоском `name`).
    name_i18n = models.JSONField(default=dict, blank=True)
    # Вид выбора на витрине (реестр option_styles.MODIFIER_STYLES). Per-группа,
    # потому что «Größe» и «Beilage» просят разного; "" = как раньше.
    display_style = models.CharField(max_length=12, blank=True, default="")
    min_select = models.PositiveIntegerField(default=0)
    max_select = models.PositiveIntegerField(default=1)  # 0 = без предела
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.product} · {self.name}"

    @property
    def name_localized(self) -> str:
        """I18N-10: название группы на языке посетителя (показ, не учёт)."""
        return resolve_overlay(self.name, self.name_i18n)

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
    # I18N-10: перевод метки опции. В ЗАКАЗ уходит снимок плоского `label`
    # (что заказано — то и зафиксировано), переводится только показ на витрине.
    label_i18n = models.JSONField(default=dict, blank=True)
    # Фидбэк 2026-08-04: артикул опции — справочный (у опций нет складского
    # остатка); печатается в заказе/документах рядом с меткой.
    sku = models.CharField(max_length=100, blank=True)
    # Фото опции (FileRef-конверт, как у core.Extra.image). Пусто = без фото —
    # прежний текстовый вид. Нужно для видов «плитки»/«список с фото».
    image = models.JSONField(default=dict, blank=True)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.label} (+{self.price_delta})"

    @property
    def label_localized(self) -> str:
        """I18N-10: метка опции на языке посетителя (в заказ уходит плоская)."""
        return resolve_overlay(self.label, self.label_i18n)

    @property
    def image_url(self) -> str:
        """URL фото опции ('' если нет) — как у core.Extra."""
        img = self.image if isinstance(self.image, dict) else {}
        return img.get("url", "")


class Combo(I18nMixin, SoftDeleteMixin):
    """Комбо-набор (A4 Gastro): несколько позиций по фикс-цене (Menü/Deal).

    Состав — группы выбора (ComboGroup): фиксированная позиция = группа с одной
    опцией; выбор = группа с несколькими («выбери напиток/гарнир»). Итоговая
    цена = price + Σ надбавок выбранных опций (ComboOption.price_delta).
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # L3 (Волна L): переводы имени/описания на НЕОСНОВНЫЕ локали (оверлей
    # {locale: str}). Базовая локаль — в плоских name/description (source of
    # truth, без дрейфа) — как у booking.Service/stays.StayUnit.
    name_i18n = models.JSONField(default=dict, blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    # MEN-2 (волна Menü-Sets): галерея набора — FileRef-конверты, как Product.images.
    images = models.JSONField(default=list, blank=True)
    # Привязка к направлению (категории): блок «Menü-Pakete» на лендинге DS-7 и
    # пул блюд режима «свободная сборка». SET_NULL — набор переживает категорию.
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="combos"
    )
    # Кейтеринг: цена «pro Person» — qty в корзине трактуется как число персон.
    price_per_person = models.BooleanField(default=False)
    # Минимальный заказ в персонах (0 = без минимума); показывается в карточке,
    # детали и агрегаторе, валидируется на сервере (combo_add/checkout).
    min_persons = models.PositiveSmallIntegerField(default=0)
    # Поводы («Hochzeit», «Firmenfeier»…): свободные строки владельца — один
    # словарь с формой заявки AF-1 (site_config["anfrage"]["event_types"]).
    event_types = models.JSONField(default=list, blank=True)
    # Режим «свободная сборка»: состав = все активные блюда category по Gang'ам,
    # группы игнорируются, цены à la carte (Product.base_price). Витрина — MEN-4.
    free_pool = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name

    @property
    def primary_image_url(self) -> str:
        """URL главного фото галереи ('' если фото нет) — карточки/адаптер."""
        imgs = self.images if isinstance(self.images, list) else []
        for img in imgs:
            if isinstance(img, dict) and img.get("is_primary") and img.get("url"):
                return img["url"]
        for img in imgs:
            if isinstance(img, dict) and img.get("url"):
                return img["url"]
        return ""

    def name_localized(self, locale: str | None = None) -> str:
        """L3: имя комбо на локали (перевод из name_i18n, иначе базовое name)."""
        return self.get_overlay("name", "name_i18n", locale)

    def description_localized(self, locale: str | None = None) -> str:
        """L3: описание комбо на локали (перевод из description_i18n, иначе базовое)."""
        return self.get_overlay("description", "description_i18n", locale)

    @property
    def groups_active(self):
        return [g for g in self.groups.all() if g.is_active]


class ComboGroup(I18nMixin, TimestampedModel):
    """Группа выбора внутри комбо: «Getränk» (выбери 1), «Hauptgericht» (фикс)."""

    combo = models.ForeignKey(Combo, on_delete=models.CASCADE, related_name="groups")
    label = models.CharField(max_length=100)
    label_i18n = models.JSONField(default=dict, blank=True)  # I18N-12: заголовок шага
    # MEN-2: «Im Set enthalten» — фикс-состав (режим 1): опции рендерятся
    # плитками без выбора и в валидации/цене НЕ участвуют (их стоимость уже
    # заложена в Combo.price). Гость их не отправляет.
    included = models.BooleanField(default=False)
    min_select = models.PositiveSmallIntegerField(default=1)
    max_select = models.PositiveSmallIntegerField(default=1)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.label

    def label_localized(self, locale: str | None = None) -> str:
        """I18N-12: заголовок шага конфигуратора набора на локали."""
        return self.get_overlay("label", "label_i18n", locale)

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


class ProductReview(TimestampedModel):
    """A1/A2: отзыв о товаре (TENANT-схема). Оставлять может только верифицированный
    покупатель — проверка наличия заказа с этим товаром по email (apps.catalog.reviews).
    Один отзыв на (товар, email); повторная отправка обновляет. Владелец может скрыть
    (is_published=False) — лёгкая модерация. Агрегат avg/count — apps.catalog.reviews.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()  # 1..5 (валидируется во вьюхе)
    author_name = models.CharField(max_length=120)
    email = models.EmailField()
    comment = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "email"], name="product_review_product_email_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["product", "is_published"], name="product_review_pub_idx"),
        ]

    def __str__(self):
        return f"{self.product_id}: {self.rating}★ ({self.author_name})"

    @property
    def stars(self) -> str:
        return "★" * self.rating + "☆" * (5 - self.rating)


class PriceLog(TimestampedModel):
    """§11 PAngV (M1 Boutique, план mode-boutique-plan-2026-07-30): append-only
    журнал цен товара/варианта. Пишется сигналом при ИЗМЕНЕНИИ цены (первая
    запись — при создании); 30-дневный минимум питает строку «Niedrigster
    Preis der letzten 30 Tage» у зачёркнутой Sale-цены (без данных — честно
    молчим). Не редактируется и не чистится (лог)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_logs")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="price_logs",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "created_at"], name="pricelog_product_idx"),
        ]

    def __str__(self):
        return f"{self.product_id}: {self.price} ({self.created_at:%Y-%m-%d})"


class ProductWaitlist(TimestampedModel):
    """M2 Boutique (план mode-boutique-plan-2026-07-30): лист ожидания товара/
    размера («Größe M ausverkauft → benachrichtigen»). Уведомление уходит при
    приёмке склада (inventory.apply_manual_movement, change>0, on_commit);
    notified=True защищает от повторов, уникальность — на ЖИВУЮ подписку."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="waitlist_entries")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="waitlist_entries",
    )
    email = models.EmailField()
    notified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant", "email"],
                condition=models.Q(notified=False),
                name="uniq_product_waitlist_pending",
            )
        ]

    def __str__(self):
        return f"{self.product_id}/{self.variant_id or '-'}: {self.email}"
