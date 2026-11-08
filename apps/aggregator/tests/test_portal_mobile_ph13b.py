"""PH-13b: верх главной на телефоне по макету M5 — заголовок и быстрые чипы над слайдером,
слайдер 220 px, компактные quad-карточки. Десктоп: слайдер визуально первым (md:-order-1)."""

import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _two_quads():
    from apps.aggregator import search

    now = timezone.localtime()
    _listing(
        "promotion",
        "Feierabendtüte",
        ends_at=min(now + timedelta(minutes=30), now.replace(hour=23, minute=59)),
    )
    start, end = search.date_window("wochenende")
    begin = max(start, timezone.now() + timedelta(minutes=10))
    if begin >= end:
        pytest.skip("окно выходных закончилось")
    _listing("event", "Kinderkino", city_category="kino", starts_at=begin, ends_at=end)
    _listing("promotion", "Brötchen")


def test_h1_comes_before_the_slider_in_the_dom():
    _two_quads()
    html = _html(_portal())
    assert html.index('id="hero-h"') < html.index("data-portal-slider")
    # на десктопе слайдер остаётся визуально первым
    assert re.search(r'<div class="md:-order-1">\s*<section[^>]*data-portal-slider', html)


def test_quick_chips_mirror_the_quad_cards_and_hide_on_desktop():
    _two_quads()
    html = _html(_portal())
    nav = re.search(r"<nav[^>]*data-quick-chips[^>]*>.*?</nav>", html, re.S)
    assert nav and "md:hidden" in nav.group(0)
    chips = re.findall(r'href="([^"]+)"', nav.group(0))
    more = re.findall(
        r'<a href="([^"]+)" rel="nofollow" class="self-start', html
    )  # «Alle anzeigen» карточек
    assert chips and set(chips) == set(more)
    assert "featured" not in nav.group(0)


def test_slider_is_compact_on_phones():
    _two_quads()
    html = _html(_portal())
    slider = re.search(r"<section[^>]*data-portal-slider.*?</section>", html, re.S).group(0)
    assert "min-h-[300px]" not in slider and "min-h-[220px]" in slider
    prev = re.search(r"<button[^>]*data-slider-prev[^>]*>", slider).group(0)
    assert "max-md:hidden" in prev  # на телефоне — свайп и точки


def test_quad_cards_are_narrow_and_landscape_on_phones():
    _two_quads()
    html = _html(_portal())
    card = re.search(r'<div role="group" data-quad="[a-z]+"[^>]*>', html).group(0)
    assert "max-sm:w-[296px]" in card and "max-sm:p-3.5" in card
    assert "max-sm:aspect-[4/3]" in html
