"""T-8.21: журнал поисковых запросов каталога города.

План — docs/t8-21-search-log-plan-2026-10-15.md §6.
"""

import inspect
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError, IntegrityError
from django.db import connection as db_connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.aggregator import portal_views, search, search_log, tasks, views
from apps.aggregator.admin import SearchQueryLogAdmin, _csv_safe
from apps.aggregator.models import AggregatorListing, AggregatorPortal, SearchQueryLog

pytestmark = pytest.mark.django_db

_n = iter(range(100_000))


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _listing(title, *, kind="promotion", **kw):
    i = next(_n)
    return AggregatorListing.objects.create(
        tenant_schema=f"t{i}",
        tenant_slug=f"x{i}",
        business_name=f"Laden {i}",
        city="Solingen",
        listing_kind=kind,
        source_ref=f"s{i}",
        title={"de": title},
        detail_url="https://x.siteadaptor.de/",
        **kw,
    )


def _portal():
    return AggregatorPortal.objects.get_or_create(
        host="solingen.siteadaptor.de",
        defaults={
            "kind": "city",
            "city": "Solingen",
            "title": {"de": "Solingen"},
            "is_active": True,
        },
    )[0]


def _req(path="/", ip="10.21.0.1", **params):
    return RequestFactory().get(path, params, REMOTE_ADDR=ip)


def _portal_search(**params):
    req = _req(ip=f"10.21.{next(_n) % 250}.{next(_n) % 250}", **params)
    req.portal = _portal()
    with override_settings(ROOT_URLCONF="config.urls_portal"):
        return portal_views.portal_home(req)


def _entdecken(**params):
    with override_settings(ROOT_URLCONF="config.urls_public"):
        return views.discover_index(
            _req("/entdecken/", ip=f"10.22.{next(_n) % 250}.{next(_n) % 250}", **params)
        )


# --- запись -----------------------------------------------------------------------------


def test_portal_search_writes_row():
    _listing("Messer Santoku")
    _portal_search(q="Messer")
    row = SearchQueryLog.objects.get()
    assert row.surface == "portal" and row.portal_host == "solingen.siteadaptor.de"
    assert row.city == "Solingen" and row.query_norm == "messer"  # город — из реестра
    assert row.searches == 1 and row.last_mode == "fts" and row.last_results == 1
    assert row.day == timezone.localdate()


def test_entdecken_search_writes_row():
    _listing("Messer Santoku")
    _entdecken(q="Messer", city="Solingen")
    row = SearchQueryLog.objects.get()
    assert row.surface == "entdecken" and row.portal_host == "" and row.city == "Solingen"


def test_filters_only_search_is_logged():
    _listing("Pizza", district="graefrath")
    _portal_search(stadtteil="graefrath")
    row = SearchQueryLog.objects.get()
    assert row.query_norm == "" and row.filters_key == "stadtteil=graefrath"
    assert row.filters == {"stadtteil": "graefrath"} and row.last_mode == "none"


def test_one_write_per_request_on_both_surfaces():
    _listing("Messer")
    _portal_search(q="Messer", kind="alle")
    _entdecken(q="Messer", city="Solingen")
    assert list(SearchQueryLog.objects.values_list("searches", flat=True)) == [1, 1]


def test_same_query_same_day_aggregates():
    _listing("Messer")
    _portal_search(q="Messer")
    _portal_search(q="  MESSER ")
    row = SearchQueryLog.objects.get()
    assert row.searches == 2 and row.query_norm == "messer"


def test_zero_results_and_empty_mode_counted():
    _listing("Messer")
    _portal_search(q="Zylinderkopf")
    _portal_search(q="!!!")
    rows = {r.query_norm: r for r in SearchQueryLog.objects.all()}
    assert rows["zylinderkopf"].zero_results == 1 and rows["zylinderkopf"].last_results == 0
    assert rows["!!!"].last_mode == "empty" and rows["!!!"].zero_results == 1


def test_trigram_hit_counted():
    _listing("Messer Santoku")
    _portal_search(q="Mesesr")
    row = SearchQueryLog.objects.get()
    assert row.trigram_hits == 1 and row.last_mode == "trigram" and row.zero_results == 0


def test_cursor_pages_are_not_logged():
    _listing("Messer")
    _portal_search(q="Messer", cursor="abc")
    _entdecken(q="Messer", city="Solingen", cursor="abc")
    assert not SearchQueryLog.objects.exists()


def test_min_len_skips_single_char():
    _listing("Messer")
    _portal_search(q="m")
    assert not SearchQueryLog.objects.exists()


def test_disabled_setting_is_noop():
    _listing("Messer")
    with override_settings(
        AGGREGATOR_SEARCH_LOG={"enabled": False, "retention_days": 180, "min_len": 2}
    ):
        with CaptureQueriesContext(db_connection) as ctx:
            _portal_search(q="Messer")
    assert not SearchQueryLog.objects.exists()
    assert not any("searchquerylog" in q["sql"] for q in ctx.captured_queries)


# --- нормализация и персональные данные --------------------------------------------------


def test_normalize_query():
    assert search_log.normalize_query("  Brötchen   VOM  Bäcker ") == "brötchen vom bäcker"
    assert len(search_log.normalize_query("x" * 500)) == search_log.QUERY_MAX
    assert search_log.normalize_query("Café") == "café"  # NFC


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("mail an max@example.de bitte", "mail an ‹email› bitte"),
        ("ruf 0171 2345678 an", "ruf ‹nummer› an"),
        ("tel +49 212 123456", "tel ‹nummer›"),
        ("DE89 3704 0044 0532 0130 00", "‹iban›"),
        ("brot in 42651 solingen", "brot in 42651 solingen"),
        ("kaffee 2,50 €", "kaffee 2,50 €"),
    ],
)
def test_scrub_personal_data(raw, expected):
    assert search_log.scrub(raw) == expected


ALLOWED_FIELDS = {
    "id",
    "day",
    "surface",
    "portal_host",
    "city",
    "lang",
    "query_norm",
    "filters_key",
    "filters",
    "searches",
    "zero_results",
    "trigram_hits",
    "last_mode",
    "last_results",
}


def test_model_has_no_personal_fields():
    """Замок Р-2: новое поле требует осознанного решения — журнал без персональных данных."""
    assert {f.name for f in SearchQueryLog._meta.get_fields()} <= ALLOWED_FIELDS


def test_record_has_no_request_parameter():
    """Замок Р-2: в журнал приходят только примитивы, ничего персонального."""
    forbidden = ("request", "ip", "user", "session", "agent")
    for fn in (search.record, search_log.log, search_log._log):
        params = inspect.signature(fn).parameters
        assert not [p for p in params if any(w in p.lower() for w in forbidden)], fn.__name__


# --- отказоустойчивость -----------------------------------------------------------------


def test_log_failure_does_not_break_search():
    _listing("Messer Santoku")
    with mock.patch.object(search_log, "_log", side_effect=DatabaseError("boom")):
        html = _portal_search(q="Messer").content.decode()
        assert "Messer Santoku" in html
        html = _entdecken(q="Messer", city="Solingen").content.decode()
        assert "Messer Santoku" in html
    assert AggregatorListing.objects.exists()  # транзакция теста не отравлена


def test_create_failure_inside_savepoint_keeps_transaction_usable():
    _listing("Messer Santoku")
    with mock.patch.object(
        SearchQueryLog.objects, "create", side_effect=DatabaseError("disk full")
    ):
        assert _portal_search(q="Messer").status_code == 200
    assert AggregatorListing.objects.count() == 1


def test_race_integrity_error_falls_back_to_update():
    _listing("Messer")
    _portal_search(q="Messer")
    real_update = SearchQueryLog.objects.filter().__class__.update
    calls = {"n": 0}

    def flaky_update(self, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return 0  # «строки нет» → create → IntegrityError → повторный update
        return real_update(self, **kw)

    with (
        mock.patch.object(type(SearchQueryLog.objects.filter()), "update", flaky_update),
        mock.patch.object(SearchQueryLog.objects, "create", side_effect=IntegrityError),
    ):
        _portal_search(q="Messer")
    assert SearchQueryLog.objects.get().searches == 2


def test_query_budget_is_count_plus_upsert():
    _listing("Messer")
    _portal_search(q="Messer")  # тёплый ключ
    with CaptureQueriesContext(db_connection) as ctx:
        _portal_search(q="Messer")
    sqls = [q["sql"] for q in ctx.captured_queries if "searchquerylog" in q["sql"]]
    assert len([s for s in sqls if s.startswith("UPDATE")]) == 1
    assert not any(s.startswith("INSERT") for s in sqls)
    assert any("LIMIT 241" in q["sql"] for q in ctx.captured_queries)


def test_count_capped():
    for i in range(250):
        _listing(f"Messer {i}")
    _portal_search(q="Messer")
    assert SearchQueryLog.objects.get().last_results == 241


def test_filters_key_price_rounded():
    _listing("Pizza", new_price=Decimal("5"))
    _portal_search(q="Pizza", preis_von="2.49")
    _portal_search(q="Pizza", preis_von="2,50")
    row = SearchQueryLog.objects.get()
    assert row.searches == 2 and row.filters_key.endswith("preis_von=2")


# --- retention ----------------------------------------------------------------------------


def _row(day, **kw):
    kw.setdefault("query_norm", f"q{next(_n)}")
    kw.setdefault("searches", 1)
    return SearchQueryLog.objects.create(day=day, surface="portal", **kw)


def test_purge_respects_retention():
    today = timezone.localdate()
    old = _row(today - timedelta(days=181))
    edge = _row(today - timedelta(days=180))
    kept = _row(today - timedelta(days=180), searches=3)  # популярная — живёт весь срок
    fresh = _row(today)
    assert tasks.purge_search_log() == 2  # old по retention + edge как одиночная (30 дней)
    assert set(SearchQueryLog.objects.values_list("pk", flat=True)) == {kept.pk, fresh.pk}
    assert edge.pk
    assert not SearchQueryLog.objects.filter(pk=old.pk).exists()


# --- админка: только платформа -------------------------------------------------------------


def _admin_get(user):
    """Changelist напрямую (проект не ходит через test client — django-tenants/Domain)."""
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.cache import SessionStore

    req = _req("/admin/aggregator/searchquerylog/")
    req.user = user
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    ma = admin.site._registry[SearchQueryLog]
    return admin.site.admin_view(ma.changelist_view)(req)


@pytest.mark.urls("config.urls_public")
def test_admin_superuser_only():
    from django.contrib.auth.models import AnonymousUser

    User = get_user_model()
    assert _admin_get(AnonymousUser()).status_code == 302  # аноним → логин
    from django.core.exceptions import PermissionDenied

    staff = User.objects.create_user("staff", "s@x.de", "pw", is_staff=True)
    with pytest.raises(PermissionDenied):  # staff без superuser — 403
        _admin_get(staff)
    assert not SearchQueryLogAdmin(SearchQueryLog, admin.site).has_view_permission(
        type("R", (), {"user": staff})()
    )
    root = User.objects.create_superuser("root", "r@x.de", "pw")
    assert _admin_get(root).status_code == 200


def test_admin_not_in_tenant_urls():
    with pytest.raises(NoReverseMatch):
        reverse("admin:aggregator_searchquerylog_changelist", urlconf="config.urls_tenant")


def test_csv_export_and_injection_guard():
    today = timezone.localdate()
    _row(today, query_norm="=HYPERLINK(1)", city="solingen", zero_results=1)
    _row(today - timedelta(days=1), query_norm="=HYPERLINK(1)", city="solingen", searches=3)
    ma = SearchQueryLogAdmin(SearchQueryLog, admin.site)
    resp = ma.export_csv(_req(), SearchQueryLog.objects.all())
    body = resp.content.decode("utf-8-sig")
    assert resp["Content-Type"].startswith("text/csv") and "'=HYPERLINK(1)" in body
    grouped = ma.export_csv_grouped(_req(), SearchQueryLog.objects.all()).content.decode(
        "utf-8-sig"
    )
    assert "'=HYPERLINK(1);solingen;portal;4;1;0" in grouped
    assert _csv_safe("ok") == "ok" and _csv_safe("-1") == "'-1"


def test_result_filter_shows_only_never_found():
    today = timezone.localdate()
    never = _row(today, query_norm="nie", searches=2, zero_results=2)
    _row(today, query_norm="manchmal", searches=2, zero_results=1)
    from apps.aggregator.admin import SearchResultFilter

    ma = admin.site._registry[SearchQueryLog]
    f = SearchResultFilter(_req(treffer="nie"), {"treffer": ["nie"]}, SearchQueryLog, ma)
    assert list(f.queryset(None, SearchQueryLog.objects.all()).values_list("pk", flat=True)) == [
        never.pk
    ]


# --- находки ревью (security / django / database) --------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("DE89 3704 0044 0532 0130 00", "‹iban›"),
        ("nl91 abna 0417 1643 00", "‹iban›"),  # после casefold тоже
        ("Max@localhost", "‹email›"),
        ("(0212) 123456", "‹nummer›"),
        ("+49 (0) 212 99 88 77", "‹nummer›"),
        ("12.34.56.78.90", "‹nummer›"),
        ("Brot in 42651", "brot in 42651"),
    ],
)
def test_normalize_query_scrubs_real_path(raw, expected):
    """IBAN в нижнем регистре, e-mail без точки, телефон со скобками — через normalize."""
    assert search_log.normalize_query(raw) == expected


def test_control_chars_do_not_reach_db(caplog):
    _listing("Messer")
    with caplog.at_level("WARNING"):
        resp = _portal_search(q="Mes\x00ser")
    assert resp.status_code == 200
    assert SearchQueryLog.objects.get().query_norm == "mes ser"
    assert not [r for r in caplog.records if "search log" in r.getMessage()]


def test_log_failure_message_has_no_query(caplog):
    _listing("Messer")
    with mock.patch.object(search_log, "_log", side_effect=DatabaseError("boom Messer")):
        with caplog.at_level("WARNING"):
            _portal_search(q="GeheimerName")
    msgs = [r.getMessage() for r in caplog.records if "search log" in r.getMessage()]
    assert msgs and "GeheimerName" not in "".join(msgs) and "DatabaseError" in msgs[0]


def test_free_text_city_on_entdecken_is_not_stored():
    _listing("Messer")
    _entdecken(q="Messer", city="Anna Müller Hauptstr 5")
    assert SearchQueryLog.objects.get().city == ""
    _entdecken(q="Messer", city="solingen")
    assert SearchQueryLog.objects.get(city="Solingen").searches == 1


def test_tab_and_district_scope_are_part_of_the_key():
    """«brot» на вкладке «Angebote» (0) и на «Alle» (найдено) — разные строки."""
    _listing("Brot", kind="product")
    _portal_search(q="Brot", kind="angebote")
    _portal_search(q="Brot", kind="alle")
    rows = {r.filters_key: r for r in SearchQueryLog.objects.all()}
    assert rows["kind=angebote"].zero_results == 1 and rows["kind=alle"].zero_results == 0
    with override_settings(ROOT_URLCONF="config.urls_portal"):
        req = _req("/stadtteil/graefrath/", ip="10.23.1.1", q="Brot")
        req.portal = _portal()
        portal_views.portal_home(req, district="graefrath")
    assert SearchQueryLog.objects.filter(filters_key__contains="stadtteil=graefrath").exists()


def test_entdecken_prefilters_are_part_of_the_key():
    _listing("Brot", business_type="bakery")
    _entdecken(q="Brot", city="Solingen", type="bakery")
    _entdecken(q="Brot", city="Solingen", type="butcher")
    keys = sorted(SearchQueryLog.objects.values_list("filters_key", flat=True))
    assert keys == ["type=bakery", "type=butcher"]


def test_short_query_with_filter_logs_the_filter():
    _listing("Pizza", district="graefrath")
    _portal_search(q="p", stadtteil="graefrath")
    row = SearchQueryLog.objects.get()
    assert row.query_norm == "" and "stadtteil=graefrath" in row.filters_key


def test_single_searches_are_purged_earlier():
    today = timezone.localdate()
    single = _row(today - timedelta(days=31), searches=1)
    popular = _row(today - timedelta(days=31), searches=5)
    tasks.purge_search_log()
    assert not SearchQueryLog.objects.filter(pk=single.pk).exists()
    assert SearchQueryLog.objects.filter(pk=popular.pk).exists()


def test_csv_safe_covers_pipe_and_percent():
    assert _csv_safe("|cmd") == "'|cmd" and _csv_safe("%x") == "'%x"


def test_count_runs_inside_savepoint():
    """Сбой подсчёта не отравляет внешнюю транзакцию (django-reviewer LOW)."""
    _listing("Messer")
    with mock.patch.object(search_log, "_count_capped", side_effect=DatabaseError("x")):
        assert _portal_search(q="Messer").status_code == 200
    assert AggregatorListing.objects.count() == 1
