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
