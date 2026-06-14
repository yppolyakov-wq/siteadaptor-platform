"""Форма события для кабинета (A6b). Цена — в евро (→ cents), анкета — построчно."""

from decimal import Decimal, InvalidOperation

from django import forms

from .models import Event


class EventForm(forms.ModelForm):
    price_eur = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2, required=False, label="Preis je Platz (€)"
    )
    questions_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Anmelde-Fragen (eine pro Zeile)",
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "description",
            "location",
            "starts_at",
            "ends_at",
            "capacity",
            "require_manual_confirm",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        if self.instance and self.instance.pk:
            self.fields["price_eur"].initial = self.instance.price_eur
            self.fields["questions_text"].initial = "\n".join(self.instance.questions or [])

    def save(self, commit=True):
        event = super().save(commit=False)
        try:
            event.price_cents = int(Decimal(self.cleaned_data.get("price_eur") or 0) * 100)
        except (InvalidOperation, TypeError):
            event.price_cents = 0
        event.questions = [
            q.strip()
            for q in (self.cleaned_data.get("questions_text") or "").splitlines()
            if q.strip()
        ]
        if commit:
            event.save()
        return event
