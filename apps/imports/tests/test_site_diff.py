"""T-8.27f: повторный импорт — диф new/changed/unchanged/removed и «Bestätigen»."""

from decimal import Decimal
from unittest import mock

import pytest

from apps.catalog.models import Product
from apps.core.ssrf import Fetched
from apps.imports.models import SiteImportItem, SiteImportRun
from apps.imports.site import apply, diff, service
from apps.imports.tests.site_fakes import html
from apps.tenants.tests.factories import TenantFactory

ROOT = "https://laden.example/"


def test_new_changed_unchanged_removed():
    applied = {
        "a": {
            "fingerprint": "1",
            "data": {"name": "A", "price": "1.00"},
            "target_kind": "product",
            "target_id": "x",
        },
        "b": {
            "fingerprint": "2",
            "data": {"name": "B", "price": "2.00"},
            "target_kind": "product",
            "target_id": "y",
        },
        "c": {
            "fingerprint": "3",
            "data": {"name": "C"},
            "target_kind": "product",
            "target_id": "z",
        },
    }
    candidates = [
        {"identity_key": "a", "fingerprint": "1", "data": {"name": "A", "price": "1.00"}},
        {"identity_key": "b", "fingerprint": "9", "data": {"name": "B", "price": "2.50"}},
        {"identity_key": "d", "fingerprint": "4", "data": {"name": "D"}},
    ]
    out, removed = diff.compare(candidates, applied)
    assert [c["diff"] for c in out] == ["unchanged", "changed", "new"]
    assert out[1]["previous"] == {"price": "2.00"}
    assert [r["identity_key"] for r in removed] == ["c"] and removed[0]["target_id"] == "z"


def _site(products):
    blocks = [{"@type": "Product", "name": n, "offers": {"price": p}} for n, p in products]
    body = html(jsonld=blocks).encode()

    def fetch(url, **kw):
        if url == ROOT:
            return Fetched(url, 200, "text/html", body)
        return Fetched(url, 404, "text/html", b"")

    return fetch


def _crawl(products):
    run = SiteImportRun.objects.create(
        start_url=ROOT, host="laden.example", consent_at="2026-10-17T10:00Z", consent_version="x"
    )
    service.execute(run, fetch=_site(products))
    run.refresh_from_db()
    return run


def _apply_all(run):
    tenant = TenantFactory.build(schema_name="laden", subscription_status="trial")
    with mock.patch.object(apply, "_enqueue_images"):
        return apply.apply_items(run, tenant, {str(i.pk): {} for i in run.items.all()})


@pytest.mark.django_db
def test_second_run_diffs_against_applied(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    first = _crawl([("Brot", "3.00"), ("Kuchen", "2.00"), ("Honig", "5.00")])
    _apply_all(first)
    second = _crawl([("Brot", "3.00"), ("Kuchen", "2.40"), ("Saft", "1.50")])
    by_name = {i.data["name"]: i.diff for i in second.items.all()}
    assert by_name == {"Brot": "unchanged", "Kuchen": "changed", "Saft": "new", "Honig": "removed"}
    assert second.items.get(data__name="Kuchen").data["previous"] == {"price": "2.00"}


@pytest.mark.django_db
def test_removed_deactivates_not_deletes_and_confirm_sets_confirmed_at(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    first = _crawl([("Brot", "3.00"), ("Honig", "5.00")])
    _apply_all(first)
    honig = Product.objects.get(name__de="Honig")
    second = _crawl([("Brot", "3.00")])
    _apply_all(second)
    honig.refresh_from_db()
    assert honig.is_active is False and Product.objects.count() == 2
    brot = second.items.get(data__name="Brot")
    assert brot.diff == SiteImportItem.DIFF_UNCHANGED and brot.confirmed_at is not None
    assert Product.objects.get(name__de="Brot").base_price == Decimal("3.00")


@pytest.mark.django_db
def test_changed_updates_same_product(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    _apply_all(_crawl([("Kuchen", "2.00")]))
    _apply_all(_crawl([("Kuchen", "2.40")]))
    assert Product.objects.count() == 1
    assert Product.objects.get().base_price == Decimal("2.40")


@pytest.mark.django_db
def test_removed_item_left_unselected_stays_active(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    _apply_all(_crawl([("Honig", "5.00")]))
    second = _crawl([])  # пустой ответ сайта
    tenant = TenantFactory.build(schema_name="laden", subscription_status="trial")
    with mock.patch.object(apply, "_enqueue_images"):
        apply.apply_items(second, tenant, {})
    assert Product.objects.get().is_active is True


@pytest.mark.django_db
def test_deactivated_items_free_the_limit(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    settings.IMPORT_FREE_ITEMS = 1
    _apply_all(_crawl([("Honig", "5.00")]))
    assert apply.used_count() == 1
    _apply_all(_crawl([("Saft", "1.00")]))  # Honig пропал (отключён), Saft — новый
    assert apply.used_count() == 1
    assert Product.objects.filter(is_active=True).get().name["de"] == "Saft"
