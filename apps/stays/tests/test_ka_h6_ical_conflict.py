"""KA-H6 (аудит KA-5d, Z3): импорт iCal больше не создаёт овербукинг молча.

- синк с конфликтом: блок канала остаётся (данные OTA — правда), но статус
  источника и письмо владельцу говорят «Überbuchung»;
- событие фида, совпадающее с уже импортированной бронью канала, не задваивает;
- импорт брони канала (G11) поверх своего iCal-блока проходит, а не теряется."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.tests.dates import future_month_start
from apps.stays import availability, services
from apps.stays.models import ICalSource, StayBooking, StayUnit, UnitBlock

pytestmark = pytest.mark.django_db

D0 = future_month_start(4)
OWNER = SimpleNamespace(owner_email="owner@test.de", schema_name="h6")


def _feed(start, end):
    return (
        "BEGIN:VEVENT\r\n"
        f"DTSTART;VALUE=DATE:{start:%Y%m%d}\r\nDTEND;VALUE=DATE:{end:%Y%m%d}\r\n"
        "END:VEVENT\r\n"
    )


def _unit():
    return StayUnit.objects.create(name="FeWo", quantity=1, price_cents=10000, max_guests=4)


def _sync(source, feed, capture):
    with (
        patch("apps.core.ssrf.safe_get", return_value=feed),
        patch("apps.booking.revenue._tenant", return_value=OWNER),
        patch("apps.notifications.services.notify") as notify,
        capture(execute=True),
    ):
        services.sync_ical_source(source)
    return notify


def _book(unit, arrival, nights=3, **kw):
    return services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=nights), name="Gast", **kw
    )


def test_ical_conflict_keeps_block_and_notifies(django_capture_on_commit_callbacks):
    unit = _unit()
    _book(unit, D0)
    source = ICalSource.objects.create(unit=unit, label="Airbnb", url="https://x/cal.ics")
    notify = _sync(
        source,
        _feed(D0 + timedelta(days=1), D0 + timedelta(days=2)),
        django_capture_on_commit_callbacks,
    )
    assert UnitBlock.objects.filter(unit=unit, source_id_ref=str(source.pk)).count() == 1
    source.refresh_from_db()
    assert "Konflikt" in source.last_status
    notify.assert_called_once()
    assert notify.call_args.kwargs["recipient"] == "owner@test.de"
    key = notify.call_args.kwargs["dedupe_key"]
    notify2 = _sync(
        source,
        _feed(D0 + timedelta(days=1), D0 + timedelta(days=2)),
        django_capture_on_commit_callbacks,
    )
    assert notify2.call_args.kwargs["dedupe_key"] == key  # повтор — тот же ключ дедупа


def test_ical_no_conflict_no_notification(django_capture_on_commit_callbacks):
    unit = _unit()
    source = ICalSource.objects.create(unit=unit, label="Airbnb", url="https://x/cal.ics")
    notify = _sync(source, _feed(D0, D0 + timedelta(days=2)), django_capture_on_commit_callbacks)
    notify.assert_not_called()
    source.refresh_from_db()
    assert source.last_status == "OK: 1"


def test_ical_skips_event_matching_imported_booking(django_capture_on_commit_callbacks):
    unit = _unit()
    booking = _book(unit, D0, source_channel="booking_com", auto_confirm=True)
    StayBooking.objects.filter(pk=booking.pk).update(external_ref="BDC-1")
    source = ICalSource.objects.create(unit=unit, label="Booking", url="https://x/cal.ics")
    notify = _sync(source, _feed(D0, D0 + timedelta(days=3)), django_capture_on_commit_callbacks)
    assert not UnitBlock.objects.filter(unit=unit).exists()
    notify.assert_not_called()


def test_g11_import_replaces_covering_ical_block():
    unit = _unit()
    UnitBlock.objects.create(
        unit=unit,
        start_date=D0,
        end_date=D0 + timedelta(days=2),
        reason="iCal: Booking",
        source_id_ref="ical-1",
    )
    booking = services.import_external_booking(
        kind="booking_com",
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=3),
        name="OTA-Gast",
        external_ref="BDC-2",
    )
    assert booking is not None
    assert not UnitBlock.objects.filter(unit=unit, source_id_ref="ical-1").exists()


def test_g11_import_real_conflict_still_blocks_and_keeps_ical(django_capture_on_commit_callbacks):
    unit = _unit()
    _book(unit, D0)  # настоящая бронь — снятие iCal-блока не поможет
    UnitBlock.objects.create(
        unit=unit, start_date=D0, end_date=D0 + timedelta(days=2), source_id_ref="ical-2"
    )
    with (
        patch("apps.booking.revenue._tenant", return_value=OWNER),
        patch("apps.notifications.services.notify") as notify,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = services.import_external_booking(
            kind="booking_com",
            unit=unit,
            arrival=D0,
            departure=D0 + timedelta(days=3),
            name="OTA",
            external_ref="BDC-3",
        )
    assert result is None
    assert UnitBlock.objects.filter(unit=unit, source_id_ref="ical-2").exists()  # откат
    assert UnitBlock.objects.filter(unit=unit, reason__contains="Import-Konflikt").exists()
    notify.assert_called_once()


def test_overbooked_nights_counts_bookings_and_blocks():
    unit = _unit()
    _book(unit, D0)
    UnitBlock.objects.create(
        unit=unit, start_date=D0 + timedelta(days=1), end_date=D0 + timedelta(days=1)
    )
    assert availability.overbooked_nights(unit, D0, D0 + timedelta(days=5)) == [
        D0 + timedelta(days=1)
    ]


def test_g11_import_keeps_longer_ical_block():
    """Длинный блок «nicht verfügbar» не снимается ради короткой брони канала."""
    unit = _unit()
    UnitBlock.objects.create(
        unit=unit, start_date=D0, end_date=D0 + timedelta(days=20), source_id_ref="ical-long"
    )
    result = services.import_external_booking(
        kind="booking_com",
        unit=unit,
        arrival=D0,
        departure=D0 + timedelta(days=3),
        name="OTA",
        external_ref="BDC-4",
    )
    assert result is None
    assert UnitBlock.objects.filter(source_id_ref="ical-long").exists()


def test_replayed_webhook_does_not_revive_refunded():
    from django.db import connection

    from apps.stays.payments import mark_stay_paid

    unit = _unit()
    booking = _book(unit, D0)
    StayBooking.objects.filter(pk=booking.pk).update(
        payment_state=StayBooking.PAYMENT_REFUNDED, deposit_cents=1000, total_cents=30000
    )
    mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(booking.id))
    booking.refresh_from_db()
    assert booking.payment_state == StayBooking.PAYMENT_REFUNDED
