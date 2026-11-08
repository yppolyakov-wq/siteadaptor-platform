"""PH-13c: низ главной на телефоне по макету M5 — «Das Beste» с головой-строкой и тремя
разделами, ленты «Geschäfte»/«Neu in», «Top-Aktionen» строкой, подвал аккордеонами.
Десктоп не меняется (все правки — `max-sm:`/`md:`)."""

import re

import pytest
from django.core.cache import cache

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

# шесть РАЗНЫХ разделов справочника (по категории из каждого)
SIX = ("restaurants", "brot-backwaren", "friseur", "damenmode", "moebel", "fitness")


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _best(html):
    return re.search(r"<section[^>]*data-home-best.*?</section>", html, re.S).group(0)


def test_best_head_is_a_row_on_phones():
    for cat in SIX[:3]:
        _listing("promotion", f"In {cat}", city_category=cat)
    best = _best(_html(_portal()))
    head = re.search(r'<div class="relative h-28[^"]*"', best).group(0)
    assert "max-sm:h-auto" in head and "max-sm:flex" in head
    h3 = re.search(r"<h3 class=\"[^\"]*\">", best).group(0)
    assert "max-sm:static" in h3 and "max-sm:text-gray-900" in h3  # название — строкой, не на фото


def test_best_shows_three_on_phones_and_links_to_the_rest():
    for cat in SIX:
        _listing("promotion", f"In {cat}", city_category=cat)
    best = _best(_html(_portal()))
    assert best.count("data-best-section=") == 6  # в DOM все — запросы прежние
    assert "max-sm:[&>article:nth-child(n+4)]:hidden" in best
    link = re.search(r"<a[^>]*data-best-all[^>]*>", best).group(0)
    assert "md:hidden" in link and "data-portal-menu-open" in link


def test_best_without_hidden_sections_has_no_extra_link():
    for cat in SIX[:3]:
        _listing("promotion", f"In {cat}", city_category=cat)
    assert "data-best-all" not in _best(_html(_portal()))


def test_busy_is_a_swipe_lane_on_phones():
    for schema in ("a1", "b2", "c3"):
        for i in range(3):
            _listing("promotion", f"{schema} {i}", schema=schema)
    html = _html(_portal())
    busy = re.search(r"<section[^>]*data-home-busy.*?</section>", html, re.S).group(0)
    ul = re.search(r"<ul[^>]*>", busy).group(0)
    assert "max-sm:flex" in ul and "max-sm:overflow-x-auto" in ul
    li = re.search(r"<li[^>]*data-busy[^>]*>", busy).group(0)
    assert "relative" in li and "max-sm:w-40" in li  # грабля sr-only в ленте


def test_footer_columns_fold_on_phones():
    html = _html(_portal())
    foot = re.search(r"<footer[^>]*data-portal-footer.*?</footer>", html, re.S).group(0)
    folds = re.findall(r"<details[^>]*data-fold[^>]*>", foot)
    assert len(folds) >= 3 and all(" open" in d for d in folds)  # без JS всё раскрыто
    for fid in ("foot-discover", "foot-business", "foot-legal"):
        assert foot.count(f'id="{fid}"') == 1
    assert "data-fold" in foot.split("</footer>")[0] and "matchMedia" in foot
