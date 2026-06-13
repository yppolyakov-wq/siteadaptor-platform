"""G10 / G10a: услуги (Service) — слоты по длительности, бронь со снимком цены,
подбор ресурса бизнес-уровня, выручка за выполненную услугу."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.booking import availability, services
from apps.booking.models import AvailabilityRule, Resource, Service
from apps.booking.state_machine import BookingSM
from apps.finance.models import RevenueEntry

pytestmark = pytest.mark.django_db


def _resource(**kwargs):
    return Resource.objects.create(name=f"Platz {uuid.uuid4().hex[:6]}", **kwargs)


def _service(**kwargs):
    kwargs.setdefault("name", "Ölwechsel")
    kwargs.setdefault("duration_minutes", 60)
    kwargs.setdefault("price_cents", 4900)
    return Service.objects.create(**kwargs)


def _future_day(days=7):
    return timezone.localdate() + timedelta(days=days)


def _rule(resource, day, start="09:00", end="12:00", slot=30):
    return AvailabilityRule.objects.create(
        resource=resource, weekday=day.weekday(), start_time=start, end_time=end, slot_minutes=slot
    )


def _aware(day, hour, minute=0):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


# --- слоты по длительности услуги -------------------------------------------------


def test_free_slots_uses_service_duration():
    resource = _resource()
    day = _future_day()
    _rule(resource, day, "09:00", "12:00", slot=30)
    slots = availability.free_slots(resource, day, duration_minutes=60)
    # длина слота = 60 мин; старты каждые 30: 9:00, 9:30, 10:00, 10:30, 11:00
    assert slots[0][1] - slots[0][0] == timedelta(minutes=60)
    assert len(slots) == 5


def test_service_slots_and_assign_resource():
    r1, r2 = _resource(), _resource()
    day = _future_day()
    _rule(r1, day)
    _rule(r2, day)
    service = _service(duration_minutes=30)
    starts = availability.service_slots(service, day)
    assert starts and starts == sorted(starts)
    # ресурс назначается на свободный старт
    assert availability.assign_resource(service, starts[0]) in (r1, r2)


def test_assign_resource_none_when_full():
    resource = _resource()  # capacity 1
    day = _future_day()
    _rule(resource, day)
    service = _service(duration_minutes=30)
    start = availability.service_slots(service, day)[0]
    end = start + timedelta(minutes=30)
    services.book(resource, start=start, end=end, name="Gast")  # занял единственный ресурс
    assert availability.assign_resource(service, start) is None


# --- бронь со снимком цены + выручка ----------------------------------------------


def test_book_snapshots_service_and_price():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    assert booking.service == service and booking.price_cents == 4900


def test_fulfilled_service_records_revenue():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    sm = BookingSM()
    booking = sm.apply(booking, "confirmed")
    sm.apply(booking, "fulfilled")
    entry = RevenueEntry.objects.get(source="booking", source_ref=str(booking.id))
    assert entry.amount == Decimal("49.00") and entry.vat_rate == Decimal("19.00")


def test_fulfilled_without_price_no_revenue():
    resource = _resource()
    start = _aware(_future_day(), 9)
    booking = services.book(resource, start=start, end=start + timedelta(hours=1), name="Tisch")
    sm = BookingSM()
    sm.apply(sm.apply(booking, "confirmed"), "fulfilled")
    assert not RevenueEntry.objects.filter(source="booking").exists()
