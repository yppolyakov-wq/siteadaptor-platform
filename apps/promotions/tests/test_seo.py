"""Track B5: schema.org JSON-LD + sitemap/robots для локального SEO витрины."""

import json

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.core.seo import localbusiness_ld, offer_ld
from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


# --- LocalBusiness ------------------------------------------------------------


def test_localbusiness_ld_maps_type_and_address():
    t = TenantFactory.build(
        name="Bäckerei Müller",
        business_type="bakery",
        city="Köln",
        country="DE",
        address="Hauptstr. 1",
    )
    data = json.loads(localbusiness_ld(t, url="https://m.example.com/"))
    assert data["@type"] == "Bakery"
    assert data["name"] == "Bäckerei Müller"
    assert data["url"] == "https://m.example.com/"
    assert data["address"]["addressLocality"] == "Köln"
    assert data["address"]["addressCountry"] == "DE"


def test_localbusiness_ld_unknown_type_falls_back():
    t = TenantFactory.build(name="X", business_type="other")
    assert json.loads(localbusiness_ld(t, url="https://x.de/"))["@type"] == "LocalBusiness"


def test_localbusiness_ld_none_is_empty():
    assert localbusiness_ld(None, url="https://x.de/") == ""


# --- Offer / Product ----------------------------------------------------------


def test_offer_ld_has_offer_with_price_and_instock():
    promo = PromotionFactory(
        title={"de": "Brötchen", "en": "Roll"},
        promo_type="discount",
        price_override="1.50",
        available_quantity=5,
    )
    data = json.loads(offer_ld(promo, url="https://x.de/p/1/", image_url="https://x.de/i.jpg"))
    assert data["@type"] == "Product"
    assert data["name"] == "Brötchen"
    assert data["image"] == "https://x.de/i.jpg"
    assert data["offers"]["price"] == "1.50"
    assert data["offers"]["priceCurrency"] == "EUR"
    assert data["offers"]["availability"].endswith("/InStock")


def test_offer_ld_sold_out_availability():
    promo = PromotionFactory(promo_type="discount", price_override="2.00", available_quantity=0)
    data = json.loads(offer_ld(promo, url="https://x.de/p/1/"))
    assert data["offers"]["availability"].endswith("/SoldOut")


# --- template tag -------------------------------------------------------------


def test_localbusiness_tag_renders_script():
    req = RequestFactory().get("/")
    req.tenant = TenantFactory.build(name="Bäckerei Müller", business_type="bakery")
    out = Template("{% load seo %}{% localbusiness_jsonld %}").render(Context({"request": req}))
    assert 'type="application/ld+json"' in out
    assert "Bäckerei Müller" in out
    assert '"@type":"Bakery"' in out


def test_localbusiness_tag_without_tenant_is_blank():
    out = Template("{% load seo %}{% localbusiness_jsonld %}").render(
        Context({"request": RequestFactory().get("/")})
    )
    assert out.strip() == ""


# --- sitemap / robots ---------------------------------------------------------


def test_sitemap_lists_home_and_active_promos_only():
    PromotionFactory(status="active")
    PromotionFactory(status="draft")  # не активная — в sitemap не попадает
    resp = public_views.sitemap_xml(RequestFactory().get("/sitemap.xml"))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    body = resp.content.decode()
    assert body.startswith("<?xml")
    assert "<urlset" in body
    assert body.count("<url>") == 2  # главная + одна активная акция


def test_robots_points_to_sitemap():
    body = public_views.robots_txt(RequestFactory().get("/robots.txt")).content.decode()
    assert "User-agent: *" in body
    assert "Sitemap:" in body
    assert "sitemap.xml" in body
