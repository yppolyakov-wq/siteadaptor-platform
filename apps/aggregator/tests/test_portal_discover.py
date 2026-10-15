"""T-8.19: главная городского портала «Entdecke <город>».

План — docs/t8-19-portal-home-plan-2026-10-15.md §4.
"""

import re
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import portal_home_blocks as home
from apps.aggregator import portal_views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.aggregator.views import listings_for

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]

_n = iter(range(10_000))


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": "solingen.siteadaptor.de",
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Solingen lokal"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(kind, title, *, schema=None, **kw):
    i = next(_n)
    return AggregatorListing.objects.create(
        tenant_schema=schema or f"t{i}",
        tenant_slug=f"x{i}",
        business_name=f"Laden {i}",
        city="Solingen",
        listing_kind=kind,
        source_ref=f"{title}-{i}",
        title={"de": title},
        detail_url="https://x.siteadaptor.de/",
        **kw,
    )


def _get(portal, path="/", ip="10.0.0.1", **params):
    req = RequestFactory().get(path, params, REMOTE_ADDR=ip)
    req.portal = portal
    return req


def _html(portal, path="/", **params):
    return portal_views.portal_home(_get(portal, path, **params)).content.decode()


def _blocks(html):
    return re.findall(r'data-home-block="([^"]+)"', html)


# --- режим главной ------------------------------------------------------------------


def test_root_of_city_portal_is_home_and_tracking_params_keep_it():
    portal = _portal()
    _listing("promotion", "Herbstrabatt")
    assert "data-portal-home" in _html(portal)
    assert "data-portal-home" in _html(portal, utm_source="x", ch="qr")


@pytest.mark.parametrize(
    "params",
    [{"kind": "product"}, {"q": "brot"}, {"kat": "essen-gastronomie"}, {"neu": "1"}],
)
def test_feed_params_open_the_feed(params):
    portal = _portal()
    _listing("promotion", "Herbstrabatt")
    assert "data-portal-home" not in _html(portal, **params)


def test_vertical_portal_keeps_its_feed():
    portal = _portal(kind="vertical", city="", business_type="bakery", host="baecker.x.de")
    _listing("promotion", "Brot", business_type="bakery")
    assert "data-portal-home" not in _html(portal)


# --- пустое скрыто ------------------------------------------------------------------


def test_only_offers_shows_only_offers_block():
    portal = _portal()
    _listing("promotion", "Herbstrabatt")
    AggregatorListing.objects.update(created_at=timezone.now() - timedelta(days=30))
    html = _html(portal)
    assert _blocks(html) == ["angebote"]
    assert "data-portal-tabs" not in html  # «Alle» = единственная группа — переключать нечего


def test_empty_portal_has_search_and_empty_note_only():
    html = _html(_portal())
    assert "data-portal-search" in html and "data-home-empty" in html
    assert _blocks(html) == [] and "data-portal-tabs" not in html


def test_tab_without_data_is_hidden():
    portal = _portal()
    _listing("promotion", "Herbstrabatt")
    _listing("product", "Messer")
    html = _html(portal)
    assert 'data-portal-tab="product"' in html and 'data-portal-tab="event"' not in html
    _listing("event", "Konzert", starts_at=timezone.now() + timedelta(days=3))
    cache.clear()
    assert 'data-portal-tab="event"' in _html(portal)


def test_section_tiles_only_nonempty_with_counts():
    portal = _portal()
    _listing("promotion", "Pizza", city_category="restaurants")
    _listing("product", "Brot", city_category="brot-backwaren")
    _listing("product", "Brötchen", city_category="brot-backwaren")
    present = home.presence(listings_for(city="Solingen"))
    tiles = {t["key"]: t for t in home.section_tiles(present, "/")}
    assert set(tiles) == {"essen-gastronomie", "lebensmittel-getraenke"}
    assert tiles["lebensmittel-getraenke"]["count"] == 2
    assert tiles["essen-gastronomie"]["url"] == "/?kind=alle&kat=essen-gastronomie"
    assert 'data-section-tile="mode-accessoires"' not in _html(portal)


# --- objects.public() / демо ---------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"is_active": False},
        {"hidden_at": timezone.now()},
        {"ends_at": timezone.now() - timedelta(hours=1)},
    ],
)
def test_invisible_listings_never_reach_home(kw):
    portal = _portal()
    _listing("promotion", "Sichtbar")
    _listing("promotion", "Versteckt", city_category="restaurants", **kw)
    html = _html(portal)
    assert "Sichtbar" in html and "Versteckt" not in html
    assert 'data-section-tile="essen-gastronomie"' not in html


def test_withheld_tenant_never_reaches_home():
    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="t_hold", slug="hold", in_city_catalog=False)
    portal = _portal()
    _listing("promotion", "Sichtbar")
    _listing("promotion", "Versteckt", schema="t_hold")
    html = _html(portal)
    assert "Sichtbar" in html and "Versteckt" not in html


def test_past_event_never_reaches_home():
    portal = _portal()
    _listing("promotion", "Sichtbar")
    _listing("event", "Vorbei", starts_at=timezone.now() - timedelta(days=1))
    html = _html(portal)
    assert "Vorbei" not in html and 'data-portal-tab="event"' not in html


def test_demo_hidden_on_real_portal_and_shown_on_preview():
    _listing("promotion", "Echt")
    _listing("event", "Demo-Konzert", is_demo=True, starts_at=timezone.now() + timedelta(days=2))
    html = _html(_portal())
    assert "Demo-Konzert" not in html and 'data-portal-tab="event"' not in html
    cache.clear()
    AggregatorPortal.objects.all().delete()
    html = _html(_portal(show_demo=True))
    assert "Demo-Konzert" in html and "data-demo-notice" in html


# --- featured (UWG §5a) --------------------------------------------------------------


def test_featured_is_marked_separate_and_not_duplicated():
    portal = _portal()
    paid = _listing("promotion", "Bezahlt", featured_until=timezone.now() + timedelta(days=3))
    _listing("promotion", "Organisch")
    html = _html(portal)
    strip = html.split("data-home-featured", 1)[1].split("</section>", 1)[0]
    assert "Bezahlt" in strip and "★ Anzeige" in strip
    assert html.count(">Bezahlt<") == 1  # в блоках не повторяется
    paid.refresh_from_db()
    assert paid.featured_impressions == 1


def test_block_order_ignores_featured_until():
    base = listings_for(city="Solingen")
    a = _listing("promotion", "A", ends_at=timezone.now() + timedelta(days=1))
    b = _listing("promotion", "B", ends_at=timezone.now() + timedelta(days=2))
    first = [i.pk for i in home.home_blocks(base, city="Solingen", path="/")[0]["items"]]
    AggregatorListing.objects.filter(pk=b.pk).update(
        featured_until=timezone.now() + timedelta(days=5)
    )
    again = [i.pk for i in home.home_blocks(base, city="Solingen", path="/")[0]["items"]]
    assert first == again == [a.pk, b.pk]


# --- «Alle →» ведёт на работающую ленту (класс-замок) ---------------------------------


def _seed_everything():
    soon = timezone.now() + timedelta(days=2)
    _listing("promotion", "Pizza-Deal", city_category="restaurants", ends_at=soon)
    _listing("menu", "Festmenü", city_category="catering")
    _listing("product", "Messer", city_category="handgemachtes", is_new=True)
    _listing("product", "Brot", city_category="brot-backwaren", city_tags=["regional"])
    _listing("service", "Haarschnitt", city_category="friseur")
    _listing("service", "Kochkurs", city_category="restaurants")
    _listing("business", "Laden am Markt", city_category="restaurants")
    _listing("event", "Stadtfest", city_category="events", starts_at=soon)
    _listing("stay", "Zimmer", city_category="hotels")


def test_every_block_more_link_contains_all_block_cards():
    portal = _portal()
    _seed_everything()
    base = listings_for(city="Solingen")
    blocks = home.home_blocks(base, city="Solingen", path="/")
    assert {b["key"] for b in blocks} == {b.key for b in home.BLOCKS}
    for block in blocks:
        query = urlsplit(block["more_url"]).query
        scope = home.parse_scope(RequestFactory().get(f"/?{query}"))
        feed = home.apply_scope(base, scope)
        assert {i.pk for i in block["items"]} <= set(feed.values_list("pk", flat=True))
        html = _html(portal, **dict(p.split("=") for p in query.split("&")))
        assert block["items"][0].title["de"] in html, block["key"]


# --- лимиты ---------------------------------------------------------------------------


def test_block_limit_per_business_and_no_duplicates_between_blocks():
    for i in range(20):
        _listing("product", f"Ware {i}", schema="big")
    for i in range(10):
        _listing("product", f"Klein {i}")
    blocks = home.home_blocks(listings_for(city="Solingen"), city="Solingen", path="/")
    by_key = {b["key"]: b["items"] for b in blocks}
    assert len(by_key["produkte"]) == home.BLOCK_LIMIT
    assert sum(1 for i in by_key["produkte"] if i.tenant_schema == "big") <= 2
    pks = [i.pk for items in by_key.values() for i in items]
    assert len(pks) == len(set(pks))


def test_neu_block_and_neu_feed():
    old = timezone.now() - timedelta(days=30)
    _listing("promotion", "Alt")
    _listing("product", "Neu-Ware", is_new=True)
    AggregatorListing.objects.update(created_at=old)
    blocks = {
        b["key"]: b for b in home.home_blocks(listings_for(city="Solingen"), city="X", path="/")
    }
    titles = [i.title["de"] for i in blocks["produkte"]["items"]]
    assert "Neu-Ware" in titles
    feed = _html(_portal(), neu="1", kind="alle")
    assert "Neu-Ware" in feed and "Alt" not in feed


def test_produkte_skips_sold_out_and_puts_regional_first():
    _listing("product", "Ausverkauft", availability="sold_out")
    _listing("product", "Normal")
    _listing("product", "Regional", city_tags=["regional"])
    AggregatorListing.objects.filter(title__de="Regional").update(
        created_at=timezone.now() - timedelta(days=60)
    )
    blocks = {
        b["key"]: b
        for b in home.home_blocks(listings_for(city="Solingen"), city="Solingen", path="/")
    }
    titles = [i.title["de"] for i in blocks["produkte"]["items"]]
    assert titles[0] == "Regional" and "Ausverkauft" not in titles
    assert "Ausverkauft" in _html(_portal(), kind="product")


def test_produkte_title_has_city():
    _listing("product", "Messer")
    html = _html(_portal())
    assert "Produkte aus Solingen" in html


# --- группы ленты и поиск --------------------------------------------------------------


def test_feed_groups_and_legacy_kind():
    portal = _portal()
    _seed_everything()
    angebote = _html(portal, kind="angebote")
    assert "Pizza-Deal" in angebote and "Zimmer" in angebote and "Messer" not in angebote
    alle = _html(portal, kind="alle")
    assert "Messer" in alle and "Haarschnitt" in alle and "Stadtfest" in alle
    legacy = _html(portal, kind="promotion")
    assert 'data-portal-tab="angebote" aria-current="page"' in legacy
    assert _html(portal, kind="zzz")  # мусор — лента, не 500


def test_search_finds_products_and_carries_query():
    portal = _portal()
    _listing("product", "Winterjacke")
    _listing("promotion", "Herbstrabatt")
    html = _html(portal, q="winterjacke")
    assert "Winterjacke" in html and "Herbstrabatt" not in html
    assert 'value="winterjacke"' in html


def test_search_is_rate_limited(settings):
    from apps.core import ratelimit

    portal = _portal()
    ip = "10.9.9.9"
    for _i in range(portal_views.SEARCH_RATE_LIMIT):
        ratelimit.hit("portal-search", ip, limit=10_000, window=60)
    resp = portal_views.portal_home(_get(portal, ip=ip, q="x"))
    assert resp.status_code == 429


# --- запросы / кэш ----------------------------------------------------------------------


def test_query_count_does_not_grow_with_data(django_assert_max_num_queries):
    portal = _portal()
    _seed_everything()
    with django_assert_max_num_queries(14):
        portal_views.portal_home(_get(portal))
    for i in range(30):
        _listing("product", f"Viel {i}", city_category="brot-backwaren")
    cache.clear()
    with django_assert_max_num_queries(14):
        portal_views.portal_home(_get(portal))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PUBLIC_PAGE_CACHE_TTL=60,
)
def test_home_is_cached_without_csrf_token():
    cache.clear()
    portal = _portal()
    _listing("promotion", "Herbstrabatt")
    body = _html(portal)
    assert "data-portal-home" in body and "csrfmiddlewaretoken" not in body
    assert cache.get("pubpage2:testserver:/:de") is not None


def test_ld_lists_block_cards():
    _listing("product", "Messer", new_price=Decimal("10"))
    html = _html(_portal())
    assert '"@type": "CollectionPage"' in html or '"CollectionPage"' in html
    assert "Messer" in html.split("application/ld+json", 1)[1]
