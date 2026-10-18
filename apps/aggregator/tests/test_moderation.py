"""D2b-1 (T-8.10e): проверка карточек каталога города правилами → очередь модератора.

План — docs/d2-ai-text-check-plan-2026-10-17.md §6, §7 (D2b-1). Решения владельца:
автоматика сама НЕ скрывает (В-2), машинная пометка — не голос жалоб (В-3)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.aggregator import moderation, reports, tasks
from apps.aggregator.models import AggregatorListing, ListingReport

pytestmark = pytest.mark.django_db


def _listing(**kw):
    defaults = {
        "tenant_schema": "t_mod",
        "tenant_slug": "mod",
        "business_name": "Bäckerei Mod",
        "business_type": "bakery",
        "city": "Solingen",
        "listing_kind": "promotion",
        "source_ref": str(uuid.uuid4()),
        "title": {"de": "Frische Brezeln"},
        "teaser": {"de": "Vom Morgen"},
        "new_price": "2.50",
        "detail_url": "https://mod.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _auto(listing):
    return ListingReport.objects.filter(listing=listing, ip_hash=moderation.AUTO_MARKER)


def test_clean_listing_not_flagged():
    listing = _listing()
    moderation.moderate(listing)
    assert not _auto(listing).exists()


def test_rule_finding_creates_auto_report_once_per_message():
    listing = _listing(
        title={"de": "Gratis Kaffee – nur heute"}, ends_at=timezone.now() + timedelta(days=6)
    )
    moderation.moderate(listing)
    moderation.moderate(listing)
    (report,) = _auto(listing)
    assert report.message.startswith("[auto:rule]")
    assert "gratis_mit_preis" in report.message
    assert report.reason == ListingReport.REASON_WRONG


def test_resolved_auto_report_does_not_reappear_for_same_text():
    listing = _listing(title={"de": "Gratis Kaffee"})
    moderation.moderate(listing)
    _auto(listing).update(status=ListingReport.STATUS_RESOLVED)
    moderation.moderate(listing)
    assert _auto(listing).count() == 1


def test_changed_text_flags_again():
    listing = _listing(title={"de": "Gratis Kaffee"})
    moderation.moderate(listing)
    _auto(listing).update(status=ListingReport.STATUS_RESOLVED)
    listing.title = {"de": "Kontakt: www.example.de"}
    listing.save()
    moderation.moderate(listing)
    assert _auto(listing).count() == 2


def test_low_only_findings_not_flagged():
    listing = _listing(title={"de": "Frische Brezeln!!!"})
    moderation.moderate(listing)
    assert not _auto(listing).exists()


def test_contact_in_title_flagged_as_spam():
    listing = _listing(title={"de": "Bestellen unter www.example.de"})
    moderation.moderate(listing)
    (report,) = _auto(listing)
    assert report.reason == ListingReport.REASON_SPAM


def test_moderation_never_hides():
    listing = _listing(title={"de": "Gratis Kaffee – nur heute"})
    moderation.moderate(listing)
    listing.refresh_from_db()
    assert listing.hidden_at is None


def test_auto_report_is_not_a_voice():
    listing = _listing(title={"de": "Gratis Kaffee"})
    moderation.moderate(listing)
    reports.file_report(listing, reason="spam", ip_hash="a")
    reports.file_report(listing, reason="spam", ip_hash="b")
    listing.refresh_from_db()
    assert listing.hidden_at is None  # 2 человека + машина ≠ 3 голоса
    reports.file_report(listing, reason="spam", ip_hash="c")
    listing.refresh_from_db()
    assert listing.hidden_at is not None


def test_demo_and_internal_tenants_skipped(monkeypatch):
    demo = _listing(title={"de": "Gratis Kaffee"}, is_demo=True)
    moderation.moderate(demo)
    assert not _auto(demo).exists()
    internal = _listing(title={"de": "Gratis Kaffee"}, tenant_schema="t_int")
    monkeypatch.setattr(moderation, "_internal", lambda schema: schema == "t_int")
    moderation.moderate(internal)
    assert not _auto(internal).exists()


def test_own_duplicate_flagged():
    _listing(title={"de": "Frische Brezeln"}, source_ref="a")
    second = _listing(title={"de": "frische  brezeln"}, source_ref="b")
    moderation.moderate(second)
    (report,) = _auto(second)
    assert "duplikat_eigen" in report.message


def test_duplicate_foreign_tenants_flagged_as_spam():
    for i in range(2):
        _listing(tenant_schema=f"t_other{i}", title={"de": "Mega Deal Kaffee"})
    mine = _listing(title={"de": "Mega Deal Kaffee"})
    moderation.moderate(mine)
    (report,) = _auto(mine)
    assert "duplikat_fremd" in report.message
    assert report.reason == ListingReport.REASON_SPAM


def test_foreign_duplicate_needs_two_other_businesses():
    _listing(tenant_schema="t_other0", title={"de": "Mega Deal Kaffee"})
    mine = _listing(title={"de": "Mega Deal Kaffee"})
    moderation.moderate(mine)
    assert not _auto(mine).exists()


def test_inactive_or_old_duplicates_ignored():
    _listing(title={"de": "Frische Brezeln"}, source_ref="a", is_active=False)
    old = _listing(title={"de": "Frische Brezeln"}, source_ref="b")
    AggregatorListing.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=30)
    )
    second = _listing(title={"de": "Frische Brezeln"}, source_ref="c")
    moderation.moderate(second)
    assert not _auto(second).exists()


def test_changed_listing_enqueues_moderation_on_commit(django_capture_on_commit_callbacks):
    with mock.patch.object(tasks.moderate_listing, "delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            changed = tasks._upsert_listing(
                {"tenant_schema": "t_q", "listing_kind": "promotion", "source_ref": "x"},
                {
                    "tenant_slug": "q",
                    "business_name": "Q",
                    "title": {"de": "Gratis Kaffee"},
                    "teaser": {},
                    "detail_url": "https://q.siteadaptor.de/p/1/",
                },
            )
    assert changed is True
    assert delay.call_count == 1


def test_unchanged_upsert_does_not_enqueue(django_capture_on_commit_callbacks):
    key = {"tenant_schema": "t_q2", "listing_kind": "promotion", "source_ref": "x"}
    defaults = {
        "tenant_slug": "q2",
        "business_name": "Q2",
        "title": {"de": "Brezeln"},
        "teaser": {},
        "detail_url": "https://q2.siteadaptor.de/p/1/",
    }
    with mock.patch.object(tasks.moderate_listing, "delay"):
        tasks._upsert_listing(key, defaults)
    with mock.patch.object(tasks.moderate_listing, "delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            assert tasks._upsert_listing(key, defaults) is False
    assert delay.call_count == 0


def test_task_runs_moderation_and_tolerates_missing_listing():
    listing = _listing(title={"de": "Gratis Kaffee"})
    tasks.moderate_listing(listing_id=listing.pk)
    assert _auto(listing).exists()
    tasks.moderate_listing(listing_id=999_999_999)  # удалена — тихо


def test_broken_moderation_does_not_raise(monkeypatch):
    listing = _listing(title={"de": "Gratis Kaffee"})
    monkeypatch.setattr(moderation, "check_listing", mock.Mock(side_effect=RuntimeError("x")))
    tasks.moderate_listing(listing_id=listing.pk)


def test_admin_source_filter():
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory

    from apps.aggregator.admin import ListingReportAdmin

    listing = _listing(title={"de": "Gratis Kaffee"})
    moderation.moderate(listing)
    reports.file_report(listing, reason="spam", ip_hash="human")
    admin = ListingReportAdmin(ListingReport, AdminSite())
    flt = admin.get_list_filter(RequestFactory().get("/"))
    source = next(f for f in flt if getattr(f, "parameter_name", "") == "quelle")
    qs = ListingReport.objects.filter(listing=listing)
    auto = source(None, {"quelle": ["auto"]}, ListingReport, admin).queryset(None, qs)
    human = source(None, {"quelle": ["meldung"]}, ListingReport, admin).queryset(None, qs)
    assert {r.ip_hash for r in auto} == {moderation.AUTO_MARKER}
    assert {r.ip_hash for r in human} == {"human"}
