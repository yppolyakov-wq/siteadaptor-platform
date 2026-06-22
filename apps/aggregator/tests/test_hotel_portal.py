"""H8a/H8b: вертикальный hotel-портал — схлопывание номеров + поиск по датам."""

import types
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import hotel_search
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.aggregator.portal_views import _collapse_hotels, portal_home
from apps.stays import services
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 12, 1)


def _su(**kwargs):
    kwargs.setdefault("price_cents", 9000)
    kwargs.setdefault("max_guests", 2)
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", **kwargs)


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


# --- H8b: живой поиск по датам ----------------------------------------------------


def test_availability_cheapest_free_room():
    cache.clear()
    _su(price_cents=12000)
    _su(price_cents=8000)  # дешевле
    ok, cents = hotel_search.hotel_availability("public", D0, D0 + timedelta(days=2), 2)
    assert ok and cents == 16000  # 2 ночи × 80 €


def test_availability_false_when_occupied():
    cache.clear()
    unit = _su(price_cents=9000, max_guests=2)
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="G")
    ok, cents = hotel_search.hotel_availability("public", D0, D0 + timedelta(days=2), 2)
    assert ok is False and cents == 0


def test_availability_respects_capacity_and_min_nights():
    cache.clear()
    _su(price_cents=9000, max_guests=2, min_nights=3)
    # 2 гостя ок по вместимости, но 2 ночи < min_nights=3 → нет
    ok, _ = hotel_search.hotel_availability("public", D0, D0 + timedelta(days=2), 2)
    assert ok is False
    # 3 ночи — ок
    ok2, _ = hotel_search.hotel_availability("public", D0, D0 + timedelta(days=3), 2)
    assert ok2 is True
    # 4 гостя — превышает вместимость
    cache.clear()
    ok3, _ = hotel_search.hotel_availability("public", D0, D0 + timedelta(days=3), 4)
    assert ok3 is False


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_date_search_keeps_available_with_range_price():
    cache.clear()
    _su(price_cents=9000, max_guests=2)  # доступный номер в схеме public
    portal = AggregatorPortal.objects.create(
        host="hotels.siteadaptor.de",
        kind=AggregatorPortal.KIND_VERTICAL,
        business_type="hotel",
        title={"de": "Hotels"},
        is_active=True,
    )
    AggregatorListing.objects.create(
        tenant_schema="public",
        tenant_slug="seeblick",
        business_name="Pension Seeblick",
        business_type="hotel",
        listing_kind=AggregatorListing.KIND_STAY,
        source_ref="a",
        title={"de": "Zimmer"},
        new_price=Decimal("90"),
        detail_url="https://seeblick.siteadaptor.de/unterkunft/a/",
        is_active=True,
    )
    von, bis = D0, D0 + timedelta(days=2)
    req = RequestFactory().get(
        "/",
        {"von": von.isoformat(), "bis": bis.isoformat(), "gaeste": "2"},
        HTTP_HOST="hotels.siteadaptor.de",
    )
    req.portal = portal
    req.tenant = types.SimpleNamespace(schema_name="public")
    resp = portal_home(req)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Pension Seeblick" in body
    assert "180" in body  # 2 ночи × 90 € за диапазон
    assert "von=" in body and "erw=2" in body  # диплинк с датами
