"""Формы каталога. i18n-поля (name/description) редактируются отдельными
полями de/en и собираются в JSONField.
"""

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    name_de = forms.CharField(label=_("Name (DE)"), max_length=200)
    name_en = forms.CharField(label=_("Name (EN)"), max_length=200, required=False)

    class Meta:
        model = Category
        fields = ["parent", "slug", "icon", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = _("Leave blank to generate from the German name.")
        self.fields["parent"].required = False

        qs = Category.objects.all()
        if self.instance and self.instance.pk:
            # нельзя выбрать родителем саму категорию или её потомка (цикл)
            qs = qs.exclude(pk__in=self._descendant_ids(self.instance))
            self.fields["name_de"].initial = (self.instance.name or {}).get("de", "")
            self.fields["name_en"].initial = (self.instance.name or {}).get("en", "")
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
        category.name = {
            "de": self.cleaned_data["name_de"],
            "en": self.cleaned_data.get("name_en", ""),
        }
        category.slug = self.cleaned_data["slug"]
        if commit:
            category.save()
        return category


class ProductForm(forms.ModelForm):
    name_de = forms.CharField(label=_("Name (DE)"), max_length=200)
    name_en = forms.CharField(label=_("Name (EN)"), max_length=200, required=False)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    description_en = forms.CharField(
        label=_("Description (EN)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "base_price",
            "currency",
            "sku",
            "stock_quantity",
            "is_active",
            "is_featured",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # живые категории в выпадашке
        self.fields["category"].queryset = Category.objects.all()
        self.fields["category"].required = False
        if self.instance and self.instance.pk:
            self.fields["name_de"].initial = (self.instance.name or {}).get("de", "")
            self.fields["name_en"].initial = (self.instance.name or {}).get("en", "")
            self.fields["description_de"].initial = (self.instance.description or {}).get("de", "")
            self.fields["description_en"].initial = (self.instance.description or {}).get("en", "")

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price must be ≥ 0."))
        return price

    def save(self, commit=True):
        product = super().save(commit=False)
        product.name = {
            "de": self.cleaned_data["name_de"],
            "en": self.cleaned_data.get("name_en", ""),
        }
        product.description = {
            "de": self.cleaned_data.get("description_de", ""),
            "en": self.cleaned_data.get("description_en", ""),
        }
        if commit:
            product.save()
        return product
