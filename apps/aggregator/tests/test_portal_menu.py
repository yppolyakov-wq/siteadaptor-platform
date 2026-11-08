"""PH-2: мега-меню «Kategorien» и полоса разделов портала."""

import html as html_mod
import re

import pytest

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import portal_icons
from apps.aggregator.tests.test_portal_discover import _html, _portal, _seed_everything
from apps.core import city_categories as cc

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def test_every_section_has_an_svg_icon():
    for s in cc.SECTIONS:
        assert s.key in portal_icons.SECTION_ICONS, s.key


def test_menu_lists_only_filled_sections_with_counts():
    portal = _portal()
    _seed_everything()
    present = home.presence(home.L.objects.all())
    menu = home.menu_sections(present, "/")
    assert menu and all(s["count"] == present["sections"][s["key"]] for s in menu)
    keys = {s["key"] for s in menu}
    assert keys == {k for k, n in present["sections"].items() if n}
    for s in menu:
        assert sum(c["count"] for c in s["subs"]) == s["count"]
    assert portal


def test_menu_links_lead_to_the_same_counts():
    portal = _portal()
    _seed_everything()
    body = _html(portal)
    rows = re.findall(r'<h3 id="pmp-([^"]+)"[^>]*>(\d+)', body)
    assert rows
    for url in re.findall(r'href="([^"]+)" data-portal-menu-section=', body):
        params = dict(p.split("=") for p in html_mod.unescape(url).split("?", 1)[1].split("&"))
        feed = _html(portal, **params)
        assert "data-card-title" in feed


def test_home_has_menu_strip_anchor_and_no_csrf():
    portal = _portal()
    _seed_everything()
    body = _html(portal)
    assert 'id="portal-menu"' in body
    # PH-11a: полоса иконок разделов снята — навигация по разделам только через мега-меню.
    assert "data-portal-strip" not in body
    assert 'id="kategorien"' in body
    assert 'href="/#kategorien" data-portal-menu-open' in body  # без JS — якорь главной
    assert "csrfmiddlewaretoken" not in body
    assert "<script" not in body.split('id="portal-menu"', 1)[1].split("</dialog>", 1)[0]


def test_feed_menu_is_cached(django_assert_max_num_queries):
    from django.core.cache import cache

    portal = _portal()
    _seed_everything()
    cache.clear()
    first = _html(portal, kind="alle")
    assert 'id="portal-menu"' in first
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as cold:
        cache.clear()
        _html(portal, kind="alle")
    with CaptureQueriesContext(connection) as warm:
        _html(portal, kind="alle")
    assert len(warm.captured_queries) < len(cold.captured_queries)


def test_mobile_bottom_nav_and_swipe_rows():
    portal = _portal()
    _seed_everything()
    # resolver_match ставит роутер — RequestFactory его не знает (раньше aria-current давали
    # снятые вкладки главной, PH-11d2): собираем запрос как роутер.
    from django.urls import resolve

    from apps.aggregator import portal_views
    from apps.aggregator.tests.test_portal_discover import _get

    req = _get(portal)
    req.resolver_match = resolve("/")
    body = portal_views.portal_home(req).content.decode()
    nav = body.split("data-portal-bottom-nav", 1)[1].split("</nav>", 1)[0]
    assert 'aria-current="page"' in nav
    # контент главной на телефоне: quad-лента (PH-11d1), «Das Beste» (PH-11d2) или ряды-страховка
    assert any(m in body for m in ("data-card-row", "data-home-quad", "data-home-best"))
    assert "csrfmiddlewaretoken" not in body
