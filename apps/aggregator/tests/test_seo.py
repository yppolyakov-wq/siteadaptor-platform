"""Track B5b: sitemap/robots агрегатора + ItemList JSON-LD на городской странице."""

import uuid

import pytest
from django.test import RequestFactory, override_settings

from apps.aggregator import views
from apps.aggregator.models import AggregatorListing

pytestmark = pytest.mark.django_db


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Hilden",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot -20%"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


@override_settings(ROOT_URLCONF="config.urls_public")
def test_sitemap_has_index_cities_and_types():
    _listing(city="Hilden", business_type="bakery")
    _listing(city="Köln", business_type="butcher")
    _listing(city="Hilden", business_type="bakery", is_active=False)  # неактивные — мимо
    resp = views.sitemap_xml(RequestFactory().get("/sitemap.xml"))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    body = resp.content.decode()
    assert body.startswith("<?xml")
    assert "/entdecken/Hilden/" in body
    assert "/entdecken/Hilden/bakery/" in body
    # index + 2 города + 2 (город,тип) = 5
    assert body.count("<url>") == 5


@override_settings(ROOT_URLCONF="config.urls_public")
def test_sitemap_excludes_inactive():
    _listing(city="Hilden", is_active=True)
    _listing(city="GhostCity", is_active=False)
    body = views.sitemap_xml(RequestFactory().get("/sitemap.xml")).content.decode()
    assert "GhostCity" not in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_robots_points_to_sitemap():
    body = views.robots_txt(RequestFactory().get("/robots.txt")).content.decode()
    assert "User-agent: *" in body
    assert "Sitemap:" in body
    assert "sitemap.xml" in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_emits_itemlist_jsonld():
    _listing(city="Hilden", title={"de": "AktivesAngebot"})
    body = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden").content.decode()
    assert 'type="application/ld+json"' in body
    assert '"@type":"ItemList"' in body
    assert "AktivesAngebot" in body


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_sort_by_name_orders_az():
    """A8: ?sort=name сортирует выдачу по business_name A–Z; select отражает выбор."""
    _listing(city="Hilden", business_name="Zeta Bäckerei", tenant_schema="tz", title={"de": "Z"})
    _listing(city="Hilden", business_name="Alpha Bistro", tenant_schema="ta", title={"de": "A"})
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?sort=name"), "Hilden"
    ).content.decode()
    assert body.index("Alpha Bistro") < body.index("Zeta Bäckerei")  # A–Z
    assert 'value="name" selected' in body  # дропдаун отражает выбор


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_default_sort_is_newest():
    """A8: дефолт — neueste (выбран в select), невалидный sort игнорируется."""
    _listing(city="Hilden", business_name="Eins")
    body = views.city_listing(
        RequestFactory().get("/entdecken/Hilden/?sort=bogus"), "Hilden"
    ).content.decode()
    assert 'value="neueste" selected' in body
