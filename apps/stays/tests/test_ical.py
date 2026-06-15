"""A5b: iCal экспорт/импорт — build_feed/parse_events + синк блоков."""

from datetime import date
from unittest.mock import patch

import pytest

from apps.stays import ical, services
from apps.stays.models import ICalSource, StayBooking, StayUnit, UnitBlock

pytestmark = pytest.mark.django_db


def _unit(**kw):
    defaults = {"name": "FeWo", "quantity": 1, "price_cents": 10000, "max_guests": 4}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def test_parse_events_reads_all_day_vevents():
    text = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:abc-123\r\n"
        "DTSTART;VALUE=DATE:20260701\r\n"
        "DTEND;VALUE=DATE:20260705\r\n"
        "SUMMARY:Booked\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = ical.parse_events(text)
    assert events == [("abc-123", date(2026, 7, 1), date(2026, 7, 5))]


def test_parse_events_handles_datetime_dtstart():
    text = "BEGIN:VEVENT\r\nDTSTART:20260701T140000Z\r\nDTEND:20260703T100000Z\r\nEND:VEVENT\r\n"
    events = ical.parse_events(text)
    assert events == [("", date(2026, 7, 1), date(2026, 7, 3))]


def test_build_feed_round_trips_booking_and_block():
    unit = _unit()
    booking = StayBooking.objects.create(
        unit=unit,
        customer=services._get_or_create_customer(name="K", email="k@test.de", phone=""),
        reference_code="S-ABC123",
        arrival=date(2026, 7, 1),
        departure=date(2026, 7, 4),
    )
    block = UnitBlock.objects.create(
        unit=unit, start_date=date(2026, 8, 1), end_date=date(2026, 8, 2)
    )
    feed = ical.build_feed(unit, [booking], [block], host="shop.test")
    assert "BEGIN:VCALENDAR" in feed and "END:VCALENDAR" in feed
    events = ical.parse_events(feed)
    # бронь: DTEND = departure (эксклюзивно); блок: end_date+1 (включительно→эксклюзивно)
    starts = {(s, e) for _u, s, e in events}
    assert (date(2026, 7, 1), date(2026, 7, 4)) in starts
    assert (date(2026, 8, 1), date(2026, 8, 3)) in starts


def test_sync_ical_source_creates_inclusive_blocks():
    unit = _unit()
    source = ICalSource.objects.create(unit=unit, label="Airbnb", url="https://x/cal.ics")
    feed = (
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260901\r\nDTEND;VALUE=DATE:20260905\r\nEND:VEVENT\r\n"
    )

    class _Resp:
        text = feed

        def raise_for_status(self):
            pass

    with patch("requests.get", return_value=_Resp()):
        created = services.sync_ical_source(source)
    assert created == 1
    block = UnitBlock.objects.get(unit=unit, source_id_ref=str(source.pk))
    # DTEND 09-05 эксклюзивно → последняя занятая ночь 09-04 (включительно)
    assert block.start_date == date(2026, 9, 1)
    assert block.end_date == date(2026, 9, 4)
    source.refresh_from_db()
    assert source.last_status == "OK: 1"
    assert source.last_synced_at is not None


def test_sync_is_idempotent_and_keeps_manual_blocks():
    unit = _unit()
    manual = UnitBlock.objects.create(
        unit=unit, start_date=date(2026, 10, 1), end_date=date(2026, 10, 2)
    )
    source = ICalSource.objects.create(unit=unit, url="https://x/cal.ics")
    feed = (
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20261101\r\nDTEND;VALUE=DATE:20261103\r\nEND:VEVENT\r\n"
    )

    class _Resp:
        text = feed

        def raise_for_status(self):
            pass

    with patch("requests.get", return_value=_Resp()):
        services.sync_ical_source(source)
        services.sync_ical_source(source)  # повтор не плодит блоки
    assert UnitBlock.objects.filter(unit=unit, source_id_ref=str(source.pk)).count() == 1
    assert UnitBlock.objects.filter(pk=manual.pk).exists()  # ручной блок не тронут


def test_sync_keeps_blocks_on_network_error():
    unit = _unit()
    source = ICalSource.objects.create(unit=unit, url="https://x/cal.ics")
    UnitBlock.objects.create(
        unit=unit,
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 2),
        source_id_ref=str(source.pk),
    )
    with patch("requests.get", side_effect=Exception("boom")):
        created = services.sync_ical_source(source)
    assert created == 0
    # при сбое старые блоки источника НЕ удаляются
    assert UnitBlock.objects.filter(unit=unit, source_id_ref=str(source.pk)).count() == 1
    source.refresh_from_db()
    assert "boom" in source.last_status
