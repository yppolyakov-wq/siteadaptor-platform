"""G8 / G8c: гео — дистанция, разбор координат, «рядом», точки карты, denorm
lat/lng в sync_listing, near-режим выдачи."""

import uuid
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.aggregator import geo, tasks, views
from apps.aggregator.models import AggregatorListing
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _listing(slug, lat, lng, **kw):
    defaults = {
        "tenant_schema": slug,
        "tenant_slug": slug,
        "business_name": "B",
        "business_type": "other",
        "city": "München",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Angebot"},
        "detail_url": f"https://{slug}.siteadaptor.de/p/1/",
        "is_active": True,
        "latitude": lat,
        "longitude": lng,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


# --- чистые хелперы ---------------------------------------------------------------


def test_haversine_known_distance():
    # München ↔ Augsburg ≈ 55–60 км
    km = geo.haversine_km(48.137, 11.575, 48.371, 10.898)
    assert 50 < km < 70


def test_parse_latlng_valid_and_invalid():
    rf = RequestFactory()
    assert geo.parse_latlng(rf.get("/?lat=48.1&lng=11.5")) == (48.1, 11.5)
    assert geo.parse_latlng(rf.get("/")) == (None, None)
    assert geo.parse_latlng(rf.get("/?lat=200&lng=11")) == (None, None)  # вне диапазона
    assert geo.parse_latlng(rf.get("/?lat=x&lng=y")) == (None, None)


# --- nearest / map_points ---------------------------------------------------------


def test_nearest_sorts_and_skips_no_coords():
    _listing("near", Decimal("48.14"), Decimal("11.58"))
    _listing("far", Decimal("52.52"), Decimal("13.40"))  # Berlin
    _listing("noc", None, None)
    result = geo.nearest(AggregatorListing.objects.all(), 48.137, 11.575)
    assert [item.tenant_slug for item in result] == ["near", "far"]  # noc исключён
    assert result[0].distance_km < result[1].distance_km


def test_map_points_only_with_coords():
    _listing("a", Decimal("48.1"), Decimal("11.5"))
    _listing("b", None, None)
    pts = geo.map_points(list(AggregatorListing.objects.all()))
    assert len(pts) == 1 and pts[0]["lat"] == 48.1


# --- denorm в sync ----------------------------------------------------------------


def test_sync_copies_latlng_from_tenant():
    TenantFactory(
        schema_name="public",
        slug="geo-shop",
        latitude=Decimal("48.1372000"),
        longitude=Decimal("11.5755000"),
    )
    promo = Promotion.objects.create(status="active", title={"de": "A"})
    tasks.sync_listing("public", str(promo.id))
    listing = AggregatorListing.objects.get(tenant_schema="public", promo_uuid=promo.id)
    assert listing.latitude == Decimal("48.1372000")
    assert listing.longitude == Decimal("11.5755000")


# --- near-режим выдачи ------------------------------------------------------------


def test_city_listing_near_mode_sorts_and_maps(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    _listing("near", Decimal("48.14"), Decimal("11.58"), title={"de": "NahDran"})
    _listing("far", Decimal("48.40"), Decimal("11.95"), title={"de": "WeitWeg"})
    request = RequestFactory().get("/entdecken/München/?lat=48.137&lng=11.575")
    body = views.city_listing(request, city="München").content.decode()
    assert body.index("NahDran") < body.index("WeitWeg")  # ближний выше
    assert "agg-map" in body  # карта отрисована
