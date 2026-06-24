"""G11: каналы продаж + нормализованный импорт броней из OTA."""

from datetime import date, timedelta

import pytest

from apps.stays import availability
from apps.stays.models import Channel, StayBooking, StayUnit
from apps.stays.services import import_external_booking

pytestmark = pytest.mark.django_db

D0 = date(2030, 6, 3)


def _unit(**kw):
    defaults = {"name": "Z", "quantity": 1, "price_cents": 9000, "max_guests": 2}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def test_import_creates_booking_with_channel_and_ref():
    unit = _unit()
    b = import_external_booking(
        kind=Channel.KIND_BOOKING,
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="OTA Gast",
        external_ref="BKG-1",
    )
    assert b is not None
    assert b.source_channel == "booking" and b.external_ref == "BKG-1"
    assert b.status == StayBooking.STATUS_CONFIRMED


def test_import_is_idempotent_by_ref():
    unit = _unit()
    a = import_external_booking(
        kind=Channel.KIND_BOOKING,
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="G",
        external_ref="BKG-2",
    )
    b = import_external_booking(
        kind=Channel.KIND_BOOKING,
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="G",
        external_ref="BKG-2",
    )
    assert a.pk == b.pk
    assert StayBooking.objects.filter(external_ref="BKG-2").count() == 1


def test_import_conflict_blocks_dates_and_returns_none():
    unit = _unit(quantity=1)
    # первый источник занял единственный номер на даты
    import_external_booking(
        kind=Channel.KIND_AIRBNB,
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="A",
        external_ref="AIR-1",
    )
    # вторая бронь на те же даты — конфликт → None + блок
    res = import_external_booking(
        kind=Channel.KIND_BOOKING,
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="B",
        external_ref="BKG-3",
    )
    assert res is None
    # даты теперь недоступны (блок поставлен)
    assert availability.range_available(unit, D0, D0 + timedelta(days=2)) is False
