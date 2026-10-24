"""KA-12 E4.10b: бронь на N номеров хранит все назначенные номера.

Первый — `room` (его читают шахматка, карточка, хаускипинг), остальные —
`extra_rooms`; всего назначено не больше `rooms`; занятые доп. номера не
предлагаются другим броням; смена категории снимает все; выезд пачкает все."""

import uuid
from datetime import date, timedelta

import pytest

from apps.stays import availability, services
from apps.stays.models import Customer, Room, StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = date.today() + timedelta(days=10)


def _unit(n=3):
    unit = StayUnit.objects.create(name="DZ", quantity=n, max_guests=2, price_cents=9000)
    rooms = [Room.objects.create(unit=unit, number=str(101 + i), sort_order=i) for i in range(n)]
    return unit, rooms


def _booking(unit, rooms=1, arrival=D0):
    return StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email="g@t.de"),
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        guests=2,
        rooms=rooms,
        status=StayBooking.STATUS_CONFIRMED,
        reference_code=f"S-{uuid.uuid4().hex[:8].upper()}",
    )


def test_assign_two_rooms_to_multiroom():
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=2)
    services.assign_rooms(b, [r1, r2])
    b.refresh_from_db()
    assert b.room_id == r1.id
    assert [r.number for r in services.assigned_rooms(b)] == ["101", "102"]


def test_cannot_assign_more_than_rooms():
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=2)
    with pytest.raises(services.RoomConflict):
        services.assign_rooms(b, [r1, r2, r3])
    b.refresh_from_db()
    assert b.room_id is None and not b.extra_rooms.exists()


def test_extra_rooms_are_busy_for_other_bookings():
    unit, (r1, r2, r3) = _unit()
    services.assign_rooms(_booking(unit, rooms=2), [r1, r2])
    other = _booking(unit)
    assert [r.number for r in services.free_rooms_for(other)] == ["103"]
    with pytest.raises(services.RoomConflict):
        services.assign_room(other, r2)


def test_move_to_other_unit_clears_all_assignments():
    unit, (r1, r2, _r3) = _unit()
    dest, _dest_rooms = _unit()
    b = _booking(unit, rooms=2)
    services.assign_rooms(b, [r1, r2])
    services.move_stay(b, arrival=b.arrival, departure=b.departure, unit=dest, reprice=False)
    b.refresh_from_db()
    assert b.room_id is None and not b.extra_rooms.exists()


def test_checkout_marks_all_rooms_dirty():
    from apps.stays.state_machine import StayBookingSM

    unit, (r1, r2, _r3) = _unit()
    b = _booking(unit, rooms=2)
    services.assign_rooms(b, [r1, r2])
    StayBookingSM().apply(b, StayBooking.STATUS_FULFILLED)
    assert set(
        Room.objects.filter(pk__in=[r1.pk, r2.pk]).values_list("housekeeping", flat=True)
    ) == {Room.HK_DIRTY}


def test_lane_rows_show_booking_in_each_assigned_room():
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=3)
    services.assign_rooms(b, [r1, r2])
    bookings = list(StayBooking.objects.filter(pk=b.pk).prefetch_related("extra_rooms"))
    rows = availability.room_lane_rows(unit, [r1, r2, r3], D0, 7, bookings, [])
    by_room = {r["room_id"]: r for r in rows}
    for room in (r1, r2):
        assert any(c.get("kind") == "booking" for c in by_room[room.id]["cells"])
    assert not any(c.get("kind") == "booking" for c in by_room[r3.id]["cells"])
    # третий номер ещё не назначен — одна «Zimmer offen»-полоса
    unassigned = [r for r in rows if r["room_id"] is None]
    assert len(unassigned) == 1


def test_drop_conflicting_rooms_keeps_free_ones():
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=2)
    services.assign_rooms(b, [r1, r2])
    later = D0 + timedelta(days=5)
    blocker = _booking(unit, arrival=later)
    services.assign_room(blocker, r2)
    services.move_stay(b, arrival=later, departure=later + timedelta(days=2), reprice=False)
    services.drop_conflicting_rooms(b)
    b.refresh_from_db()
    assert [r.number for r in services.assigned_rooms(b)] == ["101"]


def test_edit_form_assigns_rooms_and_clears_extras(settings):
    from apps.stays import views
    from apps.stays.tests.test_belegungsplan import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=2)
    data = {
        "action": "update",
        "arrival": b.arrival.isoformat(),
        "departure": b.departure.isoformat(),
        "unit": str(unit.pk),
        "adults": "2",
        "children": "0",
        "reprice": "0",
        "room": str(r1.pk),
        "room_extra_present": "1",
        "room_extra": [str(r3.pk)],
    }
    views.stay_action(_req("post", data=data), pk=b.pk)
    b.refresh_from_db()
    assert [r.number for r in services.assigned_rooms(b)] == ["101", "103"]
    # снять доп. номер: селект пуст, сентинел есть
    views.stay_action(_req("post", data={**data, "room_extra": [""]}), pk=b.pk)
    b.refresh_from_db()
    assert [r.number for r in services.assigned_rooms(b)] == ["101"]


def test_edit_form_without_sentinel_keeps_extras(settings):
    """Форма без полей доп. номеров (старая/компактная) не стирает их (W0)."""
    from apps.stays import views
    from apps.stays.tests.test_belegungsplan import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    unit, (r1, r2, r3) = _unit()
    b = _booking(unit, rooms=2)
    services.assign_rooms(b, [r1, r2])
    views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": b.arrival.isoformat(),
                "departure": b.departure.isoformat(),
                "unit": str(unit.pk),
                "adults": "2",
                "children": "0",
                "reprice": "0",
                "room": str(r1.pk),
            },
        ),
        pk=b.pk,
    )
    b.refresh_from_db()
    assert [r.number for r in services.assigned_rooms(b)] == ["101", "102"]
