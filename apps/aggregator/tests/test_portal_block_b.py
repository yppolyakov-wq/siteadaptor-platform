"""Блок Б фидбэка портала (план docs/backlog-portal-direction-2026-10-16.md §2).

Б1 результаты выше · Б2 Liste/Karte. Замки написаны ДО кода.
"""

import uuid

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal

pytestmark = pytest.mark.django_db

_HOST = "solingen.siteadaptor.de"


@pytest.fixture(autouse=True)
def _clear(isolated_ratelimit):
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": _HOST,
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Angebote in Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


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


def _html(portal, path="/", **kw):
    req = RequestFactory().get(path, HTTP_HOST=_HOST)
    req.portal = portal
    return portal_views.portal_home(req, **kw).content.decode()


def _seed():
    _listing(title={"de": "Pizza Margherita"}, district="wald", business_type="restaurant")
    _listing(title={"de": "Reifenwechsel"}, district="mitte", business_type="kfz")
    _listing(title={"de": "Brot"}, district="graefrath", business_type="bakery")


# --- Б1: при поиске — сначала результаты, уточнение свёрнуто, чипы по найденному -----


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_shows_hit_count_and_collapses_refinement():
    p = _portal()
    _seed()
    html = _html(p, "/?q=Pizza")
    assert "data-hit-count" in html
    assert "1 Treffer" in html
    refine = html.index("data-portal-refine")
    assert html.index("data-district-chips") > refine  # районы — внутри свёрнутого блока
    assert html.rindex("Pizza Margherita") > refine  # карточка (в <head> — JSON-LD)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_chips_are_built_from_found_pool():
    p = _portal()
    _seed()
    html = _html(p, "/?q=Pizza")
    chips = html[html.index("data-district-chips") : html.index("data-district-chips") + 3000]
    assert "/stadtteil/wald/" in chips
    assert "/stadtteil/mitte/" not in chips  # в Mitte пиццы нет — мёртвый чип не нужен


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_without_search_layout_is_unchanged():
    p = _portal()
    _seed()
    html = _html(p, "/stadtteil/wald/", district="wald")
    assert "data-portal-refine" not in html
    assert "data-hit-count" not in html
    # без поиска районы — над формой поиска, как раньше
    assert html.index("data-district-chips") < html.index('name="q"')


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_search_with_district_keeps_all_district_chips():
    p = _portal()
    _seed()
    html = _html(p, "/stadtteil/wald/?q=Pizza", district="wald")
    assert "/stadtteil/mitte/" in html  # переключение района при поиске не теряется


# --- Б2: список по умолчанию, карта по кнопке, Leaflet лениво -----------------------


def _with_coords(**kw):
    return _listing(latitude=51.17, longitude=7.08, **kw)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_map_is_hidden_by_default_and_leaflet_not_loaded():
    p = _portal()
    _with_coords(district="wald")
    html = _html(p, "/stadtteil/wald/", district="wald")
    assert 'src="https://unpkg.com/leaflet' not in html  # Leaflet грузится только по клику
    assert 'id="agg-map-data"' in html
    assert "data-map-toggle" in html
    assert "data-map-open" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_map_opens_with_ansicht_karte_and_keeps_query():
    p = _portal()
    _with_coords(district="wald", title={"de": "Pizza"})
    html = _html(p, "/stadtteil/wald/?q=Pizza&ansicht=karte", district="wald")
    assert "data-map-open" in html
    # ссылка «Liste» сохраняет запрос и убирает вид
    assert 'href="?q=Pizza"' in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_city_page_also_lists_first():
    _with_coords(city="Solingen")
    req = RequestFactory().get("/entdecken/solingen/")
    html = views.city_listing(req, "Solingen").content.decode()
    assert 'src="https://unpkg.com/leaflet' not in html
    assert "data-map-toggle" in html
