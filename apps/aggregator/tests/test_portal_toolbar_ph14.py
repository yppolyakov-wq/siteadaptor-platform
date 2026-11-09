"""PH-14 (вариант A): панель выдачи в одну строку. План — docs/ph14-search-toolbar-plan-2026-11-09.md."""

from __future__ import annotations

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


def _seed():
    _listing("promotion", "Pizza Margherita", city_category="restaurants", district="wald")
    _listing("promotion", "Pizza Salami", city_category="restaurants", district="mitte")
    _listing("product", "Pizzastein", city_category="restaurants", district="wald")
    return _portal()


def _bar(html):
    return (
        html.split("<div data-flt-bar", 1)[1].split("</form>", 1)[0]
        + html.split("data-view-switch", 1)[1].split("</nav>", 1)[0]
    )


def test_one_row_holds_filter_kinds_district_open_sort_and_view():
    html = _html(_seed(), q="Pizza")
    row = (
        html.split("<div data-flt-bar", 1)[1].split("data-flt-applied", 1)[0].split("<script", 1)[0]
    )
    for marker in (
        "data-flt-open",
        "data-portal-tabs",
        'data-flt-pop="stadtteil"',
        "Jetzt geöffnet",
        "data-flt-sort",
        'data-view="kacheln"',
        'data-view="liste"',
    ):
        assert marker in row, marker
    # Bereich / Preis / Merkmale — только в фильтре
    for gone in ('data-flt-pop="bereich"', 'data-flt-pop="preis"', 'data-flt-pop="merkmal"'):
        assert gone not in html, gone
    assert html.count("data-portal-tabs") == 1  # вкладки не дублируются отдельной строкой


def test_hit_count_and_bell_sit_in_the_title_line():
    html = _html(_seed(), q="Pizza")
    title = html.split("<h1", 1)[1].split("</div>", 1)[0]
    assert "data-hit-count" in title and "3 Treffer" in title
    bell = re.search(r"<a [^>]*data-search-follow[^>]*>.*?</a>", title, re.S).group(0)
    assert "h-11 w-11" in bell and 'class="sr-only"' in bell


def test_applied_filters_are_chips_below_the_row_with_clear_all():
    html = _html(_seed(), q="Pizza", stadtteil=["wald", "mitte"])
    applied = html.split("data-flt-applied", 1)[1].split("</div>", 1)[0]
    assert applied.count("data-flt-pill") == 2 and "data-flt-reset-all" in applied


def test_list_view_renders_rows_and_survives_filters():
    html = _html(_seed(), q="Pizza", ansicht="liste")
    assert "data-card-rows" in html
    current = re.search(r'<a [^>]*data-view="liste"[^>]*>', html).group(0)
    assert 'aria-current="page"' in current and 'rel="nofollow"' in current
    # переход фильтром (Jetzt geöffnet) сохраняет вид
    open_link = re.search(r'<a href="([^"]*)"[^>]*>\s*Jetzt geöffnet', html).group(1)
    assert "ansicht=liste" in open_link.replace("&amp;", "&")


def test_garbage_view_is_tiles_and_sort_offers_nearby_without_point():
    html = _html(_seed(), q="Pizza", ansicht="<x>")
    assert "data-card-rows" not in html
    kacheln = re.search(r'<a [^>]*data-view="kacheln"[^>]*>', html).group(0)
    assert 'aria-current="page"' in kacheln
    form = re.search(r"<form [^>]*data-flt-sort[^>]*>", html).group(0)
    assert 'data-needs-point="naehe"' in form
    assert '<option value="naehe"' in html


def test_toolbar_has_no_csrf_or_post():
    html = _html(_seed(), q="Pizza")
    flt = html.split("data-flt ", 1)[1].split("<script", 1)[0]
    assert "csrfmiddlewaretoken" not in flt and 'method="post"' not in flt.lower()


def test_kind_tabs_and_new_search_keep_the_list_view():
    """django-ревью PH-14: вкладка «Produkte» и новый запрос не возвращают плитки."""
    html = _html(_seed(), q="Pizza", ansicht="liste")
    tab = re.search(r'<a href="([^"]*)" data-portal-tab="product"', html).group(1)
    assert "ansicht=liste" in tab.replace("&amp;", "&")
    head = html.split("data-portal-header-search", 1)[1].split("</form>", 1)[0]
    assert 'name="ansicht" value="liste"' in head
