"""T-8.13a: единые категории каталога города — справочник, синк, фильтры портала.

План — docs/t8-13a-city-categories-plan-2026-10-10.md §2 (таксономия — ТЗ «Siteadaptor 2.0» §4).
"""

import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import category_facets, portal_views, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.core import city_categories as cc
from apps.promotions.models import Promotion
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


# --- справочник ----------------------------------------------------------------------


def test_registry_slugs_unique_and_sections_exist():
    cat_keys = [c.key for c in cc.CATEGORIES]
    section_keys = [s.key for s in cc.SECTIONS]
    assert len(set(cat_keys)) == len(cat_keys)
    assert len(set(section_keys)) == len(section_keys)
    assert not set(cat_keys) & set(section_keys)  # `?kat=` однозначен
    assert {c.section for c in cc.CATEGORIES} == set(section_keys)  # пустых разделов нет


def test_registry_follows_tz_main_categories():
    assert len(cc.SECTIONS) == 15
    assert str(cc.section("mode-accessoires").label) == "Mode & Accessoires"
    assert cc.category("damenmode").section == "mode-accessoires"


def test_every_business_type_has_a_known_suggestion():
    for value, _label in Tenant.BUSINESS_TYPES:
        assert value in cc.BY_BUSINESS_TYPE, value
        assert cc.category(cc.suggest_for_business_type(value)), value


def test_event_themes_map_to_known_categories():
    from apps.events.taxonomy import CATEGORIES as THEMES

    for key, _label in THEMES:
        assert cc.category(cc.BY_EVENT_THEME.get(key, "events")), key


def test_normalize_drops_unknown():
    assert cc.normalize_category("damenmode") == "damenmode"
    assert cc.normalize_category("<script>") == ""
    assert cc.normalize_category("mode-accessoires") == ""  # раздел — не категория акции
    assert cc.normalize_tags(["regional", "x", "vegan", "vegan"]) == ["vegan", "regional"]


def test_filter_section_expands_to_its_categories():
    keys = cc.keys_for_filter("mode-accessoires")
    assert "damenmode" in keys and "schuhe" in keys and "brot-backwaren" not in keys
    assert cc.keys_for_filter("schuhe") == ["schuhe"]
    assert cc.keys_for_filter("nope") == []


# --- синк ------------------------------------------------------------------------------


def test_promotion_listing_gets_own_category_and_tags():
    TenantFactory(schema_name="public", slug="cat-own", business_type="clothing")
    promo = Promotion.objects.create(
        status="active",
        title={"de": "Jacke"},
        city_category="herrenmode",
        city_tags=["regional", "x"],
    )
    assert tasks.sync_listing("public", str(promo.pk)) == "upserted"
    row = AggregatorListing.objects.get()
    assert row.city_category == "herrenmode"
    assert row.city_tags == ["regional"]


def test_promotion_without_category_gets_business_type_suggestion():
    TenantFactory(schema_name="public", slug="cat-sug", business_type="clothing")
    promo = Promotion.objects.create(status="active", title={"de": "Jacke"})
    tasks.sync_listing("public", str(promo.pk))
    assert AggregatorListing.objects.get().city_category == "damenmode"


@pytest.mark.parametrize(
    ("kind", "snap", "expected"),
    [
        ("stay", None, ("hotels", [])),
        ("event", {"category": "yoga"}, ("yoga", ["yoga"])),
        ("event", {"category": ""}, ("events", [])),
        ("tour", {"category": "natur"}, ("outdoor", [])),
        ("menu", {"diets": ["vegan", "foo"]}, ("catering", ["vegan"])),
    ],
)
def test_other_kinds_follow_rules(kind, snap, expected):
    tenant = TenantFactory(schema_name="cat_kind", slug="cat-kind")
    out = tasks._city_fields(kind, tenant, snap)
    assert (out["city_category"], out["city_tags"]) == expected


# --- фильтры -------------------------------------------------------------------------


def test_listings_for_filters_by_section_category_and_tag():
    _listing(city_category="damenmode", city_tags=["regional"])
    _listing(city_category="schuhe")
    _listing(city_category="brot-backwaren", city_tags=["vegan"])
    assert views.listings_for(city_category="mode-accessoires").count() == 2
    assert views.listings_for(city_category="schuhe").count() == 1
    assert views.listings_for(city_tag="vegan").count() == 1
    # мусор фильтр не включает (и не роняет)
    assert views.listings_for(city_category="zzz", city_tag="zzz").count() == 3


def test_chips_show_only_present_and_open_section():
    _listing(city_category="damenmode", city_tags=["regional"])
    _listing(city_category="brot-backwaren")
    qs = AggregatorListing.objects.public()
    chips = category_facets.chips(qs, "/", "", "")
    assert [s["key"] for s in chips["sections"]] == ["lebensmittel-getraenke", "mode-accessoires"]
    assert chips["categories"] == []  # раздел не открыт
    assert [t["key"] for t in chips["tags"]] == ["regional"]
    opened = category_facets.chips(qs, "/", "mode-accessoires", "")
    assert [c["key"] for c in opened["categories"]] == ["damenmode"]
    assert opened["label"] == "Mode & Accessoires"


def test_selected_ignores_garbage():
    req = RequestFactory().get("/?kat=<x>&merkmal=drop table")
    assert category_facets.selected(req) == ("", "")


def _portal():
    return AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "Angebote in Solingen"},
        is_active=True,
    )


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_filters_by_kat_and_shows_chips():
    portal = _portal()
    _listing(title={"de": "Mantel"}, city_category="damenmode")
    _listing(title={"de": "Brötchen"}, city_category="brot-backwaren")
    req = RequestFactory().get("/?kat=mode-accessoires")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Mantel" in html and "Brötchen" not in html
    assert 'data-cat-chip="damenmode"' in html
    assert 'data-cat-chip="lebensmittel-getraenke"' in html  # чип раздела по всему пулу


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_garbage_param_does_not_break():
    portal = _portal()
    _listing(title={"de": "Mantel"}, city_category="damenmode")
    req = RequestFactory().get("/?kat=%27%3B--&merkmal=%3Cb%3E")
    req.portal = portal
    resp = portal_views.portal_home(req)
    assert resp.status_code == 200 and "Mantel" in resp.content.decode()


@pytest.mark.urls("config.urls_public")
def test_discover_search_filters_by_tag_and_keeps_params():
    _listing(title={"de": "Vegane Torte"}, city_category="brot-backwaren", city_tags=["vegan"])
    _listing(title={"de": "Mettbrötchen"}, city_category="brot-backwaren")
    html = views.discover_index(
        RequestFactory().get("/entdecken/?merkmal=vegan&city=Solingen")
    ).content.decode()
    assert "Vegane Torte" in html and "Mettbrötchen" not in html
    assert "data-category-chips" in html and "city=Solingen" in html
