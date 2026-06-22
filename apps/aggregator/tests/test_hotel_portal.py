"""H8a: вертикальный hotel-портал — схлопывание листингов номеров в карточку-отель."""

import types
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.aggregator.portal_views import _collapse_hotels, portal_home

pytestmark = pytest.mark.django_db


def _listing(schema, name, price, kind=AggregatorListing.KIND_STAY, ref="r"):
    return AggregatorListing(
        tenant_schema=schema,
        tenant_slug=schema,
        business_name=name,
        listing_kind=kind,
        source_ref=ref,
        title={"de": f"{name} Zimmer"},
        new_price=Decimal(price) if price is not None else None,
        detail_url=f"https://{schema}.x/unterkunft/{ref}/",
    )


def test_collapse_one_card_per_hotel_cheapest():
    cards = [
        _listing("seeblick", "Pension Seeblick", "89", ref="a"),
        _listing("seeblick", "Pension Seeblick", "69", ref="b"),
        _listing("seeblick", "Pension Seeblick", "149", ref="c"),
        _listing("alpenhof", "Hotel Alpenhof", "120", ref="d"),
    ]
    out = _collapse_hotels(cards)
    assert len(out) == 2  # два отеля
    see = next(c for c in out if c.tenant_schema == "seeblick")
    assert see.room_count == 3
    assert see.new_price == Decimal("69")  # дешевейший номер
    assert see.detail_url.endswith("/unterkunft/b/")
    assert see.title_text == "Pension Seeblick"  # заголовок = отель


def test_collapse_keeps_non_stay_listings():
    cards = [
        _listing("baeck", "Bäckerei", "5", kind=AggregatorListing.KIND_PROMOTION, ref="p"),
        _listing("seeblick", "Pension Seeblick", "89", ref="a"),
    ]
    out = _collapse_hotels(cards)
    assert len(out) == 2
    promo = next(c for c in out if c.listing_kind == AggregatorListing.KIND_PROMOTION)
    assert not hasattr(promo, "room_count")


def test_collapse_preserves_first_appearance_order():
    cards = [
        _listing("alpenhof", "Hotel Alpenhof", "120", ref="d"),
        _listing("seeblick", "Pension Seeblick", "89", ref="a"),
        _listing("alpenhof", "Hotel Alpenhof", "99", ref="e"),
    ]
    out = _collapse_hotels(cards)
    assert [c.tenant_schema for c in out] == ["alpenhof", "seeblick"]


# --- интеграция: рендер вертикального hotel-портала -------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_hotel_portal_renders_one_card_per_hotel():
    cache.clear()
    portal = AggregatorPortal.objects.create(
        host="hotels.siteadaptor.de",
        kind=AggregatorPortal.KIND_VERTICAL,
        business_type="hotel",
        title={"de": "Hotels & Pensionen"},
        is_active=True,
    )
    for ref, price in [("a", "89"), ("b", "69"), ("c", "149")]:
        AggregatorListing.objects.create(
            tenant_schema="seeblick",
            tenant_slug="seeblick",
            business_name="Pension Seeblick",
            business_type="hotel",
            listing_kind=AggregatorListing.KIND_STAY,
            source_ref=ref,
            title={"de": f"Zimmer {ref}"},
            new_price=Decimal(price),
            detail_url=f"https://seeblick.siteadaptor.de/unterkunft/{ref}/",
            is_active=True,
        )
    req = RequestFactory().get("/", HTTP_HOST="hotels.siteadaptor.de")
    req.portal = portal
    req.tenant = types.SimpleNamespace(schema_name="public")
    resp = portal_home(req)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Pension Seeblick" in body
    # схлопнуто в один отель: остаётся дешевейший номер (b), прочие (a/c) убраны
    assert "/unterkunft/b/" in body and "69" in body
    assert "/unterkunft/a/" not in body and "/unterkunft/c/" not in body
