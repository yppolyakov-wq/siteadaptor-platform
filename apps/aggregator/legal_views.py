"""T-8.35: «Rechtliches» городского портала — хаб, Impressum, Datenschutz, Nutzungsbedingungen.

План — docs/t8-35-portal-legal-plan-2026-11-17.md. Тексты — на немецком (обязывающая
версия); реквизиты — только из `portal_operator.info` (админка), пока неполные или не вычитаны
юристом — плашка «Entwurf — nicht rechtsverbindlich». Страницы не индексируются.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from . import portal_operator
from .platform_links import platform_url

PAGES = {
    "hub": "aggregator/legal_hub.html",
    "impressum": "aggregator/legal_impressum.html",
    "datenschutz": "aggregator/legal_datenschutz.html",
    "nutzung": "aggregator/legal_nutzung.html",
}


def _facts() -> dict:
    """Сроки и получатели — из настроек (тексты не расходятся с кодом)."""
    search = getattr(settings, "AGGREGATOR_SEARCH_LOG", {}) or {}
    stats = getattr(settings, "AGGREGATOR_PORTAL_STATS", {}) or {}
    from .models import ListingReport

    return {
        "search_log_days": search.get("retention_days", 180),
        "search_log_days_single": search.get("retention_days_single", 30),
        "stats_days": stats.get("retention_days", 400),
        "map_tiles": "OpenFreeMap" if "openfreemap" in (settings.MAP_STYLE_URL or "") else "",
        "report_auto_hide": ListingReport.AUTO_HIDE_AT,
    }


def legal_page(request, page: str = "hub"):
    portal = getattr(request, "portal", None)
    if portal is None or page not in PAGES:
        raise Http404
    op = portal_operator.info(portal)
    ctx = {
        "portal": portal,
        "op": op,
        "o": op.operator,
        "page": page,
        "robots_noindex": True,
        "facts": _facts(),
        "business_agb_url": platform_url("platform-agb"),
        "is_german": (getattr(request, "LANGUAGE_CODE", "de") or "de").startswith("de"),
    }
    return render(request, PAGES[page], ctx)
