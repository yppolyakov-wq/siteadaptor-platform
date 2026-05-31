"""Формы кабинета: создание/редактирование акций.

i18n-поля (title/description) редактируются парами de/en и собираются в
JSONField. Статус акции через форму не меняется — только через PromotionSM
(кнопки переходов). starts_at/ends_at — datetime-local.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product

from .models import Promotion

_DT_FMT = "%Y-%m-%dT%H:%M"


class _DateTimeLocal(forms.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(
            required=False,
            input_formats=[_DT_FMT],
            widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=_DT_FMT),
            **kwargs,
        )


class PromotionForm(forms.ModelForm):
    title_de = forms.CharField(label=_("Title (DE)"), max_length=200)
    title_en = forms.CharField(label=_("Title (EN)"), max_length=200, required=False)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    description_en = forms.CharField(
        label=_("Description (EN)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    starts_at = _DateTimeLocal(label=_("Starts at"))
    ends_at = _DateTimeLocal(label=_("Ends at"))

    class Meta:
        model = Promotion
        fields = [
            "product",
            "promo_type",
            "discount_percent",
            "price_override",
            "available_quantity",
            "max_per_customer",
            "reservation_ttl_hours",
            "auto_confirm",
            "starts_at",
            "ends_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.all()
        self.fields["product"].required = False
        if self.instance and self.instance.pk:
            self.fields["title_de"].initial = (self.instance.title or {}).get("de", "")
            self.fields["title_en"].initial = (self.instance.title or {}).get("en", "")
            self.fields["description_de"].initial = (self.instance.description or {}).get("de", "")
            self.fields["description_en"].initial = (self.instance.description or {}).get("en", "")

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", _("End must be after start."))
        return cleaned

    def save(self, commit=True):
        promo = super().save(commit=False)
        promo.title = {
            "de": self.cleaned_data["title_de"],
            "en": self.cleaned_data.get("title_en", ""),
        }
        promo.description = {
            "de": self.cleaned_data.get("description_de", ""),
            "en": self.cleaned_data.get("description_en", ""),
        }
        if commit:
            promo.save()
        return promo
