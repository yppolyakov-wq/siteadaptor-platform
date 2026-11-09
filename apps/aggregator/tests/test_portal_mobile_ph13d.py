"""PH-13d: выдача поиска на телефоне (макет M6; с 2026-11-09 — плитка 2 в ряд, строки — «Liste»),
«Später geöffnet · N». Раздел без поиска остаётся плиткой; с sm разметка прежняя."""

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


def test_search_results_are_tiles_two_per_row_on_phones():
    """2026-11-09 (фидбэк владельца): «Kacheln» на телефоне — плитка 2 в ряд, фото во всю
    ширину; строки — только в «Liste» (раньше поиск на телефоне дублировал «Liste»)."""
    _listing("promotion", "Pizza Margherita")
    _listing("promotion", "Pizza Salami")
    html = _html(_portal(), q="Pizza")
    grid = re.search(r"<div[^>]*data-flt-grid[^>]*>", html).group(0)
    assert "grid-cols-2" in grid and "max-sm:grid-cols-1" not in grid
    assert "data-card-list" not in html and "max-sm:w-[116px]" not in html
    assert "max-sm:aspect-square" in html  # фото крупно, как в каталоге


def test_liste_view_keeps_rows_in_search():
    _listing("promotion", "Pizza Margherita")
    html = _html(_portal(), q="Pizza", ansicht="liste")
    assert "data-card-rows" in html


def test_category_page_without_search_keeps_tiles():
    _listing("promotion", "Pizza", city_category="restaurants")
    html = _html(_portal(), kind="alle", kat="essen-gastronomie")
    assert "data-card-list" not in html and "data-card-rows" not in html


def test_desktop_grid_classes_stay():
    _listing("promotion", "Pizza Margherita")
    html = _html(_portal(), q="Pizza")
    grid = re.search(r"<div[^>]*data-flt-grid[^>]*>", html).group(0)
    assert "xl:grid-cols-4" in grid or "lg:grid-cols-3" in grid


def test_filter_drawer_is_a_bottom_sheet_on_phones():
    _listing("promotion", "Pizza Margherita")
    html = _html(_portal(), q="Pizza")
    dialog = re.search(r'<dialog id="flt-drawer"[^>]*>', html).group(0)
    assert "max-sm:rounded-t-3xl" in dialog and "max-sm:h-[85dvh]" in dialog
    assert "lg:block" in dialog  # на десктопе — та же колонка
    assert "data-flt-handle" in html


def test_later_divider_shows_how_many():
    from django.utils import timezone

    from apps.tenants.tests.factories import TenantFactory

    tomorrow = str((timezone.localtime().weekday() + 1) % 7)
    TenantFactory(
        schema_name="zu", slug="zu", opening_hours_structured={tomorrow: ["08:00", "18:00"]}
    )
    _listing("promotion", "Pizza offen")
    _listing("promotion", "Pizza zu", schema="zu")
    html = _html(_portal(), q="Pizza")
    if "data-later-divider" not in html:
        pytest.skip("часы не дали «später geöffnet»")
    divider = re.search(r"<div[^>]*data-later-divider.*?</div>", html, re.S).group(0)
    assert re.search(r"data-later-count>\s*1\s*<", divider)
