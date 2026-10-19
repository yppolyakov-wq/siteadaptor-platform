"""T-8.10f F-3: «следующий шаг» в карточках MCP и учёт обращений ассистентов.

План — docs/t8-10-rest-plan-2026-10-19.md §1.4 (next_step), §1.5 (атрибуция).
Шаг акции = отклик T-8.2 (`response_for`) — та же кнопка, что на витрине."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import override_settings

from apps.aggregator import portal_stats
from apps.aggregator.models import PortalStat
from apps.aggregator.tests.test_machine_readable import _listing, _portal
from apps.aggregator.tests.test_mcp_tools import ON, _data
from apps.promotions import response
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _rl(isolated_ratelimit):
    return isolated_ratelimit


@pytest.fixture
def tenant():
    return TenantFactory(schema_name="t1", slug="baeckerei", city="Solingen")


def _promo_listing(promo, **kw):
    return _listing(
        source_ref=str(promo.pk),
        detail_url=f"https://baeckerei.siteadaptor.de/p/{promo.pk}/",
        **kw,
    )


@override_settings(**ON)
def test_next_step_follows_owner_response_choice(tenant):
    portal = _portal()
    coupon = PromotionFactory(metadata={"response": response.COUPON})
    reserve = PromotionFactory(metadata={"response": response.RESERVE})
    show = PromotionFactory(metadata={"response": response.SHOW})
    by_ref = {}
    for promo in (coupon, reserve, show):
        by_ref[promo.pk] = _promo_listing(promo).pk
    items = {it["id"]: it for it in _data(portal, "search_offers", {})["items"]}
    assert items[by_ref[coupon.pk]]["next_step"]["type"] == "coupon"
    assert items[by_ref[reserve.pk]]["next_step"]["type"] == "reserve"
    assert items[by_ref[show.pk]]["next_step"]["type"] == "visit"


@override_settings(**ON)
def test_next_step_matches_storefront_response(tenant):
    """Совпадает с кнопкой витрины: тот же `response_for` с тем же тенантом."""
    portal = _portal()
    promo = PromotionFactory()
    listing = _promo_listing(promo)
    expected = response.response_for(promo, tenant)
    expected = "visit" if expected == response.SHOW else expected
    card = _data(portal, "get_offer", {"offer_id": listing.pk})["offer"]
    assert card["next_step"]["type"] == expected


@override_settings(**ON)
def test_next_step_link_carries_mcp_channel_and_listing(tenant):
    portal = _portal()
    promo = PromotionFactory()
    listing = _promo_listing(promo)
    url = _data(portal, "get_offer", {"offer_id": listing.pk, "language": "en"})["offer"][
        "next_step"
    ]["url"]
    query = parse_qs(urlsplit(url).query)
    assert query["ch"] == ["mcp"] and query["cl"] == [str(listing.pk)]
    assert query["hl"] == ["en"]


@override_settings(**ON)
def test_external_site_gets_only_channel():
    """Визитка «Nur Eintrag» (T-8.27d): на чужой сайт — только канал, без листинга."""
    portal = _portal()
    listing = _listing(source_ref="extern", detail_url="https://example.org/brot/")
    url = _data(portal, "get_offer", {"offer_id": listing.pk})["offer"]["next_step"]["url"]
    query = parse_qs(urlsplit(url).query)
    assert query == {"ch": ["mcp"]}


@override_settings(**ON)
def test_non_promotion_kinds_have_default_steps():
    portal = _portal()
    stay = _listing(source_ref="zimmer", listing_kind="stay")
    card = _data(portal, "get_offer", {"offer_id": stay.pk})["offer"]
    assert card["next_step"]["type"] == "booking"


@override_settings(**ON)
def test_missing_tenant_falls_back_to_open():
    portal = _portal()
    listing = _listing(source_ref="00000000-0000-0000-0000-000000000000", tenant_schema="weg")
    card = _data(portal, "get_offer", {"offer_id": listing.pk})["offer"]
    assert card["next_step"]["type"] == "open"


@override_settings(**ON)
def test_steps_resolved_once_per_tenant(tenant, monkeypatch):
    import django_tenants.utils as tu

    calls = []
    real = tu.schema_context

    def spy(schema):
        calls.append(schema)
        return real(schema)

    monkeypatch.setattr(tu, "schema_context", spy)
    portal = _portal()
    for _ in range(4):
        _promo_listing(PromotionFactory())
    _data(portal, "search_offers", {})
    assert calls == ["t1"]


@override_settings(**ON)
def test_bad_source_ref_does_not_drop_other_steps(tenant):
    """Ревью F-3: легаси-листинг без UUID не обнуляет шаги остальных акций тенанта."""
    portal = _portal()
    coupon = PromotionFactory(metadata={"response": response.COUPON})
    good = _promo_listing(coupon)
    _listing(source_ref="", detail_url="https://baeckerei.siteadaptor.de/p/x/")
    items = {it["id"]: it for it in _data(portal, "search_offers", {})["items"]}
    assert items[good.pk]["next_step"]["type"] == "coupon"


@override_settings(**ON)
def test_search_counts_impressions_and_offer_counts_view():
    portal = _portal()
    a = _listing(source_ref="a")
    _listing(source_ref="b")
    _data(portal, "search_offers", {})
    _data(portal, "get_offer", {"offer_id": a.pk})
    rows = PortalStat.objects.filter(channel="mcp")
    assert rows.filter(action="impression").count() == 2
    assert rows.get(action="view", source_ref="a").count == 1


@override_settings(**ON)
def test_machine_counts_are_not_deduplicated_per_visitor():
    """Все жители за одним адресом платформы — не «один посетитель»."""
    portal = _portal()
    a = _listing(source_ref="a")
    for _ in range(3):
        _data(portal, "get_offer", {"offer_id": a.pk})
    assert PortalStat.objects.get(channel="mcp", action="view").count == 3


def test_record_machine_never_raises(monkeypatch):
    monkeypatch.setattr(portal_stats, "_bump", lambda *a, **k: 1 / 0)
    listing = _listing()
    assert portal_stats.record_machine(None, [listing], action="view", channel="mcp") == 0


def test_record_machine_rejects_unknown_channel():
    listing = _listing()
    assert portal_stats.record_machine(None, [listing], action="view", channel="evil") == 0


@override_settings(**ON)
def test_machine_limit_counts_rows_not_calls(settings):
    settings.AGGREGATOR_PORTAL_STATS = {**settings.AGGREGATOR_PORTAL_STATS, "machine_limit": 3}
    portal = _portal()
    for i in range(2):
        _listing(source_ref=f"r{i}")
    _data(portal, "search_offers", {})  # 2 строки
    _data(portal, "search_offers", {})  # ещё 2 → сверх лимита 3, не пишется
    assert sum(PortalStat.objects.values_list("count", flat=True)) == 2


def test_owner_funnel_excludes_assistant_counts_and_shows_them_apart():
    from django.utils import timezone

    from apps.aggregator import owner_stats

    tenant = TenantFactory(schema_name="t_os", slug="os", city="Solingen")
    today = timezone.localdate()
    common = {"tenant_schema": "t_os", "day": today, "listing_kind": "promotion", "source_ref": "a"}
    PortalStat.objects.create(action="view", channel="portal", count=2, **common)
    PortalStat.objects.create(action="view", channel="mcp", count=50, **common)
    PortalStat.objects.create(action="impression", channel="mcp", count=70, **common)
    PortalStat.objects.create(action="deal", channel="mcp", count=1, **common)
    stats = owner_stats.summary(tenant, 30)
    funnel = {row["code"]: row["value"] for row in stats["funnel"]}
    assert funnel["view"] == 2 and funnel["impression"] == 0
    assert funnel["deal"] == 1  # сделка по ссылке ассистента — человек, в воронке
    assert stats["assistants"] == (70, 50)
    assert owner_stats.portal_totals(tenant) == (2, 0)
    assert stats["top"][0]["values"]["view"] == 2
