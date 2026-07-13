"""Branchen-Landingpages: eine öffentliche Feature-Seite je Archetyp.

`/branchen/<slug>/` beschreibt, was die Plattform für DIESE Branche kann. Inhalt =
generisches Modul-Raster (deterministisch aus `core.modules.REGISTRY`, gegroundet)
+ archetyp-spezifische Highlights (kuratiert, deutsch). Basissprache = Deutsch
(msgid); Übersetzungen en/ru/tr/uk kommen per .po nach (i18n-ready).

Slugs = Tenant.BUSINESS_TYPES ohne "other" (neutraler Typ hat keine eigene Branche).
"""

from django.utils.translation import gettext_lazy as _

from apps.core import modules

# Deutsche Kurznamen der Branche (für Überschriften/Index); Modell-Label ist "Bakery /
# Bäckerei" (zweisprachig) — hier die reine DE-Anzeige.
DISPLAY_NAME = {
    "bakery": _("Bäckereien"),
    "butcher": _("Metzgereien"),
    "grocery": _("Lebensmittelgeschäfte"),
    "clothing": _("Modegeschäfte"),
    "restaurant": _("Restaurants"),
    "cafe": _("Cafés"),
    "retail": _("Einzelhandel"),
    "online_shop": _("Online-Shops"),
    "tour_operator": _("Touren-Anbieter"),
    "hotel": _("Hotels & Pensionen"),
    "friseur": _("Friseursalons"),
    "handwerker": _("Handwerksbetriebe"),
    "werkstatt": _("KFZ-Werkstätten"),
    "events": _("Veranstalter"),
}

# Reihenfolge = Modell-Reihenfolge (ohne "other").
SLUGS = tuple(DISPLAY_NAME.keys())

# Archetyp-spezifische Highlights (kuratiert, gegroundet an echten Features). Wird
# unten von der Recherche gefüllt; leer = Seite zeigt nur das Modul-Raster.
# Form: {slug: {"headline": _, "intro": _, "highlights": [{"icon","title","text"}]}}
CONTENT: dict[str, dict] = {}


def is_valid(slug: str) -> bool:
    return slug in DISPLAY_NAME


def _module_features(slug: str) -> list[dict]:
    """Empfohlene Module dieses Archetyps als Feature-Karten (Icon/Name/Beschreibung)
    — deterministisch aus dem Modul-Register (Quelle der Wahrheit, deutsch)."""
    feats = []
    for m in modules.REGISTRY:
        if m.core:
            continue
        if slug in m.recommended_for:
            feats.append({"icon": m.icon, "label": m.label_de, "desc": m.description_de})
    return feats


def _demo_url(request, slug: str) -> str:
    """Live-Demo-Link des Archetyps (nur wenn geseedet) — Wiederverwendung der
    Onboarding-Logik, damit keine toten Links erscheinen."""
    from . import onboarding

    for card in onboarding.business_type_cards(request):
        if card["value"] == slug:
            return card["demo_url"]
    return ""


def page_context(request, slug: str) -> dict:
    """Voller Kontext der Branchenseite."""
    from django.conf import settings

    from .models import Tenant

    label = dict(Tenant.BUSINESS_TYPES).get(slug, slug)
    content = CONTENT.get(slug, {})
    icon = _meta().get(slug, ("✨", ""))[0]
    langs = [
        {"code": c, "label": c.upper()}
        for c in getattr(settings, "CABINET_LANGUAGES", [settings.LANGUAGE_CODE])
    ]
    return {
        "slug": slug,
        "label": str(label),
        "display_name": DISPLAY_NAME.get(slug, label),
        "icon": icon,
        "headline": content.get("headline"),
        "intro": content.get("intro"),
        "highlights": content.get("highlights", []),
        "features": _module_features(slug),
        "demo_url": _demo_url(request, slug),
        "seo_title": content.get("seo_title"),
        "seo_desc": content.get("seo_desc"),
        "ui_languages": langs,
    }


def index_cards(request) -> list[dict]:
    """Alle Branchen für die Übersicht /branchen/."""
    meta = _meta()
    return [
        {
            "slug": s,
            "icon": meta.get(s, ("✨", ""))[0],
            "name": DISPLAY_NAME[s],
            "blurb": meta.get(s, ("", ""))[1],
        }
        for s in SLUGS
    ]


def _meta() -> dict:
    from .onboarding import BUSINESS_TYPE_META

    return BUSINESS_TYPE_META
