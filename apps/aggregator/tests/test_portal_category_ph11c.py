"""PH-11c: страница раздела (`?kat=<раздел>` без q) — дерево разделов слева и плитки подкатегорий."""

import pytest

from apps.aggregator import portal_views
from apps.aggregator.search import SearchFilters
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _seed():
    _listing("promotion", "Pasta-Abend", city_category="restaurants")
    _listing("promotion", "Croissant", city_category="cafes")
    _listing("promotion", "Brotkorb", city_category="brot-backwaren")
    return _portal()


def _tree(html):
    return html.split("data-category-tree", 1)[1].split("</nav>", 1)[0]


def test_section_page_shows_tree_with_current_section_expanded():
    html = _html(_seed(), kat="essen-gastronomie")
    tree = _tree(html)
    assert 'aria-current="page"' in tree
    current = tree.split('aria-current="page"', 1)[0].rsplit("<a", 1)[1]
    assert "kat=essen-gastronomie" in current
    assert "Restaurants" in tree and "Cafés" in tree  # подкатегории раскрыты


def test_section_page_shows_subcategory_tiles_linking_to_categories():
    html = _html(_seed(), kat="essen-gastronomie")
    tiles = html.split("data-subcategory-tiles", 1)[1].split("</nav>", 1)[0]
    assert "kat=restaurants" in tiles and "kat=cafes" in tiles
    assert "1 Angebot" in tiles


def test_category_page_marks_category_and_has_no_tiles():
    html = _html(_seed(), kat="restaurants")
    tree = _tree(html)
    current = tree.split('aria-current="page"', 1)[0].rsplit("<a", 1)[1]
    assert "kat=restaurants" in current
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
