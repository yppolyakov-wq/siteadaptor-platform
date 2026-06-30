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


def test_localbusiness_ld_schema_type_override():
    # A9: явный тип (AutoRepair) перекрывает вывод из business_type
    t = TenantFactory.build(name="Werkstatt", business_type="other")
    data = json.loads(localbusiness_ld(t, url="https://w.de/", schema_type="AutoRepair"))
    assert data["@type"] == "AutoRepair"


def test_localbusiness_ld_includes_aggregate_rating():
    from decimal import Decimal

    t = TenantFactory.build(name="X", business_type="cafe")
    data = json.loads(
        localbusiness_ld(t, url="https://x.de/", aggregate_rating=(Decimal("4.50"), 12))
    )
    ar = data["aggregateRating"]
    assert ar["@type"] == "AggregateRating"
    assert ar["ratingValue"] == "4.5" and ar["reviewCount"] == 12


def test_localbusiness_ld_skips_rating_when_zero_count():
    t = TenantFactory.build(name="X")
    data = json.loads(localbusiness_ld(t, url="https://x.de/", aggregate_rating=(0, 0)))
    assert "aggregateRating" not in data


def test_localbusiness_ld_includes_opening_hours():
    # A8: opening_hours_structured → schema.org OpeningHoursSpecification (Map Pack/AI).
    t = TenantFactory.build(
        name="X",
        business_type="bakery",
        opening_hours_structured={"0": ["09:00", "18:00"], "5": ["08:00", "13:00"]},
    )
    spec = json.loads(localbusiness_ld(t, url="https://x.de/"))["openingHoursSpecification"]
    assert {
        "@type": "OpeningHoursSpecification",
        "dayOfWeek": "https://schema.org/Monday",
        "opens": "09:00",
        "closes": "18:00",
    } in spec
    assert any(s["dayOfWeek"].endswith("/Saturday") for s in spec)


def test_localbusiness_ld_no_opening_hours_no_spec():
    t = TenantFactory.build(name="X")
    assert "openingHoursSpecification" not in json.loads(localbusiness_ld(t, url="https://x.de/"))


def test_localbusiness_ld_includes_logo_and_sameas():
    # A8: лого → logo + фолбэк image; website_url → sameAs (связь сущностей для Google).
    t = TenantFactory.build(
        name="X", logo_url="https://x.de/logo.png", website_url="https://shop.example.com"
    )
    data = json.loads(localbusiness_ld(t, url="https://x.de/"))
    assert data["logo"] == "https://x.de/logo.png"
    assert data["image"] == "https://x.de/logo.png"  # лого как image, если фото не передано
    assert data["sameAs"] == ["https://shop.example.com"]


def test_localbusiness_ld_explicit_image_beats_logo():
    t = TenantFactory.build(name="X", logo_url="https://x.de/logo.png")
    data = json.loads(localbusiness_ld(t, url="https://x.de/", image="https://x.de/photo.jpg"))
    assert data["image"] == "https://x.de/photo.jpg"  # переданное фото приоритетнее лого
    assert data["logo"] == "https://x.de/logo.png"


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


def test_localbusiness_tag_includes_aggregate_rating():
    from decimal import Decimal

    from django.db import connection

    from apps.aggregator.models import BusinessRating

    BusinessRating.objects.create(
        tenant_schema=connection.schema_name, avg_rating=Decimal("4.50"), review_count=8
    )
    req = RequestFactory().get("/")
    req.tenant = TenantFactory.build(name="Y", business_type="cafe")
    out = Template("{% load seo %}{% localbusiness_jsonld %}").render(Context({"request": req}))
    assert "AggregateRating" in out and '"reviewCount":8' in out


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
