"""PH-11d1b (макет K1): quad-карточки главной — Endet heute · Beliebt/Jetzt geöffnet · Neu ·
Am Wochenende. Пустая карточка не рендерится, показанное ⊆ ленты, платное не попадает."""

import re
from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator.models import AggregatorListing, PortalStat
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    """Корень портала и «Beliebt» кэшируются (Redis переживает прогоны и делится xdist)."""
    cache.clear()
    yield
    cache.clear()


def _quads(html):
    return re.findall(r'data-quad="([a-z]+)"', html)


def _quad(html, key):
    return html.split(f'data-quad="{key}"', 1)[1].split("</section>", 1)[0]


def _ends_today():
    now = timezone.localtime()
    eod = now.replace(hour=23, minute=59, second=0, microsecond=0)
    return min(now + timedelta(minutes=30), max(eod, now + timedelta(seconds=30)))


def _views(listing, n, days_ago=0):
    PortalStat.objects.create(
        day=date.today() - timedelta(days=days_ago),
        tenant_schema=listing.tenant_schema,
        listing_kind=listing.listing_kind,
        source_ref=listing.source_ref,
        listing_id=listing.pk,
        action="view",
        channel="portal",
        count=n,
    )


def _second_card():
    """Ряд карточек — от двух: вторая — «Am Wochenende» (датированное из «Freizeit»)."""
    from apps.aggregator import search

    start, end = search.date_window("wochenende")
    begin = max(start, timezone.now() + timedelta(minutes=10))
    if begin >= end:
        pytest.skip("окно выходных закончилось")
    _listing("event", "Kinderkino", city_category="kino", starts_at=begin, ends_at=end)


def test_ending_today_card_links_to_sorted_offers():
    _second_card()
    _listing("promotion", "Heute weg", ends_at=_ends_today())
    _listing("promotion", "Noch lange", ends_at=timezone.now() + timedelta(days=5))
    html = _html(_portal())
    card = _quad(html, "endet")
    assert "Heute weg" in card and "Noch lange" not in card
    assert "kind=angebote&amp;sort=endet" in card


def test_empty_cards_are_not_rendered():
    _listing("product", "Brot", city_category="brot-backwaren")
    html = _html(_portal())
    assert "endet" not in _quads(html) and "wochenende" not in _quads(html)


def test_popular_needs_threshold_else_no_popular_card():
    portal = _portal()
    _second_card()
    items = [_listing("promotion", f"Hit {i}") for i in range(4)]
    for item in items[:3]:
        _views(item, 5)
    _views(items[3], 2)  # ниже порога — «Beliebt» не набирается
    assert "beliebt" not in _quads(_html(portal))
    _views(items[3], 1, days_ago=6)  # 2+1 = 3 за неделю (сумма по дням)
    cache.clear()
    card = _quad(_html(portal), "beliebt")
    assert all(f"Hit {i}" in card for i in range(4))


def test_featured_never_in_popular():
    portal = _portal()
    _second_card()
    items = [_listing("promotion", f"Hit {i}") for i in range(4)]
    paid = _listing("promotion", "Bezahlt", featured_until=timezone.now() + timedelta(days=1))
    for item in [*items, paid]:
        _views(item, 9)
    quads = "".join(_quad(_html(portal), k) for k in _quads(_html(portal)))
    assert "Bezahlt" not in quads


def test_popular_ids_query_is_cached():
    portal = _portal()
    items = [_listing("promotion", f"Hit {i}") for i in range(4)]
    for item in items:
        _views(item, 5)
    now = timezone.now()
    first = home._popular_ids(portal.pk, now)
    PortalStat.objects.all().delete()
    assert home._popular_ids(portal.pk, now) == first  # кэш 15 минут


def test_cards_do_not_repeat_items():
    portal = _portal()
    for i in range(3):
        _listing("promotion", f"Neu und endet {i}", ends_at=_ends_today())
    html = _html(portal)
    shown = re.findall(r'data-quad="[a-z]+".*?</section>', html, flags=re.S)
    titles = [t for s in shown for t in re.findall(r"Neu und endet \d", s)]
    assert len(titles) == len(set(titles))


def test_single_card_is_not_a_row():
    _listing("promotion", "Heute weg", ends_at=_ends_today())
    assert "data-home-quad" not in _html(_portal())


def test_quad_cards_sit_below_heading_and_link_names_are_unique():
    _second_card()
    _listing("promotion", "Heute weg", ends_at=_ends_today())
    html = _html(_portal())
    assert html.index('id="hero-h"') < html.index("data-home-quad")
    card = _quad(html, "endet")
    assert '<span class="sr-only">: Endet heute</span>' in card


def test_pool_only_queries_stay_bounded(django_assert_max_num_queries):
    portal = _portal()
    for i in range(6):
        _listing("promotion", f"Angebot {i}", ends_at=_ends_today())
    AggregatorListing.objects.update(is_active=True)
    with django_assert_max_num_queries(60):
        _html(portal)
