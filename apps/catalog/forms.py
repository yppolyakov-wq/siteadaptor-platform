"""Формы каталога. i18n-поля (name/description) редактируются отдельными
полями de/en и собираются в JSONField.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Category, Product


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
