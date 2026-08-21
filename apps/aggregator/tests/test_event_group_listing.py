"""6c: заезды тура / серия событий — ОДНА запись агрегатора (групповой листинг).

План docs/mx-followups-plan-2026-08-21.md. Payload = ближайший будущий заезд;
per-event строки групповых чистятся; beat перекатывает протухшие записи.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.events.models import Event, Tour
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("slug", "reisen")
    kw.setdefault("name", "Reisen X")
    return TenantFactory(schema_name="public", **kw)


def _departure(tour=None, days=10, **kw):
    defaults = {
        "title": "Manali–Leh",
        "starts_at": timezone.now() + timedelta(days=days),
        "price_cents": 199000,
        "status": Event.STATUS_PUBLISHED,
        "tour": tour,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_tour_departures_collapse_to_one_listing():
    _tenant()
    tour = Tour.objects.create(title="Manali–Leh", slug="manali-leh", is_published=True)
    d1 = _departure(tour, days=30)
    d2 = _departure(tour, days=10)  # ближайший
    assert tasks.sync_event_listing("public", str(d1.id)) == "upserted"
    assert tasks.sync_event_listing("public", str(d2.id)) == "upserted"

    rows = AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_EVENT)
    assert rows.count() == 1
    row = rows.get()
    assert row.source_ref == f"tour:{tour.pk}"
    assert row.title_text == "Manali–Leh"
    assert row.starts_at == d2.starts_at  # payload = ближайший заезд
    assert row.detail_url.endswith("/tour/manali-leh/")


def test_series_groups_and_detail_links_nearest_event():
    _tenant()
    sid = uuid.uuid4()
    e1 = _departure(None, days=20, series_id=sid, title="Kurs")
    e2 = _departure(None, days=5, series_id=sid, title="Kurs")
    tasks.sync_event_listing("public", str(e1.id))
    rows = AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_EVENT)
    assert rows.count() == 1
    row = rows.get()
    assert row.source_ref == f"series:{sid}"
    assert row.detail_url.endswith(f"/veranstaltung/{e2.id}/")


def test_group_row_replaces_legacy_per_event_row():
    """Миграционный путь: старая per-event строка группового события удаляется."""
    _tenant()
    tour = Tour.objects.create(title="T", slug="t", is_published=True)
    d = _departure(tour)
    # Легаси-строка (как до 6c).
    AggregatorListing.objects.create(
        tenant_schema="public",
        listing_kind=AggregatorListing.KIND_EVENT,
        source_ref=str(d.id),
        title={"de": "alt"},
    )
    tasks.sync_event_listing("public", str(d.id))
    refs = set(
        AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_EVENT).values_list(
            "source_ref", flat=True
        )
    )
    assert refs == {f"tour:{tour.pk}"}


def test_roll_moves_stale_group_to_next_departure():
    """Beat: ближайший заезд прошёл → запись перекатывается на следующий;
    дат больше нет → запись удаляется."""
    _tenant()
    tour = Tour.objects.create(title="T", slug="t2", is_published=True)
    nxt = _departure(tour, days=40)
    row_key = {"listing_kind": AggregatorListing.KIND_EVENT, "source_ref": f"tour:{tour.pk}"}
    tasks.sync_event_listing("public", str(nxt.id))
    # Симулируем протухание: payload указывает в прошлое.
    AggregatorListing.objects.filter(**row_key).update(starts_at=timezone.now() - timedelta(days=1))
    assert tasks.roll_event_group_listings() == 1
    assert AggregatorListing.objects.get(**row_key).starts_at == nxt.starts_at

    # Заездов больше нет → удаление.
    Event.objects.all().delete()
    AggregatorListing.objects.filter(**row_key).update(starts_at=timezone.now() - timedelta(days=1))
    tasks.roll_event_group_listings()
    assert not AggregatorListing.objects.filter(**row_key).exists()


def test_reconcile_keeps_group_rows():
    _tenant()
    tour = Tour.objects.create(title="T", slug="t3", is_published=True)
    _departure(tour, days=15)
    solo = _departure(None, days=8, title="Solo")
    tasks.reconcile_schema("public")
    refs = set(
        AggregatorListing.objects.filter(listing_kind=AggregatorListing.KIND_EVENT).values_list(
            "source_ref", flat=True
        )
    )
    assert refs == {f"tour:{tour.pk}", str(solo.id)}


# --- витринный листинг (свод в one-card) ---------------------------------------


def test_storefront_index_collapses_group(client):
    """6c: /veranstaltung/ показывает серию одной карточкой с бейджем «+N Termine»."""
    from django.test import RequestFactory

    from apps.events import public_views

    tenant = _tenant()
    tour = Tour.objects.create(title="Manali–Leh", slug="ml", is_published=True)
    _departure(tour, days=10)
    _departure(tour, days=30)
    _departure(None, days=5, title="Solo-Event")

    request = RequestFactory().get("/veranstaltung/")
    request.tenant = tenant
    request.session = {}
    response = public_views.veranstaltung_index(request)
    body = response.content.decode()
    assert body.count("Manali–Leh") >= 1
    assert "+1 Termine" in body  # второй заезд свёрнут в бейдж
    assert "Solo-Event" in body
