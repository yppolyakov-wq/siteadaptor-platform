"""T-8.10d D-1e: входы в подписку на поиск — под выдачей портала и /entdecken/, сужение
на странице компании. Кнопки — ссылки/GET-формы (кэш публичных страниц P0-1)."""

from urllib.parse import parse_qsl

import pytest
from django.http import QueryDict
from django.test import override_settings

from apps.aggregator import follow, follow_query, portal_views, reviews_views, views
from apps.aggregator.tests.test_follow_query import (
    CITY,
    OHLIGS,
    _listing,
    _portal,
    _qd,
    _req,
    _tenant,
)

pytestmark = pytest.mark.django_db


def test_follow_link_only_for_real_query_sets():
    portal = _portal()
    # одно старое условие — для него уже есть кнопка «Folgen», вторую не рисуем
    assert follow_query.follow_link(_qd(stadtteil=OHLIGS), portal=portal) is None
    assert follow_query.follow_link(_qd(), portal=portal) is None
    target, qs = follow_query.follow_link(_qd(q="Tomaten", stadtteil=OHLIGS), portal=portal)
    assert target.kind == "query"
    params = dict(parse_qsl(qs))
    assert params["art"] == "suche" and params["q"] == "Tomaten"


def test_follow_link_path_district_and_dropped_names_only():
    portal = _portal()
    target, qs = follow_query.follow_link(
        _qd(q="Tomaten", lat="51.17", lng="7.08", datum="heute"),
        portal=portal,
        path_district=OHLIGS,
    )
    pairs = parse_qsl(qs)
    assert ("stadtteil", OHLIGS) in pairs
    # координаты/даты посетителя — только именами, без значений
    assert "51.17" not in qs and "heute" not in qs
    assert dict(pairs)["entfaellt"] == "datum,lat,lng"
    assert follow_query.dropped(QueryDict(qs)) == ["datum", "lat", "lng"]


def test_dropped_marker_is_whitelisted():
    assert follow_query.dropped(_qd(entfaellt="datum,evil,<x>")) == ["datum"]


def test_follow_link_entdecken_needs_city_and_skips_unsupported_filters():
    assert follow_query.follow_link(_qd(q="Tomaten"), portal=None) is None
    assert follow_query.follow_link(_qd(q="Tomaten", city="Solingen"), portal=None) is not None
    # фильтры только /entdecken/ письмо не знает — честнее не предлагать подписку
    assert (
        follow_query.follow_link(_qd(q="Tomaten", city="Solingen", diet="vegan"), portal=None)
        is None
    )


def test_query_string_joins_all_pairs():
    target = follow.parse_target(_qd(art="suche", q="Tomaten", marke="Bio Hof"), portal=_portal())
    pairs = parse_qsl(target.query_string)
    assert ("q", "Tomaten") in pairs and ("marke", "Bio Hof") in pairs


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_results_show_search_follow(isolated_ratelimit):
    portal = _portal()
    tenant = _tenant()
    _listing(tenant, title={"de": "Tomaten rot"})
    html = portal_views.portal_home(_req("get", "/", {"q": "Tomaten"}, portal=portal)).content
    html = html.decode()
    assert "data-search-follow" in html and "art=suche" in html
    plain = portal_views.portal_home(_req("get", "/", portal=portal)).content.decode()
    assert "data-search-follow" not in plain


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_results_show_search_follow_with_city(isolated_ratelimit):
    tenant = _tenant()
    _listing(tenant, title={"de": "Tomaten rot"})
    with_city = views.discover_index(_req("get", "/entdecken/", {"q": "Tomaten", "city": CITY}))
    assert "data-search-follow" in with_city.content.decode()
    without = views.discover_index(_req("get", "/entdecken/", {"q": "Tomaten"}))
    assert "data-search-follow" not in without.content.decode()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_narrow_form_lists_own_categories_and_brands():
    portal = _portal()
    tenant = _tenant()
    other = _tenant()
    _listing(tenant, brand="Sonnenhof")
    _listing(other, brand="Fremdmarke", city_category="baeckerei")
    html = reviews_views.business_page(
        _req("get", f"/unternehmen/{tenant.slug}/", portal=portal), tenant.slug
    ).content.decode()
    assert "data-follow-narrow" in html
    assert 'name="art" value="suche"' in html and f'value="{tenant.slug}"' in html
    assert "Sonnenhof" in html and "Fremdmarke" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_no_narrow_form_for_demo():
    portal = _portal(show_demo=True)
    demo = _tenant(is_demo=True)
    _listing(demo, is_demo=True, brand="Sonnenhof")
    html = reviews_views.business_page(
        _req("get", f"/unternehmen/{demo.slug}/", portal=portal), demo.slug
    ).content.decode()
    assert "data-follow-narrow" not in html
