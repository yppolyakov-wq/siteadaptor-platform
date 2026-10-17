"""В5 (план docs/v5-portal-analytics-plan-2026-10-17.md): учёт результатов каталога города —
агрегат «день × бизнес × предложение × действие × канал» без персональных данных.
Замки написаны ДО кода (V5-1: фундамент)."""

import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import portal_stats
from apps.aggregator.models import AggregatorListing, PortalStat
from apps.core import bots

pytestmark = pytest.mark.django_db

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
ALLOWED_FIELDS = {
    "id",
    "day",
    "tenant_schema",
    "listing_kind",
    "source_ref",
    "listing_id",
    "action",
    "channel",
    "is_demo",
    "count",
}


@pytest.fixture(autouse=True)
def _private_cache(monkeypatch, isolated_ratelimit):
    """Соль и ключи дедупа — в приватном LocMem теста: CI делит один Redis между
    воркерами, чужой `cache.clear()` иначе давал бы лишний счёт (урок CI #2683)."""
    from django.core.cache.backends.locmem import LocMemCache

    # Имя уникально: экземпляры LocMem с одним именем делят хранилище между тестами.
    store = LocMemCache(f"pstat-test-{uuid.uuid4().hex}", {})
    isolated_ratelimit.clear()  # у общей фикстуры одно имя LocMem на все тесты
    monkeypatch.setattr(portal_stats, "cache", store)
    return store


def _listing(**kw):
    defaults = {
        "tenant_schema": "t_pizza",
        "tenant_slug": "pizza",
        "business_name": "Pizzeria",
        "business_type": "restaurant",
        "city": "Solingen",
        "listing_kind": "promotion",
        "source_ref": "p1",
        "title": {"de": "Pizza-Abend"},
        "detail_url": "https://pizza.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _req(ua=UA, ip="10.0.0.1", method="get", **extra):
    rf = RequestFactory()
    return getattr(rf, method)("/", HTTP_USER_AGENT=ua, REMOTE_ADDR=ip, **extra)


def _count(**flt):
    return sum(PortalStat.objects.filter(**flt).values_list("count", flat=True))


# --- модель: без персональных данных -------------------------------------------------


def test_model_has_no_personal_fields():
    """Новое поле требует осознанного решения: ни IP, ни UA, ни сессии в агрегате."""
    assert {f.name for f in PortalStat._meta.get_fields()} <= ALLOWED_FIELDS


def test_actions_and_channels_are_closed_sets():
    assert set(PortalStat.ACTIONS_CODES) == {"impression", "view", "click", "contact", "deal"}
    lst = _listing()
    portal_stats.record(_req(), listings=[lst], action="nonsense", channel="portal")
    portal_stats.record(_req(), listings=[lst], action="view", channel="evil")
    assert not PortalStat.objects.exists()


# --- запись и дедуп ------------------------------------------------------------------


def test_view_is_recorded_once_per_visitor_and_day():
    lst = _listing()
    for _ in range(3):
        portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    assert _count(action="view") == 1
    row = PortalStat.objects.get()
    assert (row.tenant_schema, row.listing_kind, row.source_ref) == ("t_pizza", "promotion", "p1")
    assert row.listing_id == lst.pk and row.day == timezone.localdate() and not row.is_demo


def test_other_visitor_counts_separately():
    lst = _listing()
    portal_stats.record(_req(ip="10.0.0.1"), listings=[lst], action="view", channel="portal")
    portal_stats.record(_req(ip="10.0.0.2"), listings=[lst], action="view", channel="portal")
    portal_stats.record(_req(ua=UA + " Edg/120"), listings=[lst], action="view", channel="portal")
    assert _count(action="view") == 3


def test_new_day_salt_counts_again():
    lst = _listing()
    portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    tomorrow = timezone.localdate() + timedelta(days=1)
    with mock.patch.object(portal_stats.timezone, "localdate", return_value=tomorrow):
        portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    assert _count(action="view") == 2
    assert PortalStat.objects.filter(day=tomorrow).exists()


def test_actions_are_deduped_independently():
    lst = _listing()
    for action in ("impression", "view", "click"):
        portal_stats.record(_req(), listings=[lst], action=action, channel="portal")
    assert PortalStat.objects.count() == 3


def test_batch_of_listings_one_call():
    lst = [_listing(source_ref=f"p{i}") for i in range(5)]
    portal_stats.record(_req(), listings=lst, action="impression", channel="portal")
    assert _count(action="impression") == 5
    portal_stats.record(_req(), listings=lst, action="impression", channel="portal")
    assert _count(action="impression") == 5


def test_business_level_row_without_listing():
    portal_stats.record(
        _req(), tenant_schema="t_pizza", action="contact", channel="portal", is_demo=False
    )
    row = PortalStat.objects.get()
    assert (row.listing_kind, row.source_ref, row.listing_id) == ("", "", None)


def test_ip_and_ua_never_reach_the_database():
    lst = _listing()
    portal_stats.record(_req(ip="203.0.113.77"), listings=[lst], action="view", channel="portal")
    flat = repr(list(PortalStat.objects.values()))
    assert "203.0.113.77" not in flat and "Chrome" not in flat


# --- боты ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ua, extra",
    [
        ("", {}),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", {}),
        ("curl/8.4.0", {}),
        ("python-requests/2.31", {}),
        ("Mozilla/5.0 HeadlessChrome/120", {}),
        ("facebookexternalhit/1.1", {}),
        (UA, {"HTTP_SEC_PURPOSE": "prefetch"}),
        (UA, {"HTTP_PURPOSE": "prefetch"}),
    ],
)
def test_bots_and_prefetch_are_not_counted(ua, extra):
    assert bots.is_bot(_req(ua=ua, **extra))
    portal_stats.record(
        _req(ua=ua, **extra), listings=[_listing()], action="view", channel="portal"
    )
    assert not PortalStat.objects.exists()


def test_real_browser_is_not_a_bot():
    assert not bots.is_bot(_req())


def test_rate_limited_visitor_is_not_counted():
    lsts = [_listing(source_ref=f"p{i}") for i in range(3)]
    with override_settings(
        AGGREGATOR_PORTAL_STATS={**portal_stats.settings.AGGREGATOR_PORTAL_STATS, "rate_limit": 2}
    ):
        for lst in lsts:
            portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    assert _count(action="view") == 2


# --- демо --------------------------------------------------------------------------------


def test_demo_listing_is_marked_demo():
    lst = _listing(is_demo=True)
    portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    assert PortalStat.objects.get().is_demo


# --- отказоустойчивость -----------------------------------------------------------------


def test_cache_failure_counts_nothing_and_never_raises():
    """Недоступный Redis → не считаем (недосчёт честнее накрутки) и не роняем страницу."""
    lst = _listing()
    with mock.patch.object(portal_stats.cache, "add", side_effect=ConnectionError("down")):
        portal_stats.record(_req(), listings=[lst], action="view", channel="portal")
    assert not PortalStat.objects.exists()


def test_db_failure_never_raises():
    lst = _listing()
    with mock.patch.object(portal_stats, "_bump", side_effect=RuntimeError("boom")):
        portal_stats.record(_req(), listings=[lst], action="view", channel="portal")


def test_db_failure_releases_dedup_keys():
    """Стенд V5-4: метки дедупа ставились ДО упавшего INSERT — и визит этого посетителя
    за день терялся насовсем. При сбое записи метки снимаются: следующий раз засчитается."""
    lst = _listing()
    with mock.patch.object(portal_stats, "_bump", side_effect=RuntimeError("boom")):
        assert portal_stats.record(_req(), listings=[lst], action="view", channel="portal") == 0
    assert portal_stats.record(_req(), listings=[lst], action="view", channel="portal") == 1
    assert _count(action="view") == 1


@override_settings(AGGREGATOR_PORTAL_STATS={"enabled": False, "retention_days": 400})
def test_disabled_switch():
    portal_stats.record(_req(), listings=[_listing()], action="view", channel="portal")
    assert not PortalStat.objects.exists()


# --- ретеншн ---------------------------------------------------------------------------


def test_purge_removes_old_rows_only():
    today = timezone.localdate()
    keep = today - timedelta(days=10)
    old = today - timedelta(days=401)
    for day in (keep, old):
        PortalStat.objects.create(
            day=day, tenant_schema="t", action="view", channel="portal", count=3
        )
    assert portal_stats.purge(today=today) == 1
    assert list(PortalStat.objects.values_list("day", flat=True)) == [keep]


# --- админка: демо по умолчанию скрыто, только суперпользователю ------------------------


def test_admin_hides_demo_by_default_and_is_superuser_only():
    from django.contrib.admin.sites import site

    from apps.aggregator.admin import PortalStatAdmin, PortalStatDemoFilter

    day = timezone.localdate()
    PortalStat.objects.create(day=day, tenant_schema="a", action="view", channel="portal", count=1)
    PortalStat.objects.create(
        day=day, tenant_schema="d", action="view", channel="portal", count=1, is_demo=True
    )
    admin = PortalStatAdmin(PortalStat, site)
    req = RequestFactory().get("/")
    req.user = mock.Mock(is_superuser=True)
    qs = PortalStat.objects.all()

    def shown(params):
        flt = PortalStatDemoFilter(req, params, PortalStat, admin)
        return sorted(flt.queryset(req, qs).values_list("tenant_schema", flat=True))

    assert shown({}) == ["a"]
    assert shown({"demo": ["ja"]}) == ["d"]
    assert shown({"demo": ["alle"]}) == ["a", "d"]
    req.user = mock.Mock(is_superuser=False)
    assert not admin.has_module_permission(req)
    assert not admin.has_add_permission(req) and not admin.has_change_permission(req)


# --- ревью V5-1 ---------------------------------------------------------------------


def test_sql_failure_inside_outer_transaction_does_not_poison_it():
    """Учёт зовут из on_commit/атомиков сделки: сбой INSERT не смеет оборвать внешнюю
    транзакцию (savepoint в `_bump`)."""
    from django.db import transaction

    lst = _listing()
    with transaction.atomic():
        with mock.patch.object(PortalStat._meta, "db_table", "agg_no_such_table"):
            assert portal_stats.record(_req(), listings=[lst], action="view", channel="portal") == 0
        assert AggregatorListing.objects.filter(pk=lst.pk).exists()  # транзакция жива


def test_duplicate_rows_in_one_batch_count_once():
    lst = _listing()
    assert (
        portal_stats.record(_req(), listings=[lst, lst], action="impression", channel="portal") == 1
    )
    assert _count(action="impression") == 1


def test_batch_is_capped():
    lsts = [_listing(source_ref=f"p{i}") for i in range(portal_stats.MAX_BATCH + 5)]
    assert (
        portal_stats.record(_req(), listings=lsts, action="impression", channel="portal")
        == portal_stats.MAX_BATCH
    )


def test_rate_limit_is_checked_before_dedupe_keys_are_written(_private_cache):
    """Ротация UA не должна раздувать Redis: при превышении лимита ключи дедупа не пишутся."""
    lst = [_listing(source_ref=f"p{i}") for i in range(3)]
    cfg = {**portal_stats.settings.AGGREGATOR_PORTAL_STATS, "rate_limit": 1}
    with override_settings(AGGREGATOR_PORTAL_STATS=cfg):
        portal_stats.record(_req(ua=UA + " a"), listings=lst, action="view", channel="portal")
        before = len(_private_cache._cache)
        portal_stats.record(_req(ua=UA + " b"), listings=lst, action="view", channel="portal")
    assert len(_private_cache._cache) == before
    assert _count(action="view") == 3


def test_salt_lives_no_longer_than_dedupe_keys():
    assert portal_stats.SALT_TTL == portal_stats.SEEN_TTL


def test_purge_deletes_in_batches():
    today = timezone.localdate()
    old = today - timedelta(days=500)
    for i in range(7):
        PortalStat.objects.create(
            day=old, tenant_schema=f"t{i}", action="view", channel="portal", count=1
        )
    with mock.patch.object(portal_stats, "PURGE_BATCH", 3):
        assert portal_stats.purge(today=today) == 7
    assert not PortalStat.objects.exists()


# --- V5-2: просмотр страницы предложения/бизнеса и переход к продавцу ----------------
# План §15. Счёт живёт СНАРУЖИ кэша страницы (P0-1) и не трогает сессию/cookie.

PORTAL_HOST = "solingen.siteadaptor.de"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _portal(**kw):
    from apps.aggregator.models import AggregatorPortal

    defaults = {
        "host": PORTAL_HOST,
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _page(path, portal=None, ip="10.1.0.1", ua=UA, method="get", **extra):
    from django.contrib.sessions.backends.cache import SessionStore

    req = getattr(RequestFactory(), method)(
        path, HTTP_HOST=PORTAL_HOST, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip, **extra
    )
    if portal is not None:
        req.portal = portal
    req.session = SessionStore()
    return req


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_offer_view_counted_on_miss_and_hit_without_cookies(monkeypatch):
    from django.core.cache import cache as page_cache

    from apps.aggregator import structured, views

    page_cache.clear()
    portal = _portal()
    listing = _listing()
    calls = []
    orig = structured.listing_ld
    monkeypatch.setattr(
        structured, "listing_ld", lambda *a, **kw: calls.append(1) or orig(*a, **kw)
    )
    path = f"/angebot/{listing.pk}/"
    req1, req2 = _page(path, portal, ip="10.1.0.1"), _page(path, portal, ip="10.1.0.2")
    r1 = views.offer_page(req1, listing.pk)
    assert r1.status_code == 200
    assert page_cache.get(f"pubpage2:{PORTAL_HOST}:{path}:de") is not None
    r2 = views.offer_page(req2, listing.pk)
    assert r2.status_code == 200 and len(calls) == 1  # второй ответ — из кэша
    assert not r1.cookies and not r2.cookies
    for req in (req1, req2):
        assert req.session.modified is False and req.session.is_empty()
    assert _count(action="view", channel="portal", listing_id=listing.pk) == 2
    views.offer_page(_page(path, portal, ip="10.1.0.1"), listing.pk)  # тот же посетитель
    assert _count(action="view", channel="portal") == 2
    page_cache.clear()


@override_settings(ROOT_URLCONF="config.urls_public")
def test_offer_view_channel_entdecken_on_main_domain():
    from apps.aggregator import views

    listing = _listing()
    resp = views.offer_page(_page(f"/entdecken/angebot/{listing.pk}/"), listing.pk)
    assert resp.status_code == 200
    assert _count(action="view", channel="entdecken") == 1
    assert _count(channel="portal") == 0


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_offer_view_not_counted_for_bot_head_404_and_business_redirect(
    django_assert_num_queries,
):
    from django.core.cache import cache as page_cache
    from django.http import Http404

    from apps.aggregator import views

    page_cache.clear()
    portal = _portal()
    listing = _listing()
    path = f"/angebot/{listing.pk}/"
    views.offer_page(_page(path, portal, ua="Googlebot/2.1"), listing.pk)  # прогрев кэша
    with django_assert_num_queries(0):  # бот на hit не платит запросом
        assert (
            views.offer_page(_page(path, portal, ua="Googlebot/2.1"), listing.pk).status_code == 200
        )
    assert PortalStat.objects.count() == 0
    views.offer_page(_page(path, portal, method="head"), listing.pk)
    assert PortalStat.objects.count() == 0
    demo = _listing(is_demo=True, tenant_schema="t_demo", source_ref="d1")
    with pytest.raises(Http404):
        views.offer_page(_page(f"/angebot/{demo.pk}/", portal), demo.pk)
    assert PortalStat.objects.count() == 0
    biz = _listing(listing_kind="business", source_ref="business", tenant_schema="t_biz")
    assert views.offer_page(_page(f"/angebot/{biz.pk}/", portal), biz.pk).status_code == 301
    assert PortalStat.objects.count() == 0
    page_cache.clear()


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_offer_view_hidden_after_caching_is_not_counted():
    from django.core.cache import cache as page_cache

    from apps.aggregator import views

    page_cache.clear()
    portal = _portal()
    listing = _listing()
    path = f"/angebot/{listing.pk}/"
    views.offer_page(_page(path, portal, ua="Googlebot/2.1"), listing.pk)  # прогрев кэша
    AggregatorListing.objects.filter(pk=listing.pk).update(hidden_at=timezone.now())
    assert views.offer_page(_page(path, portal), listing.pk).status_code == 200  # из кэша
    assert PortalStat.objects.count() == 0
    page_cache.clear()


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_repeat_view_on_cache_hit_costs_no_query(django_assert_num_queries):
    """Ревью V5-2: повторный просмотр тем же посетителем — без запроса в БД."""
    from django.core.cache import cache as page_cache

    from apps.aggregator import views

    page_cache.clear()
    portal = _portal()
    listing = _listing()
    path = f"/angebot/{listing.pk}/"
    views.offer_page(_page(path, portal), listing.pk)
    with django_assert_num_queries(0):
        assert views.offer_page(_page(path, portal), listing.pk).status_code == 200
    assert _count(action="view") == 1
    page_cache.clear()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_offer_view_demo_on_preview_portal_is_flagged():
    from apps.aggregator import views

    portal = _portal(show_demo=True)
    demo = _listing(is_demo=True)
    assert views.offer_page(_page(f"/angebot/{demo.pk}/", portal), demo.pk).status_code == 200
    row = PortalStat.objects.get()
    assert row.is_demo is True and row.action == "view"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_view_counts_business_card_or_tenant_row():
    from apps.aggregator import reviews_views
    from apps.tenants.tests.factories import TenantFactory

    portal = _portal()
    TenantFactory(schema_name="t_brot", slug="brot", name="Brot", city="Solingen")
    card = _listing(
        tenant_schema="t_brot",
        tenant_slug="brot",
        listing_kind="business",
        source_ref="business",
        detail_url="https://brot.siteadaptor.de/",
    )
    resp = reviews_views.business_page(_page("/unternehmen/brot/", portal), "brot")
    assert resp.status_code == 200
    row = PortalStat.objects.get(tenant_schema="t_brot")
    assert (row.listing_kind, row.source_ref, row.listing_id) == ("business", "business", card.pk)
    assert row.channel == "portal" and row.action == "view"

    TenantFactory(schema_name="t_demo", slug="demo", name="Demo", city="Solingen", is_demo=True)
    preview = _portal(host="preview.siteadaptor.de", show_demo=True)
    reviews_views.business_page(_page("/unternehmen/demo/", preview), "demo")
    row = PortalStat.objects.get(tenant_schema="t_demo")
    assert (row.listing_kind, row.source_ref, row.listing_id) == ("business", "business", None)
    assert row.is_demo is True


def _outbound(pk, portal=None, **kw):
    from apps.aggregator import views

    return views.outbound_click(_page(f"/weiter/{pk}/", portal, **kw), pk)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_outbound_redirect_counts_click_and_appends_cl():
    portal = _portal()
    listing = _listing()
    resp = _outbound(listing.pk, portal)
    assert resp.status_code == 302
    assert resp["Location"] == listing.with_channel("portal", lang="de", listing_ref=True)
    assert resp["Location"].endswith(f"&cl={listing.pk}")
    assert "no-store" in resp["Cache-Control"]
    assert "noindex" in resp["X-Robots-Tag"]
    assert _count(action="click", channel="portal", listing_id=listing.pk) == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_outbound_unknown_hidden_or_out_of_scope_goes_home_without_count():
    portal = _portal()
    hidden = _listing(hidden_at=timezone.now(), source_ref="h")
    other_city = _listing(city="Hilden", tenant_schema="t_hilden", source_ref="o")
    demo = _listing(is_demo=True, tenant_schema="t_demo", source_ref="d")
    for pk in (999999, hidden.pk, other_city.pk, demo.pk):
        resp = _outbound(pk, portal)
        assert resp.status_code == 302 and resp["Location"] == "/", pk
    assert PortalStat.objects.count() == 0


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_outbound_non_http_target_goes_home():
    portal = _portal()
    for i, url in enumerate(("ftp://x/", "javascript:alert(1)")):
        listing = _listing(detail_url=url, source_ref=f"bad{i}")
        assert _outbound(listing.pk, portal)["Location"] == "/"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_outbound_rate_limited_still_redirects(monkeypatch):
    # Не фикстура `settings`: вместе с @override_settings она при выходе восстанавливает
    # ROOT_URLCONF портала, и он утекает в следующие тесты процесса (CI g1).
    cfg = portal_stats._cfg
    monkeypatch.setattr(portal_stats, "_cfg", lambda key: 1 if key == "rate_limit" else cfg(key))
    portal = _portal()
    listing = _listing()
    _outbound(listing.pk, portal, ip="10.5.5.5")
    resp = _outbound(listing.pk, portal, ip="10.5.5.5", ua=UA + " Other")
    assert resp["Location"].startswith("https://pizza.siteadaptor.de/")
    assert _count(action="click") == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_outbound_head_redirects_without_count_and_post_is_405():
    portal = _portal()
    listing = _listing()
    resp = _outbound(listing.pk, portal, method="head")
    assert resp.status_code == 302 and resp["Location"].startswith("https://")
    assert _outbound(listing.pk, portal, method="post").status_code == 405
    assert PortalStat.objects.count() == 0


@override_settings(ROOT_URLCONF="config.urls_public")
def test_featured_click_records_click_and_keeps_featured_counter():
    from apps.aggregator import views

    listing = _listing(featured_until=timezone.now() + timedelta(hours=5))
    resp = views.featured_click(_page(f"/entdecken/klick/{listing.pk}/"), listing.pk)
    # V5-5 (D-9): ссылка несёт канал ТОЙ поверхности, где был клик.
    assert resp["Location"] == listing.with_channel("entdecken", lang="de", listing_ref=True)
    listing.refresh_from_db()
    assert listing.featured_clicks == 1
    assert _count(action="click", channel="entdecken") == 1


def test_with_channel_listing_ref_is_opt_in():
    listing = _listing()
    assert "cl=" not in listing.portal_url
    url = listing.with_channel("portal", lang="de", listing_ref=True)
    assert url.count(f"cl={listing.pk}") == 1
    preset = _listing(detail_url="https://pizza.siteadaptor.de/p/1/?cl=7", source_ref="p2")
    assert preset.with_channel("portal", listing_ref=True).count("cl=") == 1


def test_outbound_routes_resolve_before_catch_all():
    from django.urls import resolve

    from apps.aggregator import views

    assert resolve("/weiter/7/", urlconf="config.urls_portal").func is views.outbound_click
    match = resolve("/entdecken/weiter/7/", urlconf="config.urls_public")
    assert match.func is views.outbound_click


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_seller_links_go_through_outbound():
    from types import SimpleNamespace

    from apps.aggregator import geo, reviews_views, views
    from apps.tenants.tests.factories import TenantFactory

    portal = _portal()
    listing = _listing()
    html = views.offer_page(_page(f"/angebot/{listing.pk}/", portal), listing.pk).content.decode()
    assert f'href="/weiter/{listing.pk}/" rel="nofollow" data-offer-cta' in html
    assert '<link rel="canonical" href="https://pizza.siteadaptor.de/p/1/">' in html
    assert '"url":"https://pizza.siteadaptor.de/p/1/"' in html  # JSON-LD — чистый detail_url

    TenantFactory(schema_name="t_brot", slug="brot", name="Brot", city="Solingen")
    card = _listing(
        tenant_schema="t_brot",
        tenant_slug="brot",
        listing_kind="business",
        source_ref="business",
        detail_url="https://brot.siteadaptor.de/",
    )
    html = reviews_views.business_page(_page("/unternehmen/brot/", portal), "brot").content
    assert f'href="/weiter/{card.pk}/" rel="nofollow"'.encode() in html

    points = geo.map_points([_listing(latitude=51.1, longitude=7.0, source_ref="m1")])
    assert points[0]["url"].startswith("/weiter/")
    dated = SimpleNamespace(
        pk=1,
        latitude=51.1,
        longitude=7.0,
        title_text="Zimmer",
        is_featured_now=False,
        range_nights=2,
        portal_url="https://hotel.siteadaptor.de/u/1/?von=2026-11-01&ch=portal",
    )
    assert geo.map_points([dated])[0]["url"] == dated.portal_url  # даты целы

    with override_settings(ROOT_URLCONF="config.urls_public"):
        req = _page("/entdecken/merkliste/")
        req.session["shortlist"] = [listing.pk]
        shortlist_html = views.shortlist_compare(req).content.decode()
    assert shortlist_html.count(f'href="/entdecken/weiter/{listing.pk}/" rel="nofollow"') == 2


def test_robots_disallow_outbound():
    from apps.aggregator import portal_views, views

    assert "/weiter/" in portal_views.PORTAL_DISALLOW
    assert "/entdecken/weiter/" in views.PLATFORM_DISALLOW


# --- V5-4: показы карточек в списках (JS-маячок) -----------------------------------
# План §17. Маячок — POST без CSRF-токена (страницы кэшируются без токена, P0-1),
# вместо токена — same-origin; ответ всегда 204, без cookie.


def _beacon(
    ids="",
    portal=None,
    ip="10.4.0.1",
    ua=UA,
    sfs="same-origin",
    origin=None,
    body=None,
    method="post",
    content_type="application/x-www-form-urlencoded",
):
    from django.contrib.sessions.backends.cache import SessionStore

    from apps.aggregator import views

    extra = {"HTTP_HOST": PORTAL_HOST, "HTTP_USER_AGENT": ua, "REMOTE_ADDR": ip}
    if sfs:
        extra["HTTP_SEC_FETCH_SITE"] = sfs
    if origin:
        extra["HTTP_ORIGIN"] = origin
    path = "/stat/sichtbar/" if portal is not None else "/entdecken/stat/sichtbar/"
    if method == "post":
        data = body if body is not None else f"p={ids}"
        req = RequestFactory().post(path, data=data, content_type=content_type, **extra)
    else:
        req = getattr(RequestFactory(), method)(path, **extra)
    if portal is not None:
        req.portal = portal
    req.session = SessionStore()
    return views.impression_beacon(req), req


def _ids(*listings):
    return ",".join(str(x.pk) for x in listings)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_counts_visible_cards_and_returns_204_without_cookies():
    portal = _portal()
    a, b = _listing(source_ref="a"), _listing(source_ref="b")
    resp, req = _beacon(_ids(a, b), portal)
    assert resp.status_code == 204 and resp.content == b""
    assert "no-store" in resp["Cache-Control"] and not resp.cookies
    assert req.session.is_empty() and not req.session.modified
    assert _count(action="impression", channel="portal") == 2
    assert set(PortalStat.objects.values_list("listing_id", flat=True)) == {a.pk, b.pk}


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_dedups_same_visitor_same_day():
    portal = _portal()
    a, b = _listing(source_ref="a"), _listing(source_ref="b")
    _beacon(_ids(a, b), portal)
    _beacon(_ids(a, b), portal)
    assert _count(action="impression") == 2
    _beacon(_ids(a, b), portal, ua=UA + " Other")
    assert _count(action="impression") == 4


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_ignores_unknown_hidden_out_of_scope_and_demo():
    portal = _portal()
    hidden = _listing(hidden_at=timezone.now(), source_ref="h")
    other = _listing(city="Hilden", tenant_schema="t_hilden", source_ref="o")
    demo = _listing(is_demo=True, tenant_schema="t_demo", source_ref="d")
    ok = _listing(source_ref="ok")
    _beacon(f"999999,{_ids(hidden, other, demo, ok)}", portal)
    assert list(PortalStat.objects.values_list("listing_id", flat=True)) == [ok.pk]
    preview = _portal(host="preview.siteadaptor.de", show_demo=True)
    _beacon(_ids(demo), preview)
    assert PortalStat.objects.get(listing_id=demo.pk).is_demo is True


@override_settings(ROOT_URLCONF="config.urls_public")
def test_beacon_entdecken_channel_and_demo_flag():
    demo = _listing(is_demo=True, source_ref="d")
    _beacon(_ids(demo))
    row = PortalStat.objects.get()
    assert row.channel == "entdecken" and row.is_demo is True and row.action == "impression"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_truncates_to_max_batch(django_assert_max_num_queries):
    portal = _portal()
    items = [_listing(source_ref=f"x{i}") for i in range(60)]
    # SELECT листингов + INSERT пачкой; SAVEPOINT/RELEASE — от atomic() внутри _bump
    with django_assert_max_num_queries(4):
        _beacon(_ids(*items), portal)
    assert PortalStat.objects.filter(action="impression").count() == portal_stats.MAX_BATCH


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_requires_same_origin():
    portal = _portal()
    a = _listing()
    for sfs, origin in (
        ("cross-site", None),
        ("same-site", None),
        ("", "https://evil.example"),
        ("", None),
    ):
        resp, _req = _beacon(_ids(a), portal, sfs=sfs, origin=origin)
        assert resp.status_code == 204
    assert PortalStat.objects.count() == 0
    _beacon(_ids(a), portal, sfs="", origin=f"https://{PORTAL_HOST}")
    assert _count(action="impression") == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_get_and_head_are_405():
    portal = _portal()
    for method in ("get", "head"):
        resp, _req = _beacon(portal=portal, method=method)
        assert resp.status_code == 405
    assert PortalStat.objects.count() == 0


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_malformed_body_never_500(monkeypatch):
    from apps.aggregator import views

    portal = _portal()
    _listing()
    bodies = [
        "p=abc",
        "p=",
        "p=-1,0",
        "p=1e9",
        "p=99999999999999999999",
        "p=1,,2x",
        "x=1",
        "\x00\xff\xfe",
        "p=" + "1," * 2000,
    ]
    for body in bodies:
        resp, _req = _beacon(portal=portal, body=body)
        assert resp.status_code == 204, body
    resp, _req = _beacon(portal=portal, body='{"p":[1]}', content_type="application/json")
    assert resp.status_code == 204
    assert PortalStat.objects.count() == 0
    monkeypatch.setattr(views, "_scoped_listings", lambda *a: (_ for _ in ()).throw(RuntimeError))
    assert _beacon("1", portal)[0].status_code == 204


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_bots_not_counted_and_cost_no_query(django_assert_num_queries):
    portal = _portal()
    a = _listing()
    ids = _ids(a)
    for kw in (
        {"ua": ""},
        {"ua": "Googlebot/2.1"},
        {"ua": "Mozilla/5.0 HeadlessChrome/120"},
    ):
        with django_assert_num_queries(0):
            _beacon(ids, portal, **kw)
    from django.contrib.sessions.backends.cache import SessionStore

    from apps.aggregator import views

    req = RequestFactory().post(
        "/stat/sichtbar/",
        data=f"p={ids}",
        content_type="application/x-www-form-urlencoded",
        HTTP_USER_AGENT=UA,
        HTTP_SEC_FETCH_SITE="same-origin",
        HTTP_SEC_PURPOSE="prefetch",
    )
    req.portal, req.session = portal, SessionStore()
    views.impression_beacon(req)
    assert PortalStat.objects.count() == 0


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_rate_limited_before_db(monkeypatch, django_assert_num_queries):
    portal = _portal()
    a = _listing()
    cfg = portal_stats._cfg
    monkeypatch.setattr(portal_stats, "_cfg", lambda k: 1 if k == "beacon_limit" else cfg(k))
    _beacon(_ids(a), portal, ip="10.6.6.6")
    with django_assert_num_queries(0):
        resp, _req = _beacon(_ids(a), portal, ip="10.6.6.6", ua=UA + " B")
    assert resp.status_code == 204 and _count(action="impression") == 1


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_disabled_setting(monkeypatch):
    portal = _portal()
    a = _listing()
    cfg = portal_stats._cfg
    monkeypatch.setattr(portal_stats, "_cfg", lambda k: False if k == "enabled" else cfg(k))
    _beacon(_ids(a), portal)
    assert PortalStat.objects.count() == 0


def test_beacon_routes_resolve_before_catch_all():
    from django.urls import resolve

    from apps.aggregator import views

    assert resolve("/stat/sichtbar/", urlconf="config.urls_portal").func is views.impression_beacon
    m = resolve("/entdecken/stat/sichtbar/", urlconf="config.urls_public")
    assert m.func is views.impression_beacon


def test_beacon_is_csrf_exempt():
    """sendBeacon не несёт CSRF-токен: CsrfViewMiddleware обязан пропустить маячок."""
    from django.http import HttpResponse
    from django.middleware.csrf import CsrfViewMiddleware

    from apps.aggregator import views

    req = RequestFactory().post(
        "/entdecken/stat/sichtbar/", data="p=1", content_type="application/x-www-form-urlencoded"
    )
    mw = CsrfViewMiddleware(lambda r: HttpResponse())
    assert mw.process_view(req, views.impression_beacon, (), {}) is None
    assert (
        mw.process_view(req, views.featured_click, (), {}) is not None
    )  # контроль: обычной вьюхе — 403


def test_robots_disallow_beacon():
    from apps.aggregator import portal_views, views

    assert "/stat/" in portal_views.PORTAL_DISALLOW
    assert "/entdecken/stat/" in views.PLATFORM_DISALLOW


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_cards_carry_data_pstat_on_every_card():
    from django.template.loader import render_to_string

    a, b = _listing(source_ref="a"), _listing(source_ref="b")
    feat = _listing(source_ref="f", featured_until=timezone.now() + timedelta(hours=3))
    html = render_to_string("aggregator/_cards.html", {"items": [a, b, feat]})
    assert html.count('data-pstat="') == 3
    for item in (a, b, feat):
        assert f'data-pstat="{item.pk}"' in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_script_on_portal_pages():
    from apps.aggregator import portal_views

    portal = _portal()
    _listing()
    html = portal_views.portal_home(_page("/", portal)).content.decode()
    assert 'data-pstat-url="/stat/sichtbar/"' in html and "sendBeacon" in html
    assert 'data-pstat="' in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_beacon_script_on_entdecken_pages():
    from apps.aggregator import views

    _listing()
    html = views.city_listing(_page("/entdecken/Solingen/"), "Solingen").content.decode()
    assert 'data-pstat-url="/entdecken/stat/sichtbar/"' in html and 'data-pstat="' in html


def test_beacon_script_not_on_tenant_storefront():
    from pathlib import Path

    from django.conf import settings

    base = Path(settings.BASE_DIR) / "templates" / "storefront" / "_base.html"
    assert "_pstat_beacon" not in base.read_text()


@override_settings(ROOT_URLCONF="config.urls_portal", CACHES=LOCMEM, PUBLIC_PAGE_CACHE_TTL=60)
def test_offer_page_with_beacon_still_cached_without_cookies():
    from django.core.cache import cache as page_cache

    from apps.aggregator import views

    page_cache.clear()
    portal = _portal()
    listing = _listing()
    _listing(source_ref="more")  # блок «Mehr von …» — карточки с data-pstat
    path = f"/angebot/{listing.pk}/"
    r1 = views.offer_page(_page(path, portal, ip="10.7.0.1"), listing.pk)
    r2 = views.offer_page(_page(path, portal, ip="10.7.0.2"), listing.pk)
    assert not r1.cookies and not r2.cookies
    assert page_cache.get(f"pubpage2:{PORTAL_HOST}:{path}:de") is not None
    body = r2.content.decode()
    assert 'data-pstat="' in body and "data-pstat-url" in body
    page_cache.clear()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_beacon_without_content_length_is_ignored():
    """Ревью V5-4: chunked-тело (без Content-Length) не разбираем — sendBeacon его всегда шлёт."""
    portal = _portal()
    a = _listing()
    from django.contrib.sessions.backends.cache import SessionStore

    from apps.aggregator import views

    req = RequestFactory().post(
        "/stat/sichtbar/",
        data=f"p={a.pk}",
        content_type="application/x-www-form-urlencoded",
        HTTP_USER_AGENT=UA,
        HTTP_SEC_FETCH_SITE="same-origin",
    )
    del req.META["CONTENT_LENGTH"]
    req.portal, req.session = portal, SessionStore()
    assert views.impression_beacon(req).status_code == 204
    assert PortalStat.objects.count() == 0
