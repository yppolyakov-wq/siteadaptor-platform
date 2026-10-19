"""T-8.10d D-1c/D-1d: подписка на набор фильтров поиска («Benachrichtigen, wenn es so etwas gibt»).

План — docs/t8-10d-search-subscriptions-plan-2026-10-19.md §2. Замки написаны ДО кода.
E-mail/IP — uuid: счётчики rate-limit живут в общем Redis дольше теста.
"""

import uuid
from datetime import timedelta

import pytest
from django.core import signing
from django.http import QueryDict
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import follow, follow_digest, follow_query, follow_views, portal_views
from apps.aggregator.models import (
    AggregatorListing,
    AggregatorPortal,
    FollowSubscription,
    PortalUser,
    SearchQueryLog,
)
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

OHLIGS = "ohligs-aufderhoehe-merscheid"
CITY = "Solingen"


def _email():
    return f"{uuid.uuid4().hex}@kunde.test"


def _portal(**kw):
    host = kw.pop("host", f"{uuid.uuid4().hex[:8]}.solingen.test")
    defaults = {"kind": "city", "city": CITY, "title": {"de": "Solingen"}, "is_active": True}
    defaults.update(kw)
    return AggregatorPortal.objects.create(host=host, **defaults)


def _tenant(**kw):
    kw.setdefault("city", CITY)
    return TenantFactory(**kw)


def _listing(tenant, **kw):
    defaults = {
        "tenant_schema": tenant.schema_name,
        "tenant_slug": tenant.slug,
        "business_name": tenant.name,
        "business_type": tenant.business_type,
        "city": CITY,
        "listing_kind": AggregatorListing.KIND_PRODUCT,
        "source_ref": uuid.uuid4().hex,
        "title": {"de": "Tomaten"},
        "detail_url": f"https://{tenant.slug}.siteadaptor.de/p/1/",
        "is_active": True,
        "city_category": "obst-gemuese",
        "district": OHLIGS,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _qd(**params):
    qd = QueryDict(mutable=True)
    for k, v in params.items():
        for item in v if isinstance(v, list) else [v]:
            qd.appendlist(k, item)
    return qd


def _req(method, path, data=None, portal=None, user=None):
    from django.contrib.sessions.middleware import SessionMiddleware

    factory = getattr(RequestFactory(), method)
    request = factory(path, data or {}, HTTP_X_FORWARDED_FOR=f"10.{uuid.uuid4().int % 255}.1.1")
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = portal
    if user is not None:
        request.session["portal_user_id"] = user.pk
    return request


def _query_sub(user, portal, params, *, confirmed_days_ago=1):
    target = follow.parse_target(_qd(art="suche", **params), portal=portal)
    assert target is not None and target.kind == "query", target
    sub = follow.follow_now(user, target, frequency="daily", portal=portal)
    FollowSubscription.objects.filter(pk=sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=confirmed_days_ago)
    )
    sub.refresh_from_db()
    return sub


# --- канонизация ------------------------------------------------------------------------


def test_canonical_is_sorted_whitelisted_and_order_independent():
    a = follow_query.canonical(_qd(q="Tomaten", stadtteil=OHLIGS, marke="Bio Hof"), city=CITY)
    b = follow_query.canonical(_qd(marke="Bio Hof", stadtteil=OHLIGS, q="Tomaten"), city=CITY)
    assert a == b
    assert [k for k, _v in a] == ["q", "stadtteil", "marke"]
    assert follow_query.key(a) == follow_query.key(b)


def test_garbage_and_unknown_params_dropped():
    pairs = follow_query.canonical(
        _qd(q="Brot", foo="bar", kat="nicht-da", stadtteil="mond", utm_source="x"), city=CITY
    )
    assert pairs == (("q", "Brot"),)


def test_relative_time_and_geo_dropped():
    params = _qd(
        q="Brot",
        datum="heute",
        offen="1",
        umkreis="5",
        sort="neu",
        lat="51.1",
        lng="7.0",
        cursor="abc",
    )
    assert follow_query.canonical(params, city=CITY) == (("q", "Brot"),)
    assert set(follow_query.dropped(params)) == {"datum", "offen", "umkreis", "sort", "lat", "lng"}


def test_intent_resolved_into_explicit():
    pairs = dict(follow_query.canonical(_qd(q="Tomaten unter 5 €"), city=CITY))
    assert pairs["q"].lower().startswith("tomaten")
    assert pairs["preis_bis"].startswith("5")


def test_empty_canonical_and_no_city_none():
    assert follow_query.canonical(_qd(), city=CITY) is None
    assert follow_query.canonical(_qd(sort="neu", datum="heute"), city=CITY) is None
    assert follow_query.canonical(_qd(q="Brot"), city="") is None


def test_q_scrubbed_and_capped():
    pairs = follow_query.canonical(_qd(q="ruf 0212 1234567 an", stadtteil=OHLIGS), city=CITY)
    assert dict(pairs).get("q", "") == ""
    long = follow_query.canonical(_qd(q="x" * 300), city=CITY)
    assert len(dict(long)["q"]) <= follow_query.Q_MAX


def test_single_legacy_maps_to_old_target():
    portal = _portal()
    tenant = _tenant()
    assert follow.parse_target(_qd(art="suche", stadtteil=OHLIGS), portal=portal) == follow.Target(
        "district", OHLIGS, CITY
    )
    sec = follow.parse_target(_qd(art="suche", kat="lebensmittel-getraenke"), portal=portal)
    assert sec.kind == "section"
    biz = follow.parse_target(_qd(art="suche", unternehmen=tenant.slug), portal=portal)
    assert biz == follow.Target("business", tenant.schema_name)


def test_category_stays_query():
    portal = _portal()
    target = follow.parse_target(_qd(art="suche", kat="obst-gemuese"), portal=portal)
    assert target.kind == "query" and target.query == (("kat", "obst-gemuese"),)


def test_business_scoped_query_rejected_when_demo_or_withheld():
    portal = _portal()
    for tenant in (_tenant(is_demo=True), _tenant(in_city_catalog=False)):
        assert (
            follow.parse_target(_qd(art="suche", unternehmen=tenant.slug, q="Brot"), portal=portal)
            is None
        )


def test_entdecken_requires_city():
    assert follow.parse_target(_qd(art="suche", q="Brot"), portal=None) is None
    target = follow.parse_target(_qd(art="suche", q="Brot", city="solingen"), portal=None)
    assert target.kind == "query" and target.city == CITY


# --- DOI, лимиты ------------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_doi_get_has_no_side_effects_post_creates_query_sub():
    portal = _portal()
    email = _email()
    target = follow.parse_target(_qd(art="suche", q="Tomaten", stadtteil=OHLIGS), portal=portal)
    token = follow.make_doi_token(
        email=email, target=target, frequency="daily", portal=portal, locale="de"
    )
    resp = follow_views.follow_confirm(_req("get", "/x/", portal=portal), token)
    assert resp.status_code == 200 and "Tomaten" in resp.content.decode()
    assert not PortalUser.objects.filter(email=email).exists()
    resp = follow_views.follow_confirm(_req("post", "/x/", portal=portal), token)
    assert b"data-follow-done" in resp.content
    sub = FollowSubscription.objects.get(user__email=email)
    assert sub.target_kind == "query" and sub.target_key == target.key
    assert follow_query.from_stored(sub.query) == target.query


@override_settings(ROOT_URLCONF="config.urls_public")
def test_doi_token_reconfirms_whitelist():
    payload = {
        "e": _email(),
        "k": "query",
        "t": follow_query.key((("lat", "51.1"), ("q", "Brot"))),
        "c": CITY,
        "f": "daily",
        "p": None,
        "l": "de",
        "q": [["lat", "51.1"], ["q", "Brot"]],
    }
    assert follow.target_from_payload(payload) is None
    assert follow.confirm(payload) is None
    token = signing.dumps(payload, salt=follow.DOI_SALT, compress=True)
    resp = follow_views.follow_confirm(_req("get", "/x/", portal=None), token)
    assert resp.status_code == 400


def test_no_instant_for_query():
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    sub = _query_sub(user, portal, {"q": "Brot", "stadtteil": OHLIGS})
    assert follow.set_frequency(sub, "instant") is False
    target = follow.target_from_follow(sub)
    assert follow.normalize_frequency("instant", target) == "daily"


def test_subscription_cap_enforced(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_query_follows": 2}
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    _query_sub(user, portal, {"q": "Brot"})
    _query_sub(user, portal, {"q": "Käse"})
    target = follow.parse_target(_qd(art="suche", q="Wurst"), portal=portal)
    with pytest.raises(follow.FollowLimitReached):
        follow.follow_now(user, target, frequency="daily", portal=portal)
    # повтор существующей — не новая подписка, лимит не мешает
    again = follow.parse_target(_qd(art="suche", q="Brot"), portal=portal)
    follow.follow_now(user, again, frequency="weekly", portal=portal)
    assert user.follows.count() == 2


def test_total_cap_enforced(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_follows": 1}
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    _query_sub(user, portal, {"q": "Brot"})
    with pytest.raises(follow.FollowLimitReached):
        follow.follow_now(
            user, follow.Target("district", OHLIGS, CITY), frequency="daily", portal=portal
        )


def test_unique_dedupe_same_query():
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    _query_sub(user, portal, {"q": "Brot", "stadtteil": OHLIGS})
    _query_sub(user, portal, {"stadtteil": OHLIGS, "q": "Brot"})
    assert user.follows.count() == 1


# --- выборка и сводка -------------------------------------------------------------------


def _setup():
    portal = _portal()
    tenant = _tenant()
    user = PortalUser.objects.create(email=_email())
    return portal, tenant, user


def test_query_items_match_filters_and_new_since():
    portal, tenant, user = _setup()
    sub = _query_sub(user, portal, {"q": "Tomaten", "stadtteil": OHLIGS})
    hit = _listing(tenant, title={"de": "Kirschtomaten"})
    _listing(tenant, title={"de": "Gurken"})
    _listing(tenant, title={"de": "Tomaten Wald"}, district="wald")
    old = _listing(tenant, title={"de": "Tomaten alt"})
    AggregatorListing.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    items = list(follow.items_for(sub, since=follow.since_for(sub)))
    assert [i.pk for i in items] == [hit.pk]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_alle_anzeigen_superset_of_mail(isolated_ratelimit):
    portal, tenant, user = _setup()
    other = _tenant()
    cases = [
        {"q": "Tomaten"},
        {"kat": "obst-gemuese"},
        {"marke": "Sonnenhof"},
        {"unternehmen": tenant.slug, "q": "Tomaten"},
        {"stadtteil": OHLIGS, "q": "Tomaten"},
    ]
    _listing(tenant, title={"de": "Tomaten rot"}, brand="Sonnenhof")
    _listing(other, title={"de": "Tomaten gelb"}, brand="Sonnenhof")
    for params in cases:
        sub = _query_sub(user, portal, params)
        digest = follow_digest.build_digest(user, [sub], now=timezone.now())
        assert digest is not None, params
        url = digest.sections[0].more_url
        assert url.startswith(f"https://{portal.host}/?")
        query = url.split("?", 1)[1]
        req = _req("get", "/", QueryDict(query).dict(), portal=portal)
        req.GET = QueryDict(query)
        html = portal_views.portal_home(req).content.decode()
        for item in digest.sections[0].items:
            assert item.title_text in html, (params, item.title_text)
        sub.delete()


def test_query_digest_never_demo_or_hidden():
    portal, tenant, user = _setup()
    sub = _query_sub(user, portal, {"q": "Tomaten"})
    demo = _tenant(is_demo=True)
    _listing(demo, is_demo=True, title={"de": "Tomaten Demo"})
    _listing(tenant, hidden_at=timezone.now(), title={"de": "Tomaten versteckt"})
    withheld = _tenant(in_city_catalog=False)
    _listing(withheld, title={"de": "Tomaten zurück"})
    assert follow_digest.build_digest(user, [sub], now=timezone.now()) is None


def test_query_digest_does_not_touch_search_log():
    portal, tenant, user = _setup()
    sub = _query_sub(user, portal, {"q": "Tomaten"})
    _listing(tenant, title={"de": "Tomaten"})
    before = SearchQueryLog.objects.count()
    assert follow_digest.build_digest(user, [sub], now=timezone.now()) is not None
    assert SearchQueryLog.objects.count() == before


def test_overlapping_subs_item_shown_once_under_narrowest():
    portal, tenant, user = _setup()
    query_sub = _query_sub(user, portal, {"q": "Tomaten", "stadtteil": OHLIGS})
    district_sub = follow.follow_now(
        user, follow.Target("district", OHLIGS, CITY), frequency="daily", portal=portal
    )
    FollowSubscription.objects.filter(pk=district_sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=1)
    )
    district_sub.refresh_from_db()
    item = _listing(tenant, title={"de": "Tomaten"}, listing_kind=AggregatorListing.KIND_PROMOTION)
    digest = follow_digest.build_digest(user, [district_sub, query_sub], now=timezone.now())
    assert len(digest.sections) == 1  # секция района опустела из-за дедупа — пропущена
    assert digest.sections[0].sub.pk == query_sub.pk
    assert [i.pk for i in digest.sections[0].items] == [item.pk]


def test_entdecken_query_sub_all_kinds():
    _p, tenant, user = _setup()
    target = follow.parse_target(_qd(art="suche", q="Tomaten", city="solingen"), portal=None)
    sub = follow.follow_now(user, target, frequency="daily", portal=None)
    FollowSubscription.objects.filter(pk=sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=1)
    )
    sub.refresh_from_db()
    hit = _listing(tenant, title={"de": "Tomaten"})
    items = list(follow.items_for(sub, since=follow.since_for(sub)))
    assert [i.pk for i in items] == [hit.pk]
    assert "/entdecken/" in follow.scope_url(sub) or "city=Solingen" in follow.scope_url(sub)


def test_describe_is_human_readable():
    pairs = follow_query.canonical(
        _qd(q="Tomaten", kat="obst-gemuese", stadtteil=OHLIGS, marke="Sonnenhof"), city=CITY
    )
    text = follow_query.describe(pairs, city=CITY)
    assert "„Tomaten“" in text and "Sonnenhof" in text and " · " in text
