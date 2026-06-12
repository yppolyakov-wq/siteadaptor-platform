"""Формы CRM-минимума (Track C3)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.promotions.models import Customer


class CustomerForm(forms.ModelForm):
    tags_input = forms.CharField(
        label=_("Tags"),
        required=False,
        help_text=_("Comma-separated, e.g.: stammkunde, vip"),
    )

    class Meta:
        model = Customer
        fields = ["name", "email", "phone", "note", "marketing_opt_in"]
        labels = {"marketing_opt_in": _("Marketing consent")}
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
        if commit:
            customer.save()
        return customer


class NoteForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), max_length=2000)
