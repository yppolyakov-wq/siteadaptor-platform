"""T-8.10f F-2: инструменты чтения каталога города через MCP.

План — docs/t8-10-rest-plan-2026-10-19.md §1.4/§1.7 F-2. Выдача ассистенту обязана
совпадать с порталом: та же видимость, область, правила цены, «Anzeige», демо."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone
from jsonschema import Draft202012Validator

from apps.aggregator.mcp import handlers, tools
from apps.aggregator.mcp.views import mcp_endpoint
from apps.aggregator.models import SearchQueryLog
from apps.aggregator.tests.test_machine_readable import _HOST, _listing, _portal
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ON = {"MCP_ENABLED": True, "MCP_PORTAL_HOSTS": [], "ROOT_URLCONF": "config.urls_portal"}


@pytest.fixture(autouse=True)
def _rl(isolated_ratelimit):
    return isolated_ratelimit


def _call(portal, name, arguments=None):
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name}}
    if arguments is not None:
        msg["params"]["arguments"] = arguments
    req = RequestFactory().post(
        "/mcp/", data=json.dumps(msg), content_type="application/json", HTTP_HOST=_HOST
    )
    req.portal = portal
    body = json.loads(mcp_endpoint(req).content)
    assert "result" in body, body
    return body["result"]


def _data(portal, name, arguments=None):
    res = _call(portal, name, arguments)
    assert res["isError"] is False, res
    schema = tools.REGISTRY[name].output_schema
    Draft202012Validator(schema).validate(res["structuredContent"])
    return res["structuredContent"]


def _ids(data):
    return [it["id"] for it in data["items"]]


def test_registry_has_five_read_tools_with_valid_schemas():
    names = {"search_offers", "get_offer", "get_business", "list_categories", "list_districts"}
    assert names <= set(tools.REGISTRY)
    for name in names:
        tool = tools.REGISTRY[name]
        Draft202012Validator.check_schema(tool.input_schema)
        Draft202012Validator.check_schema(tool.output_schema)
        assert tool.annotations.get("readOnlyHint") is True


@override_settings(**ON)
def test_search_returns_only_portal_scope():
    portal = _portal()
    mine = _listing()
    other_city = _listing(source_ref="koeln", city="Köln")
    inactive = _listing(source_ref="aus", is_active=False)
    hidden = _listing(source_ref="versteckt", hidden_at=timezone.now())
    expired = _listing(source_ref="alt", ends_at=timezone.now() - timedelta(hours=1))
    ids = _ids(_data(portal, "search_offers", {}))
    assert mine.pk in ids
    for gone in (other_city, inactive, hidden, expired):
        assert gone.pk not in ids


@override_settings(**ON)
def test_withheld_business_never_shown():
    portal = _portal()
    TenantFactory(schema_name="t_paused", city="Solingen", is_active=False)
    paused = _listing(tenant_schema="t_paused", source_ref="pausiert")
    assert paused.pk not in _ids(_data(portal, "search_offers", {}))


@override_settings(**ON)
def test_demo_only_on_preview_portal_and_marked():
    real_portal = _portal()
    demo = _listing(source_ref="demo", is_demo=True)
    real = _listing(source_ref="echt")
    ids = _ids(_data(real_portal, "search_offers", {}))
    assert demo.pk not in ids and real.pk in ids
    real_portal.show_demo = True
    real_portal.save()
    data = _data(real_portal, "search_offers", {})
    by_id = {it["id"]: it for it in data["items"]}
    assert by_id[demo.pk]["demo"] is True and by_id[real.pk]["demo"] is False
    assert data["notice"]["preview"] is True


@override_settings(**ON)
def test_featured_not_lifted_but_marked_as_ad():
    portal = _portal()
    featured = _listing(source_ref="werbung", featured_until=timezone.now() + timedelta(days=3))
    newer = _listing(source_ref="neu")
    data = _data(portal, "search_offers", {})
    assert _ids(data)[0] == newer.pk  # органический порядок: новее первым
    card = next(it for it in data["items"] if it["id"] == featured.pk)
    assert card["sponsored"] is True and card["label"] == "Anzeige"
    plain = next(it for it in data["items"] if it["id"] == newer.pk)
    assert plain["sponsored"] is False and plain["label"] is None


@override_settings(**ON)
def test_hidden_price_never_leaks():
    portal = _portal()
    secret = _listing(source_ref="geheim", new_price=None, old_price="9.00")
    card = next(it for it in _data(portal, "search_offers", {})["items"] if it["id"] == secret.pk)
    assert card["price"] is None and card["old_price"] is None


@override_settings(**ON)
def test_card_matches_open_feed_item():
    """Карточка = элемент открытого фида (одна точка истины цены/срока/категории)."""
    from apps.aggregator import open_feed

    portal = _portal()
    listing = _listing()
    listing.refresh_from_db()
    card = _data(portal, "get_offer", {"offer_id": listing.pk})["offer"]
    req = RequestFactory().get("/", HTTP_HOST=_HOST)
    req.portal = portal
    item = open_feed.feed_item(listing, request=req, preview=False)
    ext = item["_siteadaptor"]
    for key in ("price", "old_price", "price_reference", "currency", "availability", "category"):
        assert card[key] == ext[key]
    assert card["url"] == item["url"] and card["title"] == item["title"]


@override_settings(**ON)
def test_query_intent_filters_are_applied_and_reported():
    portal = _portal()
    cheap = _listing(source_ref="billig", new_price="3.00", title={"de": "Brot billig"})
    dear = _listing(source_ref="teuer", new_price="30.00", title={"de": "Brot teuer"})
    data = _data(portal, "search_offers", {"query": "Brot unter 5 €"})
    ids = _ids(data)
    assert cheap.pk in ids and dear.pk not in ids
    assert Decimal(data["applied_filters"]["price_max"]) == Decimal("5")


@override_settings(**ON)
def test_explicit_filters():
    portal = _portal()
    in_cat = _listing(source_ref="brot", city_category="brot-backwaren")
    off_cat = _listing(source_ref="kaffee", city_category="cafes")
    data = _data(portal, "search_offers", {"category": "brot-backwaren", "price_max": 10})
    assert in_cat.pk in _ids(data) and off_cat.pk not in _ids(data)


@override_settings(**ON)
def test_garbage_filter_values_are_ignored_not_500():
    portal = _portal()
    listing = _listing()
    data = _data(
        portal,
        "search_offers",
        {"category": "gibtsnicht", "district": "nirgendwo", "date": "morgen", "size": "ZZ"},
    )
    assert listing.pk in _ids(data)


@override_settings(**ON)
def test_limit_bounds_and_cursor_paging():
    portal = _portal()
    created = [_listing(source_ref=f"n{i}") for i in range(5)]
    assert _call(portal, "search_offers", {"limit": 50})["isError"] is True
    first = _data(portal, "search_offers", {"limit": 2})
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = _data(portal, "search_offers", {"limit": 2, "cursor": first["next_cursor"]})
    assert not set(_ids(first)) & set(_ids(second))
    assert first["total"] == len(created)
    # мусорный курсор — первая страница, не 500
    assert _ids(_data(portal, "search_offers", {"limit": 2, "cursor": "%%%"})) == _ids(first)


def test_depth_is_capped():
    assert handlers.DEPTH_MAX <= 10 * handlers.LIMIT_MAX


@override_settings(**ON)
def test_unknown_arguments_rejected():
    portal = _portal()
    assert _call(portal, "search_offers", {"stadtteil": "wald"})["isError"] is True


@override_settings(**ON)
def test_get_offer_out_of_scope_is_not_found():
    portal = _portal()
    foreign = _listing(source_ref="koeln", city="Köln")
    res = _call(portal, "get_offer", {"offer_id": foreign.pk})
    assert res["isError"] is True and res["content"][0]["text"] == "Angebot nicht gefunden."
    res = _call(portal, "get_offer", {"offer_id": 999999})
    assert res["isError"] is True


@override_settings(**ON)
def test_get_offer_has_seller():
    portal = _portal()
    TenantFactory(schema_name="t1", slug="baeckerei", city="Solingen", name="Bäckerei Klinge")
    listing = _listing()
    data = _data(portal, "get_offer", {"offer_id": listing.pk})
    assert data["seller"]["name"] == "Bäckerei Klinge"
    assert "email" not in json.dumps(data["seller"]).lower()


@override_settings(**ON)
def test_get_business_profile_and_offers():
    portal = _portal()
    TenantFactory(schema_name="t1", slug="baeckerei", city="Solingen", name="Bäckerei Klinge")
    offer = _listing()
    _listing(source_ref="fremd", tenant_schema="t2", tenant_slug="andere")
    data = _data(portal, "get_business", {"slug": "baeckerei"})
    assert data["business"]["name"] == "Bäckerei Klinge"
    assert data["business"]["page"].endswith("/unternehmen/baeckerei/")
    assert [it["id"] for it in data["offers"]] == [offer.pk]


@override_settings(**ON)
def test_get_business_out_of_scope_is_not_found():
    portal = _portal()
    TenantFactory(schema_name="t9", slug="koelner", city="Köln")
    assert _call(portal, "get_business", {"slug": "koelner"})["isError"] is True
    assert _call(portal, "get_business", {"slug": "gibtsnicht"})["isError"] is True
    assert _call(portal, "get_business", {"slug": "Ungültig!"})["isError"] is True


@pytest.fixture(autouse=True)
def _cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@override_settings(**ON)
def test_list_categories_is_cached(django_assert_num_queries):
    portal = _portal()
    _listing(city_category="brot-backwaren")
    _data(portal, "list_categories", {})
    with django_assert_num_queries(0):
        _data(portal, "list_categories", {"language": "en"})


@override_settings(**ON)
def test_list_categories_only_non_empty():
    portal = _portal()
    _listing(city_category="brot-backwaren", city_tags=["vegan"])
    data = _data(portal, "list_categories", {})
    keys = [c["key"] for s in data["sections"] for c in s["categories"]]
    assert keys == ["brot-backwaren"]
    assert [t["key"] for t in data["tags"]] == ["vegan"]


@override_settings(**ON)
def test_list_districts():
    portal = _portal()
    data = _data(portal, "list_districts", {})
    assert {"slug": "graefrath", "name": "Gräfrath"} in data["districts"]


@override_settings(**ON)
def test_language_switches_labels():
    portal = _portal()
    _listing(city_category="brot-backwaren")
    de = _data(portal, "list_categories", {"language": "de"})
    en = _data(portal, "list_categories", {"language": "en"})
    assert de["sections"][0]["label"] != en["sections"][0]["label"]


@override_settings(**ON)
def test_search_is_logged_as_mcp_surface_without_personal_data():
    portal = _portal()
    _listing()
    _data(portal, "search_offers", {"query": "Brotkorb"})
    row = SearchQueryLog.objects.get()
    assert row.surface == "mcp" and row.query_norm == "brotkorb"


@override_settings(**ON)
def test_search_query_count_is_bounded(django_assert_max_num_queries):
    portal = _portal()
    for i in range(12):
        _listing(source_ref=f"q{i}")
    with django_assert_max_num_queries(12):
        data = _data(portal, "search_offers", {"limit": 10})
    assert len(data["items"]) == 10


# --- ревью F-2 ----------------------------------------------------------------


@override_settings(**ON)
def test_paging_is_logged_once():
    portal = _portal()
    for i in range(3):
        _listing(source_ref=f"p{i}", title={"de": f"Brotkorb {i}"})
    first = _data(portal, "search_offers", {"query": "Brotkorb", "limit": 1})
    _data(
        portal, "search_offers", {"query": "Brotkorb", "limit": 1, "cursor": first["next_cursor"]}
    )
    assert SearchQueryLog.objects.get().searches == 1


@override_settings(**ON)
def test_search_has_own_rate_limit(monkeypatch):
    from apps.aggregator import views as agg_views

    portal = _portal()
    monkeypatch.setattr(agg_views, "SEARCH_RATE_LIMIT", 1)
    assert _call(portal, "search_offers", {})["isError"] is False
    assert _call(portal, "search_offers", {})["isError"] is True
    # прочие инструменты лимитом поиска не задеты
    assert _call(portal, "list_districts", {})["isError"] is False


@override_settings(**ON)
def test_applied_date_uses_input_vocabulary():
    portal = _portal()
    data = _data(portal, "search_offers", {"date": "today"})
    assert data["applied_filters"]["date"] == "today"


@override_settings(**ON)
def test_business_card_is_not_an_offer():
    portal = _portal()
    card = _listing(source_ref="firma", listing_kind="business")
    assert _call(portal, "get_offer", {"offer_id": card.pk})["isError"] is True


def test_total_never_promises_more_than_reachable():
    # не фикстура `settings` вместе с override_settings: её снимок взял бы ROOT_URLCONF
    # портала и вернул его после теста (утечка urlconf в чужие тесты, CI #2870)
    from django.conf import settings

    search = {**settings.AGGREGATOR_SEARCH, "max_results": 10_000}
    with override_settings(AGGREGATOR_SEARCH=search, **ON):
        _check_total()


def _check_total():
    portal = _portal()
    _listing()
    data = _data(portal, "search_offers", {})
    assert data["total"] <= handlers.DEPTH_MAX
