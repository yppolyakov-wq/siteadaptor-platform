"""Формы CRM-минимума (Track C3)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.promotions.models import Customer

from .models import Company


class CustomerForm(forms.ModelForm):
    tags_input = forms.CharField(
        label=_("Tags"),
        required=False,
        help_text=_("Comma-separated, e.g.: stammkunde, vip"),
    )

    class Meta:
        model = Customer
        fields = ["name", "email", "phone", "company", "note", "marketing_opt_in"]
        labels = {"marketing_opt_in": _("Marketing consent"), "company": _("Company")}
        help_texts = {
            "marketing_opt_in": _(
                "Only tick if the customer explicitly agreed to receive offers (UWG §7)."
            )
        }
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tags_input"].initial = ", ".join(self.instance.tags or [])
        # CO-1: селект появляется только когда справочник не пуст — форма
        # клиента без компаний остаётся прежней (не пугаем маленький бизнес).
        if Company.objects.exists():
            self.fields["company"].empty_label = "—"
        else:
            self.fields.pop("company")

    def clean_tags_input(self):
        raw = self.cleaned_data.get("tags_input", "")
        tags = []
        for tag in raw.split(","):
            tag = tag.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
        return tags[:20]

    def save(self, commit=True):
        customer = super().save(commit=False)
        customer.tags = self.cleaned_data.get("tags_input", [])
        # PMS-аудит 2026-07-27: фиксируем момент согласия (доказательство UWG §7)
        # при переводе галки владельцем в True.
        if customer.marketing_opt_in and not customer.marketing_opt_in_at:
            from django.utils import timezone

            customer.marketing_opt_in_at = timezone.now()
        if commit:
            customer.save()
        return customer


class NoteForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), max_length=2000)


class CompanyForm(forms.ModelForm):
    """CO-1: реквизиты компании для счетов и привязки корпоративных гостей."""

    class Meta:
        model = Company
        fields = [
            "name",
            "vat_id",
            "street",
            "postal_code",
            "city",
            "email",
            "phone",
            "discount_percent",
            "note",
        ]
        labels = {
            "vat_id": _("USt-IdNr. (VAT ID)"),
            "street": _("Street"),
            "postal_code": _("Postal code"),
            "city": _("City"),
            "discount_percent": _("Discount %"),
        }
        help_texts = {
            "vat_id": _("Shown on invoices for this company."),
            "discount_percent": _("Groundwork for corporate rates (v2) — shown on the card."),
        }
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}
