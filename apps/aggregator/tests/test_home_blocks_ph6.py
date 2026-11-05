"""PH-6: блоки главной — «Endet bald», «Jetzt geöffnet», полоса «Anzeige», районы."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import portal_views
from apps.aggregator.models import AggregatorListing
from apps.aggregator.tests.test_portal_discover import _get, _html, _listing, _portal
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

ALWAYS = {str(d): ["00:00", "23:59"] for d in range(7)}


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def test_urgent_block_is_titled_endet_bald_and_sorted_by_end():
    _listing(
        "promotion",
        "Bald",
        city_category="restaurants",
        ends_at=timezone.now() + timedelta(hours=5),
    )
    blocks = home.home_blocks(AggregatorListing.objects.all(), city="Solingen", path="/")
    angebote = next(b for b in blocks if b["key"] == "angebote")
    assert angebote["title"] == "Endet bald" and "sort=endet" in angebote["more_url"]


def test_open_block_only_open_businesses_and_district_tiles():
    TenantFactory(schema_name="offen1", slug="offen1", opening_hours_structured=ALWAYS)
    TenantFactory(schema_name="zu1", slug="zu1", opening_hours_structured={})
    a = _listing("product", "Offen-Ware", schema="offen1", district="mitte")
    _listing("product", "Zu-Ware", schema="zu1", district="mitte")
    base = AggregatorListing.objects.all()
    snap = home.open_snapshot_for(base)
    open_set = home.open_schemas(snap)
    assert open_set == {"offen1"}
    block = home.open_block(base, open_set, path="/")
    assert [i.pk for i in block["items"]] == [a.pk] and block["more_url"].endswith("offen=1")
    tiles = home.district_tiles(base, "Solingen", open_set)
    assert tiles == [{"slug": "mitte", "name": tiles[0]["name"], "count": 2, "open": 1}]


def test_home_renders_new_blocks_and_marked_ad_strip(django_assert_max_num_queries):
    portal = _portal()
    TenantFactory(schema_name="offen2", slug="offen2", opening_hours_structured=ALWAYS)
    for i in range(4):  # «Produkte» берут по 2 на бизнес — остальное попадёт в «offen»
        _listing("service", f"Offen-Termin {i}", schema="offen2", district="mitte")
    _listing(
        "promotion",
        "Bezahlt",
        city_category="restaurants",
        featured_until=timezone.now() + timedelta(days=1),
    )
    body = _html(portal)
    assert 'data-home-block="offen"' in body and "data-district-tile=" in body
    assert "ANZEIGE" in body and "Bezahlte Platzierung" in body
    cache.clear()
    # 2026-11-05 (PH-6): + «Jetzt geöffnet» (1) и районы (1) поверх кап 16 главной.
    with django_assert_max_num_queries(18):
        portal_views.portal_home(_get(portal))
