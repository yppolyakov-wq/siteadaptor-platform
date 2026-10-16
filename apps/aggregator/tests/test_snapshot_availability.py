"""T-8.26 п.3 (3b): доступность акций и событий в снимке каталога города."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.events.models import Event, Ticket, Tour
from apps.promotions.models import Customer
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("slug", "biz")
    kw.setdefault("city", "Solingen")
    return TenantFactory(schema_name="public", **kw)


def _promo_row(promo):
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    return AggregatorListing.objects.get(listing_kind="promotion", source_ref=str(promo.id))


@pytest.mark.parametrize("qty,expected", [(0, "sold_out"), (None, ""), (3, "")])
def test_promotion_limit_drives_availability(qty, expected):
    _tenant()
    promo = PromotionFactory(status="active", available_quantity=qty)
    assert _promo_row(promo).availability == expected


def test_mystery_promotion_hides_price_but_not_sold_out():
    _tenant()
    promo = PromotionFactory(status="active", available_quantity=0, discount_style="mystery")
    row = _promo_row(promo)
    assert row.new_price is None and row.availability == "sold_out"


def _event(**kw):
    defaults = {
        "title": "Konzert",
        "starts_at": timezone.now() + timedelta(days=5),
        "price_cents": 1500,
        "status": Event.STATUS_PUBLISHED,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _ticket(event, qty=1, **kw):
    customer = Customer.objects.create(email=f"{uuid.uuid4().hex}@k.test", name="K")
    kw.setdefault("status", Ticket.STATUS_CONFIRMED)
    kw.setdefault("reference_code", f"E-{uuid.uuid4().hex[:6].upper()}")
    return Ticket.objects.create(event=event, customer=customer, quantity=qty, **kw)


def _event_row(event):
    assert tasks.sync_event_listing("public", str(event.id)) == "upserted"
    return AggregatorListing.objects.get(listing_kind="event", source_ref=str(event.id))


def test_event_sold_out_by_capacity():
    _tenant()
    event = _event(capacity=2)
    assert _event_row(event).availability == ""
    _ticket(event, qty=2)
    assert _event_row(event).availability == "sold_out"


def test_group_listing_sold_out_only_if_all_future_departures_sold_out():
    _tenant()
    tour = Tour.objects.create(title="Manali–Leh", slug="manali-leh", is_published=True)
    near = _event(tour=tour, capacity=1, starts_at=timezone.now() + timedelta(days=3))
    far = _event(tour=tour, capacity=1, starts_at=timezone.now() + timedelta(days=30))
    _ticket(near)
    tasks.sync_event_listing("public", str(near.id))
    row = AggregatorListing.objects.get(listing_kind="event", source_ref=f"tour:{tour.pk}")
    assert row.availability == ""  # ближайший распродан, следующий свободен
    _ticket(far)
    tasks.sync_event_listing("public", str(far.id))
    row.refresh_from_db()
    assert row.availability == "sold_out"


def test_claim_and_return_units_enqueue_promotion_sync(
    monkeypatch, django_capture_on_commit_callbacks
):
    from apps.promotions import price_layer

    _tenant()
    calls = []
    monkeypatch.setattr(
        tasks.sync_aggregator_listing,
        "apply_async",
        lambda kwargs=None, countdown=None, **kw: calls.append((kwargs, countdown)),
    )
    promo = PromotionFactory(status="active", available_quantity=2)
    with django_capture_on_commit_callbacks(execute=True):
        price_layer.claim_units(promo, 1)
        price_layer.return_units(promo.id, 1)
    assert len(calls) == 2 and all(k["promotion_id"] == str(promo.id) for k, _ in calls)
    assert all(c == 30 for _, c in calls)


def test_ticket_save_enqueues_event_sync(monkeypatch, django_capture_on_commit_callbacks):
    _tenant()
    calls = []
    monkeypatch.setattr(
        tasks.sync_aggregator_event,
        "apply_async",
        lambda kwargs=None, countdown=None, **kw: calls.append(kwargs),
    )
    event = _event(capacity=5)
    with django_capture_on_commit_callbacks(execute=True):
        _ticket(event)
    assert calls and calls[-1]["event_id"] == str(event.id)


def test_sold_out_constant_matches_model():
    assert tasks.AVAILABILITY_SOLD_OUT == AggregatorListing.AVAILABILITY_SOLD_OUT


def test_jsonld_sold_out_for_promotion_and_event():
    from types import SimpleNamespace

    from apps.aggregator import structured

    for kind in ("promotion", "event"):
        iri = structured.availability_iri(
            SimpleNamespace(listing_kind=kind, availability="sold_out")
        )
        assert iri == "https://schema.org/SoldOut", kind
