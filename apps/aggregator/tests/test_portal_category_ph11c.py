"""PH-11c: страница раздела (`?kat=<раздел>` без q) — дерево разделов слева и плитки подкатегорий."""

import pytest
from django.core.cache import cache

from apps.aggregator import portal_views
from apps.aggregator.search import SearchFilters
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Корень портала и меню кэшируются (Redis переживает прогоны и делится xdist-воркерами)."""
    cache.clear()
    yield
    cache.clear()


def _seed():
    _listing("promotion", "Pasta-Abend", city_category="restaurants")
    _listing("promotion", "Croissant", city_category="cafes")
    _listing("promotion", "Brotkorb", city_category="brot-backwaren")
    return _portal()


def test_section_and_category_pages_list_sections_only_in_the_filter():
    """2026-11-09 (решение владельца): дерево разделов над фильтром дублировало группу
    «Bereich» фильтра — снято; разделы остаются ТОЛЬКО в фильтре."""
    portal = _seed()
    for kat in ("essen-gastronomie", "restaurants"):
        html = _html(portal, kat=kat)
        assert "data-category-tree" not in html, kat
        assert "data-all-categories" not in html, kat
        bereich = html.split('id="flt-drawer"', 1)[1]
        assert "Restaurants" in bereich and "Cafés" in bereich, kat


def test_section_page_shows_subcategory_tiles_linking_to_categories():
    html = _html(_seed(), kat="essen-gastronomie")
    tiles = html.split("data-subcategory-tiles", 1)[1].split("</nav>", 1)[0]
    assert "kat=restaurants" in tiles and "kat=cafes" in tiles
    assert "1 Angebot" in tiles


def test_category_page_has_no_tiles():
    html = _html(_seed(), kat="restaurants")
    assert "data-subcategory-tiles" not in html


def test_search_has_no_category_tree():
    html = _html(_seed(), kat="essen-gastronomie", q="Pasta")
    assert "data-category-tree" not in html and "data-subcategory-tiles" not in html


def test_category_nav_resolves_section_and_category():
    nav = portal_views._category_nav
    assert nav(SearchFilters(kats=("essen-gastronomie",)), "") == {
        "current": "essen-gastronomie",
        "section": "essen-gastronomie",
    }
    assert nav(SearchFilters(kats=("restaurants",)), "") == {
        "current": "restaurants",
        "section": "essen-gastronomie",
    }
    assert nav(SearchFilters(kats=("restaurants",)), "Pizza") is None
    assert nav(SearchFilters(kats=("restaurants", "cafes")), "") is None
    assert nav(SearchFilters(kats=("unbekannt",)), "") is None


# --- ревью PH-11c ----------------------------------------------------------------------


def test_filter_column_collapses_on_every_page():
    portal = _seed()
    for params in ({"kat": "essen-gastronomie"}, {"q": "Pasta"}):
        html = _html(portal, **params)
        column = (
            html.split("data-flt-layout", 1)[1].split('id="flt-drawer"', 1)[0].rsplit("<div", 1)[1]
        )
        assert "lg:self-stretch" in column and "lg:group-data-[flt-collapsed]/flt:hidden" in column
