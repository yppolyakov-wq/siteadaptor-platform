"""PH-5: быстрые фильтры главной — только ссылки, каждая ведёт в непустую ленту."""

import html as html_mod
import re
from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit

import pytest
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _seed():
    _listing(
        "promotion",
        "Pizza-Deal",
        city_category="restaurants",
        discount_percent=30,
        new_price=5,
        ends_at=timezone.now() + timedelta(hours=3),
    )
    _listing("product", "Brot", city_category="brot-backwaren", new_price=3, district="mitte")


def test_quick_filters_are_links_into_the_feed():
    portal = _portal()
    _seed()
    body = _html(portal)
    assert "data-home-quick-filters" in body and "csrfmiddlewaretoken" not in body
    urls = re.findall(r'href="([^"]+)" rel="nofollow" data-quick-filter=', body)
    urls += re.findall(r'href="([^"]+)" rel="nofollow" class="flex items-center min-h', body)
    assert urls
    for url in urls:
        query = dict(parse_qsl(urlsplit(html_mod.unescape(url)).query))
        assert set(query) <= home.FEED_PARAMS, url  # иначе корень откроет главную
        assert "data-portal-home" not in _html(portal, **query), url


def test_near_me_hidden_without_js_and_all_filters_opens_drawer_anchor():
    portal = _portal()
    _seed()
    body = _html(portal)
    assert re.search(r"<button[^>]*hidden[^>]*data-near-me", body)
    assert "?kind=alle#filter" in body


def test_empty_toggles_are_not_shown():
    assert home.quick_filters({"offers": 0, "new_week": 0}, 0, "/") == []
    keys = [f["key"] for f in home.quick_filters({"offers": 2, "new_week": 0}, 1, "/")]
    assert keys == ["offen", "heute"]
