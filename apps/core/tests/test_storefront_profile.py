"""T-8.1a/b: профиль витрины «Nur Aktionen» + карточка «So finden Sie uns».

План: docs/t8-1-aktion-demos-plan-2026-10-09.md §2–§3.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.urls import resolve

from apps.core import business_card, hero_tiles, storefront_profile
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import menu, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

AKTIONEN = {"profile": "aktionen"}


def _request(path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return request


# --- 8.1a: хранение ----------------------------------------------------------


def test_normalize_keeps_known_profile_and_drops_garbage():
    assert siteconfig.normalize(AKTIONEN)["profile"] == "aktionen"
    assert "profile" not in siteconfig.normalize({"profile": "shop"})
    assert "profile" not in siteconfig.normalize({})  # presence-minimal: golden целы


def test_is_aktionen_accepts_tenant_request_and_dict():
    tenant = TenantFactory.build(site_config=dict(AKTIONEN))
    assert storefront_profile.is_aktionen(tenant)
    assert storefront_profile.is_aktionen(_request("/", tenant))
    assert storefront_profile.is_aktionen(AKTIONEN)
    assert not storefront_profile.is_aktionen(TenantFactory.build(site_config={}))
    assert not storefront_profile.is_aktionen(None)


# --- 8.1a: прямые адреса каталога/корзины ------------------------------------


@pytest.mark.parametrize(
    "path", ["/sortiment/", "/sortiment/brot/", "/warenkorb/", "/kombi/", "/speisekarte.pdf"]
)
def test_catalog_and_cart_redirect_home_under_profile(path):
    tenant = TenantFactory(schema_name="public", slug="t81a", site_config=dict(AKTIONEN))
    match = resolve(path, urlconf="config.urls_tenant")
    response = match.func(_request(path, tenant), *match.args, **match.kwargs)
    assert response.status_code == 302 and response["Location"] == "/"


def test_catalog_still_served_without_profile():
    tenant = TenantFactory(schema_name="public", slug="t81b", site_config={}, disabled_modules=[])
    match = resolve("/sortiment/", urlconf="config.urls_tenant")
    response = match.func(_request("/sortiment/", tenant))
    assert response.status_code == 200


# --- 8.1a: входы в каталог ---------------------------------------------------


def _menu_cfg(profile: bool) -> dict:
    cfg = {
        "menus": {
            "top": {
                "items": [
                    {"label": "Sortiment", "type": "archetype", "target": "catalog"},
                    {"label": "Kategorien", "type": "categories", "target": ""},
                    {"label": "Korb", "type": "archetype", "target": "orders"},
                    {"label": "Angebote", "type": "archetype", "target": "promotions"},
                ]
            }
        }
    }
    if profile:
        cfg.update(AKTIONEN)
    return cfg


def test_menu_drops_catalog_and_cart_nodes_under_profile():
    tenant = TenantFactory(schema_name="public", slug="t81c", disabled_modules=[])
    tenant.site_config = _menu_cfg(True)
    labels = [n["label"] for n in menu.resolve_menu(tenant, "top", tenant.site_config)]
    assert labels == ["Angebote"]
    tenant.site_config = _menu_cfg(False)
    labels = [n["label"] for n in menu.resolve_menu(tenant, "top", tenant.site_config)]
    assert "Sortiment" in labels and "Korb" in labels  # без профиля — как было


def test_hero_tiles_skip_catalog_under_profile():
    tenant = TenantFactory(schema_name="public", slug="t81d", disabled_modules=[])
    widget = next(
        key
        for key, spec in hero_tiles.HERO_TILE_SETS.items()
        if any(t.get("url") == "storefront-products" for t in spec)
    )
    before = hero_tiles.tiles_for(widget, tenant)
    tenant.site_config = dict(AKTIONEN)
    after = hero_tiles.tiles_for(widget, tenant)
    assert any("/sortiment/" in t["href"] for t in before)
    assert not any("/sortiment/" in t["href"] for t in after)


def test_bottom_nav_and_search_skip_catalog_under_profile():
    from apps.core.context import _storefront_bottom_nav, modules_nav

    tenant = TenantFactory(
        schema_name="t81e", slug="t81e", disabled_modules=[], site_config=dict(AKTIONEN)
    )
    request = _request("/", tenant)
    urls = [i["url"] for i in _storefront_bottom_nav(request, tenant)]
    assert "/sortiment/" not in urls and "/warenkorb/" not in urls
    assert "/aktionen/" in urls
    ctx = modules_nav(request)
    assert ctx["storefront_search_url"] == "/aktionen/"
    assert ctx["storefront_orders_enabled"] is False and ctx["storefront_quick_add"] is False


def test_home_hides_catalog_sections_under_profile():
    tenant = TenantFactory(schema_name="public", slug="t81f", disabled_modules=[])
    tenant.site_config = {
        **AKTIONEN,
        "sections": [{"key": "products", "enabled": True}, {"key": "promotions", "enabled": True}],
    }
    from apps.catalog.tests.factories import ProductFactory

    ProductFactory(name={"de": "Bauernbrot T81"}, base_price="4.20")
    Promotion.objects.create(title={"de": "Feierabendtüte"}, status="active")
    html = public_views.storefront_home(_request("/", tenant)).content.decode()
    assert 'id="aktionen"' in html and "Feierabendtüte" in html
    assert "Bauernbrot T81" not in html
    # контроль: без профиля та же композиция показывает товар
    tenant.site_config = {k: v for k, v in tenant.site_config.items() if k != "profile"}
    html = public_views.storefront_home(_request("/", tenant)).content.decode()
    assert "Bauernbrot T81" in html


# --- 8.1b: карточка «So finden Sie uns» --------------------------------------


def test_route_url_prefers_coordinates_then_address():
    t = TenantFactory.build(address="Klingenweg 7, 42651 Solingen", latitude=None, longitude=None)
    assert business_card.route_url(t).endswith("Klingenweg%207%2C%2042651%20Solingen")
    t.latitude, t.longitude = "51.1652000", "7.0671000"
    assert business_card.route_url(t).endswith("destination=51.1652000,7.0671000")
    assert business_card.route_url(TenantFactory.build(address="")) == ""


def test_promotion_page_shows_business_card_with_route_and_whatsapp():
    tenant = TenantFactory(
        schema_name="public",
        slug="t81g",
        name="Bäckerei Klingenbrot",
        address="Klingenweg 7, 42651 Solingen",
        whatsapp_number="+49 212 555 0101",
        disabled_modules=[],
    )
    promo = Promotion.objects.create(title={"de": "Feierabendtüte"}, status="active")
    html = public_views.promotion_detail(_request(f"/p/{promo.pk}/", tenant), promo.pk)
    html = html.content.decode()
    assert "data-business-card" in html and "Klingenweg 7, 42651 Solingen" in html
    assert "data-route" in html and "google.com/maps/dir/" in html
    assert "data-whatsapp" in html and "wa.me/492125550101" in html


def test_no_business_card_without_address_and_phone():
    tenant = TenantFactory(schema_name="public", slug="t81h", address="", disabled_modules=[])
    assert business_card.card_context(tenant) is None
    promo = Promotion.objects.create(title={"de": "X"}, status="active")
    html = public_views.promotion_detail(_request(f"/p/{promo.pk}/", tenant), promo.pk)
    assert "data-business-card" not in html.content.decode()
