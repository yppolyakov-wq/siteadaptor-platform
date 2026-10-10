"""T-8.5 «Aktion in 3 Klicks»: форма страницы ``/aktion-starten/`` и генерация поддомена.

План — docs/t8-5-quick-start-plan-2026-10-10.md. Поля акции — те же, что у ассистента
T-8.4 (форма наследуется: правила цены и срока одни), плюс «Wer sind Sie?»: название,
тип, район, e-mail. Пароля и поддомена нет — поддомен выводится из названия.
"""

from __future__ import annotations

import re

from django import forms
from django.core import signing
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.promotions import quick
from apps.promotions import response as promo_response

from .forms import _RESERVED_SLUGS
from .models import Tenant

DEFAULT_CITY = "Solingen"  # Р-6: пилот — весь Solingen
SLUG_MAX = 40
MIN_FILL_SECONDS = 3  # ловушка времени: живой человек не заполнит форму быстрее
FORM_STAMP_SALT = "t85-form"

# Типы для карточек «Wer sind Sie?» — локальные бизнесы лёгкой ступени (остальные
# доступны обычной регистрацией).
QUICK_TYPES = (
    "bakery",
    "butcher",
    "grocery",
    "cafe",
    "restaurant",
    "clothing",
    "retail",
    "friseur",
    "hotel",
    "other",
)

# Отклики без модулей заказов/заявок — то, что лёгкая витрина умеет сразу.
QUICK_RESPONSES = (promo_response.RESERVE, promo_response.COUPON, promo_response.SHOW)

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


SLUG_MIN = 3
# Заняты собственными путями страницы /aktion-starten/<…>/.
_QUICK_RESERVED = {"adresse"}
# Поддомен = имя схемы Postgres (дефисы → подчёркивания): начинается с буквы.
_SLUG_SHAPE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


def domain_base() -> str:
    """Хост платформы без порта: «siteadaptor.de»."""
    from django.conf import settings

    return getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]


def _host(slug: str) -> str:
    return f"{slug}.{domain_base()}"


def _slug_taken(slug: str) -> bool:
    from .models import Domain

    return (
        slug in _RESERVED_SLUGS
        or slug in _QUICK_RESERVED
        or Tenant.objects.filter(slug=slug).exists()
        or Tenant.objects.filter(schema_name=slug.replace("-", "_")).exists()
        # Порталы городов и демо живут на своих Domain без тенанта-однофамильца.
        or Domain.objects.filter(domain=_host(slug)).exists()
    )


def normalize_slug(text: str) -> str:
    """Что человек ввёл → вид поддомена: «Bäckerei Müller» → baeckerei-mueller."""
    base = slugify((text or "").lower().translate(_UMLAUTS))
    return re.sub(r"-{2,}", "-", base)[:SLUG_MAX].strip("-")


def slug_problem(slug: str) -> str:
    """Почему поддомен нельзя взять ("" — можно)."""
    if len(slug) < SLUG_MIN:
        return str(_("Mindestens %(n)s Zeichen.") % {"n": SLUG_MIN})
    if not _SLUG_SHAPE.match(slug):
        return str(_("Bitte mit einem Buchstaben beginnen; nur a–z, 0–9 und Bindestriche."))
    if _slug_taken(slug):
        return str(_("Diese Adresse ist schon vergeben."))
    return ""


def suggest_slug(name: str) -> str:
    """Свободный поддомен из названия: «Bäckerei Müller & Söhne» → baeckerei-mueller-soehne."""
    base = normalize_slug(name)
    if len(base) < SLUG_MIN or not base[0].isalpha():
        base = f"aktion-{base}".strip("-")[:SLUG_MAX]
    candidate, n = base, 1
    while _slug_taken(candidate):
        n += 1
        suffix = f"-{n}"
        candidate = f"{base[: SLUG_MAX - len(suffix)].rstrip('-')}{suffix}"
    return candidate


def form_stamp() -> str:
    return signing.dumps(timezone.now().timestamp(), salt=FORM_STAMP_SALT)


def too_fast(stamp: str) -> bool:
    """True — форма отправлена быстрее, чем её может заполнить человек (или без метки)."""
    try:
        started = float(signing.loads(stamp or "", salt=FORM_STAMP_SALT, max_age=24 * 3600))
    except (signing.BadSignature, TypeError, ValueError):
        return True
    return timezone.now().timestamp() - started < MIN_FILL_SECONDS


def type_cards(request=None) -> list[dict]:
    from . import onboarding

    by_value = {c["value"]: c for c in onboarding.business_type_cards(request)}
    return [by_value[v] for v in QUICK_TYPES if v in by_value]


class QuickStartForm(quick.QuickPromotionForm):
    """Экран 1 — акция (поля ассистента T-8.4), экран 2 — бизнес."""

    business_name = forms.CharField(label=_("Name Ihres Geschäfts"), max_length=200)
    business_type = forms.ChoiceField(
        label=_("Art des Geschäfts"), choices=(), widget=forms.RadioSelect
    )
    subdomain = forms.CharField(label=_("Ihre Adresse"), required=False, max_length=80)
    district = forms.ChoiceField(label=_("Stadtteil"), required=False, choices=())
    email = forms.EmailField(label=_("E-Mail"))

    def __init__(self, *args, **kwargs):
        kwargs.pop("tenant", None)
        super().__init__(*args, tenant=None, **kwargs)
        labels = dict(promo_response.CHOICES)
        self.response_options = [(k, labels[k], quick.RESPONSE_HINTS[k]) for k in QUICK_RESPONSES]
        self.fields["customer_response"].choices = [(k, labels[k]) for k in QUICK_RESPONSES]
        self.fields["customer_response"].initial = promo_response.RESERVE
        type_labels = dict(Tenant.BUSINESS_TYPES)
        self.fields["business_type"].choices = [(v, type_labels[v]) for v in QUICK_TYPES]
        from apps.core import districts

        self.fields["district"].choices = [("", _("— bitte wählen —"))] + districts.choices_for(
            DEFAULT_CITY
        )

    def clean_subdomain(self):
        """Пусто — выберем сами из названия; иначе — ровно то, что хочет владелец."""
        slug = normalize_slug(self.cleaned_data.get("subdomain") or "")
        if not slug:
            return ""
        problem = slug_problem(slug)
        if problem:
            raise forms.ValidationError(problem)
        return slug

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def promo_payload(self) -> dict:
        """Данные акции для фоновой задачи: те же ключи, что у формы ассистента."""
        d = self.cleaned_data
        payload = {
            "title": d["title"],
            "description": d.get("description") or "",
            "term": d["term"],
            "customer_response": d["customer_response"],
        }
        for key in ("new_price", "old_price"):
            if d.get(key) is not None:
                payload[key] = str(d[key])
        if d.get("percent"):
            payload["percent"] = str(d["percent"])
        if d.get("until"):
            payload["until"] = d["until"].isoformat()
        return payload
