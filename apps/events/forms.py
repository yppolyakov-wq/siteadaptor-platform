"""Форма события для кабинета (A6b). Цена — в евро (→ cents), анкета — построчно.

Развёрнутый «ретрит-лендинг» (Event.details) редактируется построчно: списки —
одна позиция на строку; карточки/отзывы/ведущие — «A | B [| C]» на строку.
"""

from decimal import Decimal, InvalidOperation

from django import forms

from . import details as details_mod
from . import registration
from .models import Event


def _ta(rows=3, ph=""):
    return forms.Textarea(attrs={"rows": rows, "placeholder": ph})


class EventForm(forms.ModelForm):
    price_eur = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2, required=False, label="Preis je Platz (€)"
    )
    questions_text = forms.CharField(
        required=False, widget=_ta(3), label="Anmelde-Fragen (eine pro Zeile)"
    )
    program_text = forms.CharField(
        required=False, widget=_ta(4), label="Ablauf / Programm (ein Punkt pro Zeile)"
    )
    tiers_text = forms.CharField(
        required=False,
        widget=_ta(3, "Frühbucher | 79\nStandard | 99\nKind | 0"),
        label="Preiskategorien (Label | Preis €, eine pro Zeile; leer = einheitlicher Preis)",
    )
    # R1: какие пресет-поля анкеты показывать на витрине (страна/ДР/питание…).
    registration_fields = forms.MultipleChoiceField(
        required=False,
        choices=registration.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Anmelde-Felder (Vorlagen — zusätzlich zu freien Fragen)",
    )
    # --- Retreat-Landing (alles optional) ---------------------------------
    promise = forms.CharField(required=False, label="Kurzversprechen (Hero)")
    for_whom_text = forms.CharField(
        required=False, widget=_ta(4), label="Für wen (eine Zeile pro Punkt)"
    )
    idea = forms.CharField(required=False, widget=_ta(3), label="Idee / Atmosphäre")
    includes_text = forms.CharField(
        required=False,
        widget=_ta(5, "Yoga | Sanfte Praxis morgens & abends"),
        label="Was ist dabei (Titel | Text)",
    )
    venue = forms.CharField(required=False, widget=_ta(3), label="Ort / Veranstaltungsort")
    accommodation_text = forms.CharField(
        required=False, widget=_ta(4), label="Unterkunft (eine Zeile pro Punkt)"
    )
    food = forms.CharField(required=False, widget=_ta(3), label="Verpflegung")
    hosts_text = forms.CharField(
        required=False,
        widget=_ta(3, "Mara Lind | Yogalehrerin | https://…/foto.jpg"),
        label="Leitung (Name | Rolle | Foto-URL)",
    )
    price_includes_text = forms.CharField(
        required=False, widget=_ta(4), label="Im Preis enthalten (eine Zeile pro Punkt)"
    )
    price_excludes_text = forms.CharField(
        required=False, widget=_ta(3), label="Nicht enthalten (eine Zeile pro Punkt)"
    )
    price_note = forms.CharField(required=False, label="Preis-Hinweis (Frühbucher, Varianten …)")
    bring_text = forms.CharField(
        required=False, widget=_ta(4), label="Mitbringen (eine Zeile pro Punkt)"
    )
    faq_text = forms.CharField(
        required=False,
        widget=_ta(5, "Für Anfänger geeignet? | Ja, alle Level willkommen."),
        label="FAQ (Frage | Antwort)",
    )
    testimonials_text = forms.CharField(
        required=False,
        widget=_ta(4, "Johanna | Köln | Hat mich geerdet."),
        label="Stimmen (Name | Stadt | Text)",
    )

    # form-field → (details-key, record-keys|None)
    _LIST_FIELDS = {
        "for_whom_text": ("for_whom", None),
        "accommodation_text": ("accommodation", None),
        "price_includes_text": ("price_includes", None),
        "price_excludes_text": ("price_excludes", None),
        "bring_text": ("bring", None),
        "includes_text": ("includes", ("title", "text")),
        "hosts_text": ("hosts", ("name", "role", "photo")),
        "faq_text": ("faq", ("q", "a")),
        "testimonials_text": ("testimonials", ("name", "city", "text")),
    }
    _SCALAR_FIELDS = ("promise", "idea", "venue", "food", "price_note")

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
            self.fields["program_text"].initial = "\n".join(self.instance.program or [])
            self.fields["tiers_text"].initial = details_mod.tiers_to_text(self.instance.tiers)
            self.fields["registration_fields"].initial = self.instance.registration_fields or []
            d = self.instance.landing
            for key in self._SCALAR_FIELDS:
                self.fields[key].initial = d.get(key, "")
            for fname, (key, rec) in self._LIST_FIELDS.items():
                self.fields[fname].initial = (
                    details_mod.records_to_text(d.get(key), rec)
                    if rec
                    else details_mod.list_to_text(d.get(key))
                )

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
        event.program = [
            p.strip()
            for p in (self.cleaned_data.get("program_text") or "").splitlines()
            if p.strip()
        ]
        raw = {key: self.cleaned_data.get(key, "") for key in self._SCALAR_FIELDS}
        for fname, (key, _rec) in self._LIST_FIELDS.items():
            raw[key] = (self.cleaned_data.get(fname) or "").splitlines()
        event.details = details_mod.normalize(raw)
        event.tiers = details_mod.normalize_tiers(
            (self.cleaned_data.get("tiers_text") or "").splitlines()
        )
        # сохраняем включённые пресет-поля в порядке каталога (стабильно)
        chosen = set(self.cleaned_data.get("registration_fields") or [])
        event.registration_fields = [k for k in registration.VALID_KEYS if k in chosen]
        if commit:
            event.save()
        return event
