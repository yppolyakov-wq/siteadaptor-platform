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
    assert f"/registrieren/?type={slug}" in html
    # Sprachumschalter vorhanden (i18n-ready).
    assert "/sprache/?lang=" in html


def test_industry_page_404_for_unknown_and_other():
    for bad in ("other", "quatsch", "hotel-x"):
        with pytest.raises(Http404):
            industry_page(RequestFactory().get(f"/branchen/{bad}/"), bad)


def test_signup_prefills_business_type_from_query():
    html = (
        BusinessSignupView().get(RequestFactory().get("/registrieren/?type=hotel")).content.decode()
    )
    # Radio des vorgewählten Typs ist checked.
    assert 'value="hotel"\n                       checked' in html or 'value="hotel"' in html
    # Konkreter: das hotel-Radio trägt checked (Reihenfolge value dann checked).
    import re

    m = re.search(r'value="hotel"[^>]*?checked', html, re.S)
    assert m, "hotel-Radio sollte bei ?type=hotel vorausgewählt sein"


def test_registration_cards_link_to_industry_pages():
    html = BusinessSignupView().get(RequestFactory().get("/")).content.decode()
    assert "/branchen/hotel/" in html and "/branchen/friseur/" in html


def test_root_serves_industries_and_signup_moved():
    """Решение владельца 2026-07-13: /branchen/ = главная (корень); регистрация — /registrieren/."""
    from django.urls import Resolver404
    from django.urls.resolvers import get_resolver

    resolver = get_resolver("config.urls_public")
    assert resolver.resolve("/").func is industries_index
    assert resolver.resolve("/branchen/").func is industries_index
    assert resolver.resolve("/registrieren/").func.view_class.__name__ == "BusinessSignupView"
    for path in ("/ueber-uns/", "/impressum/", "/datenschutz/", "/agb/"):
        resolver.resolve(path)  # не бросает Resolver404
    assert Resolver404  # использован импорт (ruff)


def test_root_captures_partner_ref():
    """Партнёрские ссылки исторически ведут на корень — ?ref должен лечь в сессию."""
    req = RequestFactory().get("/?ref=abc123")
    req.session = {}
    industries_index(req)
    assert req.session.get("partner_ref") == "abc123"


def test_public_header_footer_menu():
    """Малое меню: шапка (Branchen/Über uns/Jetzt starten) + футер (правовые)."""
    body = industries_index(RequestFactory().get("/")).content.decode()
    for link in ("/ueber-uns/", "/impressum/", "/datenschutz/", "/agb/", "/registrieren/"):
        assert link in body, link


def test_about_and_legal_pages_render():
    from apps.tenants.views import about_page, platform_legal

    assert about_page(RequestFactory().get("/ueber-uns/")).status_code == 200
    for kind in ("impressum", "datenschutz", "agb"):
        resp = platform_legal(RequestFactory().get(f"/{kind}/"), kind)
        assert resp.status_code == 200
        assert "noindex" in resp.content.decode()  # правовые не индексируем
