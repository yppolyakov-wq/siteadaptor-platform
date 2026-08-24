"""Формы каталога. i18n-поля (name/description) редактируются отдельными
полями de/en и собираются в JSONField.
"""

from decimal import Decimal

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.i18n_input import DynamicI18nFormMixin

from .food import ADDITIVES, ALLERGENS, COURSES, DIETS
from .models import Category, Product
from .option_styles import VARIANT_STYLES


class CategoryForm(DynamicI18nFormMixin, forms.ModelForm):
    # L3d.5: база (de) статическая, поля прочих локалей — динамически по
    # active_locales тенанта (без тенанта — весь реестр, паритет).
    name_de = forms.CharField(label=_("Name (DE)"), max_length=200)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    i18n_fields = (
        ("name", {"label": "Name", "max_length": 200}),
        ("description", {"label": "Beschreibung", "textarea": True}),
    )

    # KAT-1: шаблон страницы категории (реестр category_styles; "" = Standard).
    page_style = forms.ChoiceField(label=_("Seitenvorlage"), required=False)

    class Meta:
        model = Category
        fields = ["parent", "slug", "page_style", "icon", "sort_order", "is_active", "size_table"]
        labels = {"size_table": _("Größentabelle")}
        help_texts = {
            "size_table": _(
                "Optional (Mode/Schuhe): eine Zeile pro Größe, Spalten mit „|“ — "
                "erste Zeile = Überschriften. Beispiel: „Größe | Brust (cm)“."
            )
        }
        widgets = {"size_table": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = _("Leave blank to generate from the German name.")
        self.fields["parent"].required = False
        from apps.catalog.category_styles import CATEGORY_PAGE_STYLES

        self.fields["page_style"].choices = [
            (code, f"{label} — {hint}") for code, label, hint in CATEGORY_PAGE_STYLES
        ]
        self.fields["page_style"].help_text = _(
            "Wie die Seite /sortiment/<slug>/ dieser Kategorie aufgebaut ist."
        )
        self.init_i18n_fields(tenant)  # L3d.5: динамика + initial всех локалей

        qs = Category.objects.all()
        if self.instance and self.instance.pk:
            # нельзя выбрать родителем саму категорию или её потомка (цикл)
            qs = qs.exclude(pk__in=self._descendant_ids(self.instance))
        self.fields["parent"].queryset = qs

    @staticmethod
    def _descendant_ids(category) -> list:
        """id самой категории + всех её потомков (обход вниз по parent)."""
        ids = [category.pk]
        stack = list(Category.objects.filter(parent=category))
        while stack:
            node = stack.pop()
            ids.append(node.pk)
            stack.extend(Category.objects.filter(parent=node))
        return ids

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and self.instance.pk:
            if parent.pk == self.instance.pk:
                raise forms.ValidationError(_("A category cannot be its own parent."))
            if parent.pk in self._descendant_ids(self.instance):
                raise forms.ValidationError(_("Cannot move a category under its own descendant."))
        return parent

    def _unique_slug(self, base: str) -> str:
        """KAT-6: общая утилита slugs.unique_slug (сидер и товары — тот же код)."""
        from apps.catalog.slugs import unique_slug

        return unique_slug(
            Category, base, exclude_pk=self.instance.pk if self.instance.pk else None
        )

    def clean(self):
        cleaned = super().clean()
        raw_slug = (cleaned.get("slug") or "").strip()
        if raw_slug:
            # slug задан явно — не подменяем, но проверяем уникальность
            qs = Category.objects.filter(slug=raw_slug)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("slug", _("This slug is already in use."))
            cleaned["slug"] = raw_slug
        else:
            base = slugify(cleaned.get("name_de") or "") or "category"
            cleaned["slug"] = self._unique_slug(base)
        return cleaned

    def save(self, commit=True):
        category = super().save(commit=False)
        category.name = self.collect_i18n("name")
        category.description = self.collect_i18n("description")
        category.slug = self.cleaned_data["slug"]
        if commit:
            category.save()
        return category


class ProductForm(DynamicI18nFormMixin, forms.ModelForm):
    # SR-2 (фидбэк владельца 2026-08-24): «если нет категории — добавить прямо
    # с карточки товара». Не модельное поле: создаётся при Save и назначается.
    new_category = forms.CharField(
        required=False,
        max_length=120,
        label=_("New category"),
        help_text=_("Wird beim Speichern angelegt und diesem Produkt zugewiesen."),
    )
    # L3d.5: см. CategoryForm — динамические per-locale поля.
    name_de = forms.CharField(label=_("Name (DE)"), max_length=200)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    i18n_fields = (
        ("name", {"label": "Name", "max_length": 200}),
        ("description", {"label": "Beschreibung", "textarea": True}),
    )
    # Lebensmittel-Kennzeichnung (LMIV, R4): аллергены чекбоксами (JSONField на модели).
    allergens = forms.MultipleChoiceField(
        label=_("Allergens"),
        choices=ALLERGENS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    # E-2/LMZDV: kennzeichnungspflichtige Zusatzstoffe чекбоксами (JSONField).
    additives = forms.MultipleChoiceField(
        label=_("Additives"),
        choices=ADDITIVES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    # SH-4: ставка НДС — выбор из трёх законных ставок DACH, а не свободное число
    # (опечатка «1,9» стоила бы владельцу неверного счёта). Модельное поле
    # остаётся Decimal — choices живут в форме, миграции не требуют.
    vat_rate = forms.TypedChoiceField(
        label=_("MwSt.-Satz"),
        choices=[("19.00", "19 %"), ("7.00", "7 %"), ("0.00", "0 %")],
        coerce=Decimal,
        initial="19.00",
        # НЕ обязательное: форму товара постят и другие поверхности (мастер,
        # импорт, тесты) — отсутствие поля не должно ронять сохранение товара.
        required=False,
    )
    # A4: диет-теги (vegan/vegetarisch/…) чекбоксами (JSONField на модели).
    diets = forms.MultipleChoiceField(
        label=_("Diets"),
        choices=[(code, f"{icon} {label}") for code, label, icon in DIETS],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "base_price",
            "primary_action",
            "vat_rate",
            "currency",
            "unit",
            "content_amount",
            "sku",
            "gtin",
            "stock_quantity",
            "cost_price",
            "reorder_point",
            "reorder_target",
            "origin",
            "ingredients",
            "material",
            "care",
            "course",
            "is_active",
            "is_featured",
            "badge",
            "variant_style",
        ]
        labels = {
            # M1 Boutique: Textilkennzeichnung (EU 1007/2011) + Pflegehinweise.
            "material": _("Material / Zusammensetzung"),
            "care": _("Pflegehinweise"),
            "gtin": _("EAN / GTIN (barcode)"),
            "badge": _("Badge"),
            "variant_style": _("How to show the options"),
            "cost_price": _("Einkaufspreis (netto)"),
            "vat_rate": _("MwSt.-Satz"),
            "reorder_point": _("Meldebestand"),
            "reorder_target": _("Sollbestand"),
        }
        # W2: подсказки под полями (шаблон теперь их выводит) — снимают непонятность.
        help_texts = {
            "unit": _("Für den Grundpreis (z. B. €/kg). Zusammen mit der Menge."),
            "content_amount": _("Inhalt je Packung — z. B. 500 (bei Einheit „g“ → €/kg)."),
            "currency": _("Standard: EUR."),
            # SH-4: ставка нужна для разбивки итога — цена остаётся брутто (PAngV).
            # Без литерального «%»: xgettext помечает такую строку python-format,
            # и голый процент ломает извлечение (тот же класс, что уже правили
            # в форме раньше — см. build-log 2026-07-11).
            "vat_rate": _(
                "Im Preis enthalten (Bruttopreis). Lebensmittel meist 7, "
                "Standard 19 (Angabe in Prozent). Bei Kleinunternehmerregelung "
                "nach § 19 UStG ohne Wirkung."
            ),
            "cost_price": _("Nur intern — für die Margen-Anzeige, nicht öffentlich."),
            "reorder_point": _("Ab diesem Bestand meldet der Shop „nachbestellen“."),
            "stock_quantity": _("Leer = unbegrenzt (kein Bestandslimit)."),
            "gtin": _("Barcode für Preisportale/Feeds — optional."),
            "badge": _("Kleiner Aufkleber auf der Karte (z. B. „Neu“, „Beliebt“)."),
            "variant_style": _("Leer = wie in den Website-Einstellungen eingestellt."),
            "material": _(
                "Textilkennzeichnung: offizielle Fasernamen, z. B. „95 % Baumwolle, "
                "5 % Elasthan“ — Pflichtangabe bei Kleidung."
            ),
            "care": _("z. B. „30 °C Schonwäsche, nicht trocknergeeignet“ — optional."),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # живые категории в выпадашке
        self.fields["category"].queryset = Category.objects.all()
        # SR-2b (фидбэк «пустота внутри»): правая колонка живёт ВНЕ <form>
        # (панель вариантов с мини-формами должна стоять сразу под main-картой,
        # вложенные <form> недопустимы) — поля рейла привязаны атрибутом form=.
        for name in (
            "category",
            "new_category",
            "base_price",
            "vat_rate",
            "stock_quantity",
            "reorder_point",
            "unit",
            "content_amount",
            "currency",
            "sku",
            "gtin",
            "cost_price",
            "reorder_target",
            "primary_action",
            "is_active",
        ):
            if name in self.fields:
                self.fields[name].widget.attrs["form"] = "product-form"
        self.fields["category"].required = False
        self.init_i18n_fields(tenant)  # L3d.5
        # O-2: вид выбора вариантов — из реестра, с подсказками «когда уместно».
        # Пустой пункт = «как в настройках сайта» (дефолт магазина).
        self.fields["variant_style"] = forms.ChoiceField(
            label=_("How to show the options"),
            required=False,
            choices=[(key, label) for key, label, _hint in VARIANT_STYLES],
            help_text=_("Leer = wie in den Website-Einstellungen eingestellt."),
        )
        # MEN-2: тип подачи (Gang) — реестр food.COURSES; ChoiceField валидирует код.
        self.fields["course"] = forms.ChoiceField(
            label=_("Gang"),
            required=False,
            choices=[("", _("— kein Gang —"))] + list(COURSES),
            help_text=_("Für Menü-Baukasten und Speisekarte: Vorspeise, Hauptgericht …"),
        )
        if self.instance and self.instance.pk:
            self.fields["allergens"].initial = list(self.instance.allergens or [])
            self.fields["additives"].initial = list(self.instance.additives or [])
            self.fields["diets"].initial = list(self.instance.diets or [])
        # W2: порядок полей — название/описание ПЕРВЫМИ (прежде name_de рендерился 17-м).
        # Динамические per-locale name_<loc>/description_<loc> ловим по префиксу. Секции
        # шаблона роутят по имени; порядок внутри секции = этот. Неупомянутые (если появятся)
        # order_fields допишет в конец — но здесь перечислены все.
        names = [f for f in self.fields if f.startswith("name")]
        descs = [f for f in self.fields if f.startswith("description")]
        self.order_fields(
            [
                *names,
                *descs,
                "category",
                "base_price",
                "vat_rate",
                "is_active",
                "unit",
                "content_amount",
                "currency",
                "stock_quantity",
                "cost_price",
                "reorder_point",
                "reorder_target",
                "sku",
                "gtin",
                "course",
                "allergens",
                "additives",
                "diets",
                "origin",
                "ingredients",
                "material",
                "care",
                "is_featured",
                "badge",
            ]
        )

    def clean_vat_rate(self):
        """Пустое поле = не менять: ставка остаётся у товара (или дефолт 19 %)."""
        value = self.cleaned_data.get("vat_rate")
        if value in (None, ""):
            return getattr(self.instance, "vat_rate", None) or Decimal("19.00")
        return value

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price must be ≥ 0."))
        return price

    def clean_cost_price(self):
        cost = self.cleaned_data.get("cost_price")
        if cost is not None and cost < 0:
            raise forms.ValidationError(_("Einkaufspreis muss ≥ 0 sein."))
        return cost

    def clean_reorder_point(self):
        val = self.cleaned_data.get("reorder_point")
        if val is not None and val < 0:
            raise forms.ValidationError(_("Meldebestand muss ≥ 0 sein."))
        return val

    def clean_reorder_target(self):
        val = self.cleaned_data.get("reorder_target")
        if val is not None and val < 0:
            raise forms.ValidationError(_("Sollbestand muss ≥ 0 sein."))
        return val

    def save(self, commit=True):
        product = super().save(commit=False)
        product.name = self.collect_i18n("name")
        # SR-3: визуальный редактор шлёт ограниченный HTML — санитайз при
        # сохранении (второй рубеж — фильтр rich_text на рендере).
        from apps.core import richtext

        product.description = {
            k: richtext.sanitize(v) if richtext.is_rich(v) else v
            for k, v in self.collect_i18n("description").items()
        }
        # SR-2: новая категория с карточки товара — сильнее выбора в селекте
        # (владелец заполнил имя = хочет именно её; пустое поле = ничего).
        new_cat = (self.cleaned_data.get("new_category") or "").strip()
        if new_cat:
            from apps.catalog.slugs import unique_slug

            product.category = Category.objects.create(
                name={"de": new_cat},
                slug=unique_slug(Category, new_cat, fallback="kategorie"),
            )
        product.allergens = self.cleaned_data.get("allergens", [])
        product.additives = self.cleaned_data.get("additives", [])
        product.diets = self.cleaned_data.get("diets", [])
        if commit:
            product.save()
        return product
