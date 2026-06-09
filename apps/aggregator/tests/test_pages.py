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


def test_listings_for_filters_city_type_and_active():
    _listing(city="Hilden", business_type="bakery")
    _listing(city="Hilden", business_type="butcher")
    _listing(city="Köln", business_type="bakery")
    _listing(city="Hilden", business_type="bakery", is_active=False)

    assert views.listings_for(city="Hilden").count() == 2  # активные только
    assert views.listings_for(city="Hilden", business_type="bakery").count() == 1
    assert views.listings_for(city="Köln").count() == 1


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_renders_active_only():
    _listing(city="Hilden", title={"de": "AktivesAngebot"})
    _listing(city="Hilden", title={"de": "WegAngebot"}, is_active=False)
    resp = views.city_listing(RequestFactory().get("/entdecken/Hilden/"), "Hilden")
    assert resp.status_code == 200
    assert b"AktivesAngebot" in resp.content
    assert b"WegAngebot" not in resp.content


@override_settings(ROOT_URLCONF="config.urls_public")
def test_city_listing_filters_by_business_type():
    _listing(city="Hilden", business_type="bakery", title={"de": "BakeryOne"})
    _listing(city="Hilden", business_type="butcher", title={"de": "ButcherOne"})
    resp = views.city_listing(RequestFactory().get("/entdecken/Hilden/bakery/"), "Hilden", "bakery")
    assert b"BakeryOne" in resp.content
    assert b"ButcherOne" not in resp.content


@override_settings(ROOT_URLCONF="config.urls_public")
def test_discover_index_lists_cities():
    _listing(city="Hilden")
    _listing(city="Köln")
    resp = views.discover_index(RequestFactory().get("/entdecken/"))
    assert resp.status_code == 200
    assert b"Hilden" in resp.content
    assert "Köln".encode() in resp.content
