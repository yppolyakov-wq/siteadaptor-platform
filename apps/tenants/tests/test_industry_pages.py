"""Branchen-Landingpages (/branchen/ + /branchen/<slug>/)."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.tenants import archetype_pages
from apps.tenants.views import BusinessSignupView, industries_index, industry_page


def test_industries_index_lists_all_archetypes():
    body = industries_index(RequestFactory().get("/branchen/")).content.decode()
    for slug in archetype_pages.SLUGS:
        assert f"/branchen/{slug}/" in body  # Karte verlinkt jede Branche
    assert "other" not in [s for s in archetype_pages.SLUGS]  # neutraler Typ ausgeschlossen
    assert len(archetype_pages.SLUGS) == 14


@pytest.mark.parametrize("slug", archetype_pages.SLUGS)
def test_industry_page_renders_for_each_archetype(slug):
    resp = industry_page(RequestFactory().get(f"/branchen/{slug}/"), slug)
    assert resp.status_code == 200
    html = resp.content.decode()
    # Modul-Raster ist immer da (deterministisch aus dem Register).
    assert archetype_pages._module_features(slug)  # es gibt empfohlene Module
    # CTA führt in die Registrierung mit vorgewähltem Typ.
    assert f"/?type={slug}" in html
    # Sprachumschalter vorhanden (i18n-ready).
    assert "/sprache/?lang=" in html


def test_industry_page_404_for_unknown_and_other():
    for bad in ("other", "quatsch", "hotel-x"):
        with pytest.raises(Http404):
            industry_page(RequestFactory().get(f"/branchen/{bad}/"), bad)


def test_signup_prefills_business_type_from_query():
    html = BusinessSignupView().get(RequestFactory().get("/?type=hotel")).content.decode()
    # Radio des vorgewählten Typs ist checked.
    assert 'value="hotel"\n                       checked' in html or 'value="hotel"' in html
    # Konkreter: das hotel-Radio trägt checked (Reihenfolge value dann checked).
    import re

    m = re.search(r'value="hotel"[^>]*?checked', html, re.S)
    assert m, "hotel-Radio sollte bei ?type=hotel vorausgewählt sein"


def test_registration_cards_link_to_industry_pages():
    html = BusinessSignupView().get(RequestFactory().get("/")).content.decode()
    assert "/branchen/hotel/" in html and "/branchen/friseur/" in html
