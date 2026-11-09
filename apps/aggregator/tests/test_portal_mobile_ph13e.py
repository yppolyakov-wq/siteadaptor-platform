"""PH-13e: страница раздела на телефоне по макету M7 — компактные плитки подразделов и вход
во все разделы (то же мега-меню, что у ☰: второй список разделов в DOM не заводим)."""

import re

import pytest
from django.core.cache import cache

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _section_page():
    _listing("promotion", "Pizza", city_category="restaurants")
    _listing("promotion", "Croissant", city_category="cafes")
    return _html(_portal(), kind="alle", kat="essen-gastronomie")


def test_subcategory_tiles_are_compact_on_phones():
    html = _section_page()
    tiles = re.search(r"<nav[^>]*data-subcategory-tiles.*?</nav>", html, re.S).group(0)
    assert "max-sm:w-[76px]" in tiles and "max-sm:w-[72px]" in tiles
    assert "max-sm:border-0" in tiles


def test_section_page_has_no_second_category_list():
    """2026-11-09: «Alle Bereiche» и дерево сняты — разделы только в фильтре."""
    html = _section_page()
    assert "data-all-categories" not in html and "data-category-tree" not in html
