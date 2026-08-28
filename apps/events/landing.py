"""Редактор блоков «богатой страницы» — общий для события и тура (MT-1).

`Event.details` и `Tour.details` — одна и та же схема (`apps/events/details.py`),
поэтому и редактор один: поля формы, заполнение начальных значений и сборка
нормализованного словаря живут здесь, а формы просто подмешивают их.

Поля добавляются в `__init__` формы (`fields.update`), а не объявляются в классе:
для ModelForm объявленные поля и так рендерятся ПОСЛЕ модельных, а блоки лендинга
идут последними — порядок формы события остаётся прежним.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from . import details as details_mod

# form-field → (details-key, record-keys | None). None = простой список строк.
LIST_FIELDS = {
    "for_whom_text": ("for_whom", None),
    "accommodation_text": ("accommodation", None),
    "price_includes_text": ("price_includes", None),
    "price_excludes_text": ("price_excludes", None),
    "bring_text": ("bring", None),
    "includes_text": ("includes", ("title", "text")),
    "hosts_text": ("hosts", ("name", "role", "photo")),
    "faq_text": ("faq", ("q", "a")),
    "testimonials_text": ("testimonials", ("name", "city", "text", "photo", "rating")),
    "before_after_text": ("before_after", ("before", "after", "text")),
    "certifications_text": ("certifications", ("name", "issuer", "icon")),
}
SCALAR_FIELDS = ("promise", "idea", "venue", "food", "price_note")


def _ta(rows=3, ph=""):
    return forms.Textarea(attrs={"rows": rows, "placeholder": ph})


def form_fields() -> dict:
    """Свежий набор полей редактора (по экземпляру на форму — поля stateful)."""
    return {
        "promise": forms.CharField(required=False, label=_("Kurzversprechen (Hero)")),
        "for_whom_text": forms.CharField(
            required=False, widget=_ta(4), label=_("Für wen (eine Zeile pro Punkt)")
        ),
        "idea": forms.CharField(required=False, widget=_ta(3), label=_("Idee / Atmosphäre")),
        "includes_text": forms.CharField(
            required=False,
            widget=_ta(5, _("Yoga | Sanfte Praxis morgens & abends")),
            label=_("Was ist dabei (Titel | Text)"),
        ),
        "venue": forms.CharField(required=False, widget=_ta(3), label=_("Ort / Veranstaltungsort")),
        "accommodation_text": forms.CharField(
            required=False, widget=_ta(4), label=_("Unterkunft (eine Zeile pro Punkt)")
        ),
        "food": forms.CharField(required=False, widget=_ta(3), label=_("Verpflegung")),
        "hosts_text": forms.CharField(
            required=False,
            widget=_ta(3, "Mara Lind | Yogalehrerin | https://…/foto.jpg"),
            label=_("Leitung (Name | Rolle | Foto-URL)"),
        ),
        "price_includes_text": forms.CharField(
            required=False, widget=_ta(4), label=_("Im Preis enthalten (eine Zeile pro Punkt)")
        ),
        "price_excludes_text": forms.CharField(
            required=False, widget=_ta(3), label=_("Nicht enthalten (eine Zeile pro Punkt)")
        ),
        "price_note": forms.CharField(
            required=False, label=_("Preis-Hinweis (Frühbucher, Varianten …)")
        ),
        "bring_text": forms.CharField(
            required=False, widget=_ta(4), label=_("Mitbringen (eine Zeile pro Punkt)")
        ),
        "faq_text": forms.CharField(
            required=False,
            widget=_ta(5, _("Für Anfänger geeignet? | Ja, alle Level willkommen.")),
            label=_("FAQ (Frage | Antwort)"),
        ),
        "testimonials_text": forms.CharField(
            required=False,
            widget=_ta(4, "Johanna | Köln | Hat mich geerdet. | https://…/foto.jpg | 5"),
            label=_("Stimmen (Name | Stadt | Text | Foto-URL | Sterne 1–5)"),
        ),
        "before_after_text": forms.CharField(
            required=False,
            widget=_ta(3, "https://…/vorher.jpg | https://…/nachher.jpg | 3 Tage Detox"),
            label=_("Vorher/Nachher (Vorher-URL | Nachher-URL | Text)"),
        ),
        "certifications_text": forms.CharField(
            required=False,
            widget=_ta(3, "Yoga Alliance RYT-500 | Yoga Alliance | https://…/logo.svg"),
            label=_("Zertifikate / Auszeichnungen (Name | Aussteller | Logo-URL)"),
        ),
    }


def fill_initial(form, landing: dict) -> None:
    """Проставить начальные значения полей из нормализованных блоков."""
    for key in SCALAR_FIELDS:
        form.fields[key].initial = landing.get(key, "")
    for fname, (key, rec) in LIST_FIELDS.items():
        form.fields[fname].initial = (
            details_mod.records_to_text(landing.get(key), rec)
            if rec
            else details_mod.list_to_text(landing.get(key))
        )


def collect(cleaned_data: dict) -> dict:
    """Собрать нормализованный `details` из очищенных данных формы."""
    raw = {key: cleaned_data.get(key, "") for key in SCALAR_FIELDS}
    for fname, (key, _rec) in LIST_FIELDS.items():
        raw[key] = (cleaned_data.get(fname) or "").splitlines()
    return details_mod.normalize(raw)
