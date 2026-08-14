"""Форма события для кабинета (A6b). Цена — в евро (→ cents), анкета — построчно.

Развёрнутый «ретрит-лендинг» (Event.details) редактируется построчно: списки —
одна позиция на строку; карточки/отзывы/ведущие — «A | B [| C]» на строку.
"""

from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from . import details as details_mod
from . import landing, registration, taxonomy
from .models import Event, Teacher, Tour


def _ta(rows=3, ph=""):
    return forms.Textarea(attrs={"rows": rows, "placeholder": ph})


class EventForm(forms.ModelForm):
    price_eur = forms.DecimalField(
        min_value=0, max_digits=8, decimal_places=2, required=False, label=_("Preis je Platz (€)")
    )
    questions_text = forms.CharField(
        required=False, widget=_ta(3), label=_("Anmelde-Fragen (eine pro Zeile)")
    )
    program_text = forms.CharField(
        required=False, widget=_ta(4), label=_("Ablauf / Programm (ein Punkt pro Zeile)")
    )
    tiers_text = forms.CharField(
        required=False,
        widget=_ta(3, "Frühbucher | 79 | 10\nStandard | 99\nKind | 0"),
        label=(
            _(
                "Preiskategorien (Label | Preis € | Kontingent, eine pro Zeile; "
                "Kontingent optional, leer = einheitlicher Preis)"
            )
        ),
    )
    # R2: таксономия (направление/уровень/язык) — для каталога и фильтров.
    category = forms.ChoiceField(
        required=False, choices=[("", "—")] + taxonomy.CATEGORIES, label=_("Richtung / Thema")
    )
    level = forms.ChoiceField(
        required=False, choices=[("", "—")] + taxonomy.LEVELS, label=_("Level")
    )
    language = forms.ChoiceField(
        required=False, choices=[("", "—")] + taxonomy.LANGUAGES, label=_("Sprache")
    )
    # R4: онлайн-предоплата %, 0 = полная оплата (1..99 = депозит, остаток на месте).
    deposit_percent = forms.IntegerField(
        required=False, min_value=0, max_value=100, label=_("Anzahlung online (%, 0 = voll)")
    )
    # R1: какие пресет-поля анкеты показывать на витрине (страна/ДР/питание…).
    registration_fields = forms.MultipleChoiceField(
        required=False,
        choices=registration.choices,
        widget=forms.CheckboxSelectMultiple,
        label=_("Anmelde-Felder (Vorlagen — zusätzlich zu freien Fragen)"),
    )

    class Meta:
        model = Event
        fields = (
            "title",
            # MT-1: событие как заезд тур-продукта (пусто = самостоятельное событие).
            "tour",
            "description",
            "location",
            "city",
            "latitude",
            "longitude",
            "is_online",  # RT2: онлайн/Zoom-событие
            "online_url",
            "starts_at",
            "ends_at",
            "capacity",
            "require_manual_confirm",
            "offers_accommodation",
            "accommodation_units",
            "teachers",
            "waiver_required",
            "waiver_text",
            "cancellation",
            "free_cancel_days",
        )
        labels = {
            "cancellation": "Stornierung",
            "free_cancel_days": "Kostenlose Stornierung bis (Tage vor Beginn)",
            "tour": _("Gehört zur Reise (optional)"),
        }
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "waiver_text": forms.Textarea(attrs={"rows": 4, "placeholder": "leer = Standardtext"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Блоки богатой страницы — общий редактор с туром (apps/events/landing.py).
        self.fields.update(landing.form_fields())
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        # R5: выбор типов номеров для проживания — только активные юниты stays.
        from apps.stays.models import StayUnit

        self.fields["accommodation_units"].queryset = StayUnit.objects.filter(is_active=True)
        self.fields["accommodation_units"].required = False
        # R3: ведущие — только активные.
        self.fields["teachers"].queryset = Teacher.objects.filter(is_active=True)
        self.fields["teachers"].required = False
        # R12: политика отмены — необязательна в форме (фолбэк на дефолт модели).
        self.fields["cancellation"].required = False
        self.fields["free_cancel_days"].required = False
        if self.instance and self.instance.pk:
            self.fields["price_eur"].initial = self.instance.price_eur
            self.fields["questions_text"].initial = "\n".join(self.instance.questions or [])
            self.fields["program_text"].initial = "\n".join(self.instance.program or [])
            self.fields["tiers_text"].initial = details_mod.tiers_to_text(self.instance.tiers)
            self.fields["registration_fields"].initial = self.instance.registration_fields or []
            for f in ("category", "level", "language"):
                self.fields[f].initial = getattr(self.instance, f, "")
            self.fields["deposit_percent"].initial = self.instance.deposit_percent
            landing.fill_initial(self, self.instance.landing)

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
        event.details = landing.collect(self.cleaned_data)
        event.tiers = details_mod.normalize_tiers(
            (self.cleaned_data.get("tiers_text") or "").splitlines()
        )
        # сохраняем включённые пресет-поля в порядке каталога (стабильно)
        chosen = set(self.cleaned_data.get("registration_fields") or [])
        event.registration_fields = [k for k in registration.VALID_KEYS if k in chosen]
        # R2 таксономия (explicit-поля, не в Meta.fields → присваиваем вручную)
        event.category = self.cleaned_data.get("category") or ""
        event.level = self.cleaned_data.get("level") or ""
        event.language = self.cleaned_data.get("language") or ""
        event.deposit_percent = self.cleaned_data.get("deposit_percent") or 0
        if commit:
            event.save()
            self.save_m2m()  # R5/R3: accommodation_units + teachers (M2M)
        return event

    def clean_cancellation(self):
        # R12: пусто → дефолт модели (flexible), чтобы поле было необязательным.
        return self.cleaned_data.get("cancellation") or Event.CANCEL_FLEXIBLE

    def clean_free_cancel_days(self):
        return self.cleaned_data.get("free_cancel_days") or 0


class TourForm(forms.ModelForm):
    """MT-1: форма тур-продукта. Блоки богатой страницы — тот же редактор, что
    у события (apps/events/landing.py); маршрут редактируется отдельно (строки
    таблицы, парсит `itinerary.from_post`)."""

    class Meta:
        model = Tour
        fields = (
            "title",
            "summary",
            "description",
            "country",
            "region",
            "difficulty",
            "duration_days",
            "distance_km",
            "teachers",
            "is_published",
            "sort_order",
        )
        labels = {
            "title": _("Titel"),
            "summary": _("Kurzbeschreibung (Karte)"),
            "description": _("Beschreibung"),
            "country": _("Land (gruppiert die Reise-Übersicht)"),
            "region": _("Region (z. B. Himalaya, Indien)"),
            "difficulty": _("Schwierigkeit"),
            "duration_days": _("Dauer (Tage, 0 = ausblenden)"),
            "distance_km": _("Distanz (km, 0 = ausblenden)"),
            "teachers": _("Guides"),
            "is_published": _("Veröffentlicht"),
            "sort_order": _("Sortierung"),
        }
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(landing.form_fields())
        self.fields["teachers"].queryset = Teacher.objects.filter(is_active=True)
        self.fields["teachers"].required = False
        if self.instance and self.instance.pk:
            landing.fill_initial(self, self.instance.landing)

    # Числовые «шапки» необязательны: пустое поле = 0, а не ошибка формы
    # (иначе пустая «Дистанция» роняла бы сохранение описания целиком).
    def clean_duration_days(self):
        return self.cleaned_data.get("duration_days") or 0

    def clean_distance_km(self):
        return self.cleaned_data.get("distance_km") or 0

    def clean_sort_order(self):
        return self.cleaned_data.get("sort_order") or 0

    def save(self, commit=True):
        tour = super().save(commit=False)
        tour.details = landing.collect(self.cleaned_data)
        if not tour.slug:
            tour.slug = unique_tour_slug(tour.title)
        if commit:
            tour.save()
            self.save_m2m()
        return tour


def unique_tour_slug(title: str, *, exclude_pk=None) -> str:
    """Свободный slug из заголовка (как у записей блога): «tour», «tour-2», …"""
    base = slugify(title or "")[:200] or "tour"
    qs = Tour.objects.exclude(pk=exclude_pk) if exclude_pk else Tour.objects.all()
    slug, n = base, 1
    while qs.filter(slug=slug).exists():
        n += 1
        slug = f"{base[:196]}-{n}"
    return slug


class TeacherForm(forms.ModelForm):
    """R3: кабинетная форма преподавателя/ведущего."""

    class Meta:
        model = Teacher
        fields = ("name", "title", "bio", "photo_url", "website", "instagram", "is_active")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}
