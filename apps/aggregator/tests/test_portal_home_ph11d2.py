"""PH-11d2 (макет K1): «Das Beste aus jedem Bereich», «Geschäfte», «Top-Aktionen»; фидбэк
владельца 2026-11-08: карточка «Am Wochenende», язык в шапке списком, ширина на весь экран."""

import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import search
from apps.aggregator.models import AggregatorListing, FavoriteListing, PortalUser
from apps.aggregator.tests.test_portal_discover import _html, _listing, _portal

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _section(html, key):
    return html.split(f'data-best-section="{key}"', 1)[1].split("</article>", 1)[0]


def _weekend_event(title, **kw):
    start, end = search.date_window("wochenende")
    begin = max(start, timezone.now() + timedelta(minutes=10))
    if begin >= end:
        pytest.skip("окно выходных закончилось")
    return _listing("event", title, city_category="kino", starts_at=begin, ends_at=end, **kw)


# --- «Das Beste aus jedem Bereich» --------------------------------------------------------


def test_best_rows_are_contained_in_section_feed_and_link_counts_match():
    portal = _portal()
    for i in range(4):
        _listing("promotion", f"Essen {i}", city_category="restaurants")
    _listing("product", "Brot", city_category="brot-backwaren")
    html = _html(portal)
    card = _section(html, "essen-gastronomie")
    assert card.count("<li") == 3  # je 3
    link = re.search(r'href="([^"]+)" rel="nofollow" data-best-more="(\d+)"', card)
    params = dict(
        p.split("=") for p in link.group(1).replace("&amp;", "&").split("?", 1)[1].split("&")
    )
    feed = _html(portal, **params)
    assert link.group(2) == "4" and len(re.findall("data-card-title", feed)) == 4
    for title in re.findall(r"Essen \d", card):
        assert title in feed


def test_best_carries_the_kategorien_anchor():
    _listing("promotion", "Essen", city_category="restaurants")
    html = _html(_portal())
    assert 'data-home-best id="kategorien"' in html
    assert html.count('id="kategorien"') == 1


def test_best_never_shows_paid_or_the_deal_again():
    _listing(
        "promotion",
        "Deal",
        city_category="restaurants",
        discount_percent=50,
        new_price=5,
        image={"url": "https://x.test/a.jpg"},
    )
    _listing(
        "promotion",
        "Bezahlt",
        city_category="restaurants",
        featured_until=timezone.now() + timedelta(days=1),
    )
    _listing("promotion", "Organisch", city_category="restaurants")
    html = _html(_portal())
    card = _section(html, "essen-gastronomie")
    assert "Organisch" in card and "Bezahlt" not in card and ">Deal<" not in card


def test_best_dot_marks_ending_today_and_has_text_for_screen_readers():
    now = timezone.localtime()
    ends = min(
        now + timedelta(minutes=30),
        max(now.replace(hour=23, minute=59), now + timedelta(seconds=30)),
    )
    _listing("promotion", "Heute weg", city_category="restaurants", ends_at=ends)
    card = _section(_html(_portal()), "essen-gastronomie")
    assert "bg-amber-700" in card and "endet heute / wenige übrig" in card


# --- «Geschäfte» и «Top-Aktionen» ---------------------------------------------------------


def test_busy_businesses_need_three_and_count_offers():
    portal = _portal()
    for schema, n in (("a1", 3), ("b2", 2)):
        for i in range(n):
            _listing("promotion", f"{schema} {i}", schema=schema)
    assert "data-home-busy" not in _html(portal)
    _listing("promotion", "c3 0", schema="c3")
    cache.clear()
    busy = _html(portal).split("data-home-busy", 1)[1].split("</section>", 1)[0]
    assert busy.count("data-busy=") == 3 and "3 Angebote" in busy


def test_top_actions_need_two_with_two_saves_and_never_paid():
    portal = _portal()
    users = [PortalUser.objects.create(email=f"u{i}@x.test") for i in range(3)]
    a = _listing("promotion", "Gemerkt A")
    b = _listing("promotion", "Gemerkt B")
    paid = _listing("promotion", "Bezahlt", featured_until=timezone.now() + timedelta(days=1))
    for u in users:
        FavoriteListing.objects.create(user=u, listing=a)
        FavoriteListing.objects.create(user=u, listing=paid)
    FavoriteListing.objects.create(user=users[0], listing=b)
    assert "data-home-top" not in _html(portal)  # B — одно сохранение, порог не пройден
    FavoriteListing.objects.create(user=users[1], listing=b)
    cache.clear()
    top = _html(portal).split("data-home-top", 1)[1].split("</section>", 1)[0]
    assert "Gemerkt A" in top and "Gemerkt B" in top and "Bezahlt" not in top
    assert "3× gemerkt diese Woche" in top


def test_old_saves_do_not_count():
    users = [PortalUser.objects.create(email=f"u{i}@x.test") for i in range(2)]
    items = [_listing("promotion", f"Alt {i}") for i in range(2)]
    for u in users:
        for it in items:
            FavoriteListing.objects.create(user=u, listing=it)
    FavoriteListing.objects.update(created_at=timezone.now() - timedelta(days=8))
    assert home.top_actions(AggregatorListing.objects.all(), path="/") == []


# --- фидбэк владельца 2026-11-08 ----------------------------------------------------------


def test_weekend_card_keeps_its_events_from_open_now_card():
    """На проде «Kinderkino» и «Laternenabend» уходили в «Jetzt geöffnet», и карточки
    «Am Wochenende» не было: события выбирает карточка выходных, у «offen» событий нет."""
    from apps.tenants.tests.factories import TenantFactory

    always = {str(d): ["00:00", "23:59"] for d in range(7)}
    TenantFactory(schema_name="open1", slug="open1", opening_hours_structured=always)
    _weekend_event("Kinderkino", schema="open1")
    _weekend_event("Laternenabend", schema="open1")
    _listing("product", "Brot", schema="open1", city_category="brot-backwaren")
    html = _html(_portal())
    quads = re.findall(r'data-quad="([a-z]+)"', html)
    assert "wochenende" in quads
    weekend = html.split('data-quad="wochenende"', 1)[1].split("</a>\n  </div>", 1)[0]
    assert "Kinderkino" in weekend and "Laternenabend" in weekend
    if "offen" in quads:
        offen = html.split('data-quad="offen"', 1)[1].split('data-quad="', 1)[0]
        assert "Kinderkino" not in offen


def test_language_switch_in_header_is_a_dropdown():
    html = _html(_portal())
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert "data-lang-menu" in header and "lang-pill" not in header
    menu = header.split("data-lang-menu", 1)[1].split("</details>", 1)[0]
    assert menu.count("/sprache/?lang=") >= 2 and 'aria-current="true"' in menu


def test_portal_pages_are_full_width():
    html = _html(_portal())
    main = re.search(r"<main [^>]*>", html).group(0)
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert "max-w-" not in main and "max-w-[1392px]" not in header


def test_best_shows_full_rows_of_three():
    for cat in ("restaurants", "brot-backwaren", "friseur", "kino"):
        _listing("promotion", f"In {cat}", city_category=cat)
    html = _html(_portal())
    assert html.count("data-best-section=") == 3
