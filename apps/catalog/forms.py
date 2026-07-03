"""Формы каталога. i18n-поля (name/description) редактируются отдельными
полями de/en и собираются в JSONField.
"""

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.i18n_input import DynamicI18nFormMixin

from .food import ADDITIVES, ALLERGENS, DIETS
from .models import Category, Product


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

    class Meta:
        model = Category
        fields = ["parent", "slug", "icon", "sort_order", "is_active"]

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = _("Leave blank to generate from the German name.")
        self.fields["parent"].required = False
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
        """Догнать суффикс -2, -3… чтобы slug был уникален среди живых записей."""
        slug = base
        i = 2
        qs = Category.objects.all()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        while qs.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

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
            "currency",
            "unit",
            "content_amount",
            "sku",
            "gtin",
            "stock_quantity",
            "origin",
            "ingredients",
            "is_active",
            "is_featured",
            "badge",
        ]
        labels = {"gtin": _("EAN / GTIN (barcode)"), "badge": _("Badge")}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # живые категории в выпадашке
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].required = False
        self.init_i18n_fields(tenant)  # L3d.5
        if self.instance and self.instance.pk:
            self.fields["allergens"].initial = list(self.instance.allergens or [])
            self.fields["additives"].initial = list(self.instance.additives or [])
            self.fields["diets"].initial = list(self.instance.diets or [])

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price must be ≥ 0."))
        return price

    def save(self, commit=True):
        product = super().save(commit=False)
        product.name = self.collect_i18n("name")
        product.description = self.collect_i18n("description")
        product.allergens = self.cleaned_data.get("allergens", [])
        product.additives = self.cleaned_data.get("additives", [])
        product.diets = self.cleaned_data.get("diets", [])
        if commit:
            product.save()
        return product
