"""Г5: «живой» район портала (порог N бизнесов) + хвост «Auch in der Nähe».

План — docs/g5-district-threshold-plan-2026-10-17.md §7.
"""

import re
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import district_liveness, portal_views
from apps.aggregator import search as search_engine
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.core import districts
from apps.tenants.tests.factories import TenantFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.urls("config.urls_portal"),
    pytest.mark.usefixtures("isolated_ratelimit"),
]

_n = iter(range(100_000))


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
        "title": {"de": "Angebote in Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(title, district, *, schema=None, **kw):
    i = next(_n)
    kw.setdefault("business_type", "bakery")
    kw.setdefault("business_name", f"Laden {i}")
    return AggregatorListing.objects.create(
        tenant_schema=schema or f"g5t{i}",
        tenant_slug=f"g5x{i}",
        city="Solingen",
        district=district,
        source_ref=f"g5s{i}",
        title={"de": title},
        detail_url=f"https://x{i}.siteadaptor.de/p/{i}/",
        is_active=True,
        **kw,
    )


def _businesses(district, n, *, prefix="Biz", **kw):
    return [_listing(f"{prefix}{district}{k}", district, **kw) for k in range(n)]


def _html(portal, path="/stadtteil/graefrath/", district="graefrath", **params):
    req = RequestFactory().get(path, params)
    req.portal = portal
    kw = {"district": district} if district else {}
    return portal_views.portal_home(req, **kw).content.decode()


def _tail_slugs(html):
    return re.findall(r'data-district-tail="([^"]+)"', html)


def _tail_hrefs(html):
    return re.findall(r'href="([^"]+)"[^>]*data-district-tail-more', html)


# --- реестр -----------------------------------------------------------------------------


def test_neighbors_registry_is_symmetric_and_complete():
    for key, table in districts.NEIGHBORS.items():
        slugs = {d.slug for d in districts.CITIES[key]}
        assert set(table) == slugs
        for slug, near in table.items():
            assert near, slug
            assert slug not in near
            for other in near:
                assert other in slugs
                assert slug in table[other], (slug, other)


def test_neighbors_unknown_city_or_slug_is_empty():
    assert districts.neighbors("Hilden", "mitte") == ()
    assert districts.neighbors("Solingen", "atlantis") == ()
    assert districts.neighbors("Solingen", "") == ()
    assert districts.neighbors("Solingen-Ohligs", "graefrath") == ("wald", "mitte")


# --- подсчёт ----------------------------------------------------------------------------


def test_business_with_many_listings_and_two_types_counts_once():
    p = _portal()
    for k in range(5):
        _listing(f"Brot{k}", "wald", schema="one", business_type="bakery")
    _listing("Kaffee", "wald", schema="one", business_type="cafe")
    assert district_liveness.count_for(p, "wald") == 1
    assert district_liveness.count_for(p, "wald", "bakery") == 1


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=3)
def test_exactly_n_is_live_and_n_minus_one_gets_tail():
    p = _portal()
    _businesses("wald", 1, prefix="Nachbar")
    _businesses("graefrath", 3)
    html = _html(p)
    assert _tail_slugs(html) == [] and "data-district-sparse" not in html
    AggregatorListing.objects.filter(title__de="Bizgraefrath2").delete()
    cache.clear()
    html = _html(p)
    assert _tail_slugs(html) == ["wald"] and "data-district-sparse" in html


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=4)
def test_demo_counts_only_on_preview_portal():
    _businesses("graefrath", 3)
    _businesses("graefrath", 2, prefix="Demo", is_demo=True)
    real = _portal()
    preview = _portal(host="vorschau.siteadaptor.de", show_demo=True)
    assert not district_liveness.is_live(real, "graefrath")
    assert district_liveness.is_live(preview, "graefrath")


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=2)
def test_withheld_business_neither_counts_nor_appears_in_tail():
    p = _portal()
    hidden = TenantFactory(schema_name="g5hidden", email_pending=True)
    _listing("Sichtbar", "graefrath")
    _listing("Versteckt", "graefrath", schema=hidden.schema_name)
    _listing("VersteckterNachbar", "wald", schema=hidden.schema_name)
    _listing("Nachbar", "wald")
    assert district_liveness.count_for(p, "graefrath") == 1
    html = _html(p)
    assert "Nachbar" in html and "VersteckterNachbar" not in html


def test_listing_without_district_counts_nowhere():
    p = _portal()
    _listing("Irgendwo", "")
    assert district_liveness.business_counts(p) == {}


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=0)
def test_zero_threshold_switches_feature_off():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("Nachbar", "wald")
    assert _tail_slugs(_html(p)) == []


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_cache_failure_falls_back_to_direct_count():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("Nachbar", "wald")
    with mock.patch.object(district_liveness.cache, "get", side_effect=RuntimeError("down")):
        html = _html(p)
    assert _tail_slugs(html) == ["wald"]


# --- хвост ------------------------------------------------------------------------------


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_tail_shows_only_neighbors_with_district_label():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("NachbarWald", "wald")
    _listing("FernBurg", "burg-hoehscheid")  # Gräfrath не граничит с Burg
    html = _html(p)
    assert _tail_slugs(html) == ["wald"]
    tail = html.split('data-district-tail="wald"', 1)[1]
    assert "NachbarWald" in tail and "· Wald" in tail
    assert "FernBurg" not in html


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_group_is_subset_of_its_more_link_feed():
    p = _portal()
    _listing("Hier", "graefrath")
    near = _businesses("wald", 3, prefix="W", listing_kind="product")
    _businesses("wald", 2, prefix="Angebot")  # другой вид — не в области kind=product
    html = _html(p, kind="product")
    hrefs = _tail_hrefs(html)
    assert len(hrefs) == 1 and "kind=product" in hrefs[0]
    href = hrefs[0].replace("&amp;", "&")
    path, _, query = href.partition("?")
    req = RequestFactory().get(href)
    req.portal = p
    feed = portal_views.portal_home(req, district="wald").content.decode()
    tail = html.split('data-district-tail="wald"', 1)[1]
    for item in near:
        offer = f"/angebot/{item.pk}/"
        assert offer in tail and offer in feed
    assert "Angebotwald" not in tail
    assert path == "/stadtteil/wald/"


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_empty_neighbor_skipped_dead_neighbor_shown():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("MitteEins", "mitte")  # Wald пуст → берётся следующий сосед (сам «мёртвый»)
    assert _tail_slugs(_html(p)) == ["mitte"]


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_no_neighbors_with_cards_no_section_and_no_promise():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("Fern", "burg-hoehscheid")
    html = _html(p)
    assert _tail_slugs(html) == [] and "data-district-sparse" not in html


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=50)
def test_tail_only_on_last_page():
    p = _portal()
    _businesses("graefrath", 30)
    _listing("Nachbar", "wald")
    first = _html(p)
    assert _tail_slugs(first) == []
    cursor = re.search(r"cursor=([^\"&]+)", first).group(1)
    from urllib.parse import unquote

    last = _html(p, cursor=unquote(cursor))
    assert _tail_slugs(last) == ["wald"]


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_tail_limits_per_business_and_groups_and_ignores_featured():
    from datetime import timedelta

    from django.utils import timezone

    p = _portal()
    _listing("Hier", "mitte")
    for k in range(5):
        _listing(f"Gross{k}", "graefrath", schema="gross")
    for slug in ("wald", "burg-hoehscheid", "ohligs-aufderhoehe-merscheid"):
        _businesses(slug, 8, prefix="N")
    html = _html(p, path="/stadtteil/mitte/", district="mitte")
    assert len(_tail_slugs(html)) == district_liveness.TAIL_NEIGHBORS
    graefrath = html.split('data-district-tail="graefrath"', 1)[1].split("data-district-tail=", 1)[
        0
    ]
    assert len(re.findall(r">Gross\d<", graefrath)) == district_liveness.TAIL_PER_BUSINESS
    # featured не поднимает порядок хвоста: тот же порядок с платной позицией
    pool = AggregatorListing.objects.filter(district="wald")
    before = [x.pk for x in district_liveness._pick(pool, ranked=False)]
    pool.filter(pk=before[-1]).update(featured_until=timezone.now() + timedelta(days=3))
    after = [x.pk for x in district_liveness._pick(pool, ranked=False)]
    assert before == after


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_jsonld_lists_only_district_cards():
    p = _portal()
    _listing("Hier", "graefrath")
    _listing("NachbarWald", "wald")
    html = _html(p)
    ld = html.split('application/ld+json">', 1)[1].split("</script>", 1)[0]
    assert "Hier" in ld and "NachbarWald" not in ld


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_preview_tail_from_demo_shows_vorschau_notice():
    p = _portal(show_demo=True)
    _listing("Hier", "graefrath")
    _listing("DemoNachbar", "wald", is_demo=True)
    html = _html(p)
    assert _tail_slugs(html) == ["wald"] and "data-demo-notice" in html


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_query_count_bounded(django_assert_max_num_queries):
    p = _portal()
    _listing("Hier", "graefrath")
    for slug in ("wald", "mitte"):
        _businesses(slug, 6, prefix="N")
    _html(p)  # прогрев кэшей
    with django_assert_max_num_queries(25):
        _html(p)
    for slug in ("wald", "mitte"):
        _businesses(slug, 10, prefix="M")
    with django_assert_max_num_queries(25):
        _html(p)


# --- поиск и фильтры ----------------------------------------------------------------------


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_tail_follows_query_and_hits_count_district_only():
    p = _portal()
    _listing("Pizza Hier", "graefrath")
    _listing("Pizza Nachbar", "wald")
    _listing("Brot Nachbar", "wald")
    with mock.patch.object(search_engine, "record") as rec:
        html = _html(p, q="Pizza")
    assert rec.call_count == 1
    tail = html.split('data-district-tail="wald"', 1)[1]
    assert "Pizza Nachbar" in tail and "Brot Nachbar" not in tail
    assert re.search(r"data-hit-count>1 Treffer", html)
    assert "q=Pizza" in _tail_hrefs(html)[0]


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_district_as_filter_gets_tail_and_raw_place_switches_it_off():
    p = _portal()
    _listing("Kuchen Hier", "wald")
    _listing("Kuchen Mitte", "mitte")
    html = _html(p, path="/", district=None, stadtteil="wald")
    assert "mitte" in _tail_slugs(html)
    html = _html(p, path="/", district=None, q="Kuchen in Wald")
    assert "mitte" in _tail_slugs(html)
    href = _tail_hrefs(html)[0]
    assert href == "/stadtteil/mitte/?q=Kuchen"  # без фразы района и без ?stadtteil=
    html = _html(p, path="/", district=None, q="Kuchen in Wald", roh="ort")
    assert _tail_slugs(html) == []


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_near_sort_has_no_tail():
    p = _portal()
    _listing("Hier", "graefrath", latitude=51.2, longitude=7.05)
    _listing("Nachbar", "wald", latitude=51.2, longitude=7.06)
    html = _html(p, lat="51.2", lng="7.05")
    assert _tail_slugs(html) == []


@override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=5)
def test_feed_and_follow_digest_stay_exact():
    from datetime import timedelta

    from django.utils import timezone

    from apps.aggregator import follow, open_feed
    from apps.aggregator.models import FollowSubscription, PortalUser

    _listing("Hier", "graefrath")
    _listing("Nachbar", "wald")
    req = RequestFactory().get("/feed.json", {"stadtteil": "graefrath"})
    params = open_feed.parse_params(req, city="Solingen")
    feed = open_feed.feed_pool(city="Solingen", business_type="", include_demo=False, params=params)
    assert [x.title["de"] for x in feed] == ["Hier"]
    user = PortalUser.objects.create(email="g5@test.de")
    sub = FollowSubscription(
        user=user,
        target_kind=FollowSubscription.TARGET_DISTRICT,
        target_key="graefrath",
        city="Solingen",
    )
    got = follow.items_for(sub, since=timezone.now() - timedelta(days=1))
    assert [x.title["de"] for x in got] == ["Hier"]
