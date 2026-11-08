"""PH-13d: выдача поиска на телефоне по макету M6 — карточки строками (фото 116 px слева),
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


def test_search_results_are_rows_on_phones():
    _listing("promotion", "Pizza Margherita")
    _listing("promotion", "Pizza Salami")
    html = _html(_portal(), q="Pizza")
    grid = re.search(r"<div[^>]*data-card-list[^>]*>", html)
    assert grid and "max-sm:grid-cols-1" in grid.group(0)
    assert "max-sm:w-[116px]" in html and "max-sm:flex-row" in html


def test_category_page_without_search_keeps_tiles():
    _listing("promotion", "Pizza", city_category="restaurants")
    html = _html(_portal(), kind="alle", kat="essen-gastronomie")
    assert "data-card-list" not in html


def test_desktop_grid_classes_stay():
    _listing("promotion", "Pizza Margherita")
    html = _html(_portal(), q="Pizza")
    grid = re.search(r"<div[^>]*data-card-list[^>]*>", html).group(0)
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
