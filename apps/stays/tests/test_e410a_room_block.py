"""KA-12 E4.10a: блок дат на конкретную комнату (ремонт 104).

Комната с блоком гостю не назначается; в ёмкости блок считается так же, как
блок категории (один номер); в шахматке стоит в полосе своей комнаты; блок на
комнату, где уже живёт гость, — отказ «сначала переназначьте гостя»."""

from datetime import date, timedelta

import pytest

from apps.stays import availability, services
from apps.stays.models import Customer, Room, StayBooking, StayUnit, UnitBlock

pytestmark = pytest.mark.django_db

D0 = date.today() + timedelta(days=10)


def _unit(n=2):
    unit = StayUnit.objects.create(name="DZ", quantity=n, max_guests=2, price_cents=9000)
    rooms = [Room.objects.create(unit=unit, number=str(101 + i), sort_order=i) for i in range(n)]
    return unit, rooms


def _booking(unit, arrival=D0, nights=2, room=None):
    return StayBooking.objects.create(
        unit=unit,
        room=room,
        customer=Customer.objects.create(name="Gast", email="g@t.de"),
        arrival=arrival,
        departure=arrival + timedelta(days=nights),
        guests=2,
        status=StayBooking.STATUS_CONFIRMED,
    )


def test_room_block_excluded_from_free_rooms():
    unit, (r101, r102) = _unit()
    services.create_block(unit, D0, D0 + timedelta(days=1), "Renovierung", room=r102)
    b = _booking(unit)
    assert [r.number for r in services.free_rooms_for(b)] == ["101"]


def test_room_block_touching_departure_day_does_not_block():
    """Блок начинается в день выезда — ночь выезда свободна (departure эксклюзивен)."""
    unit, (r101, r102) = _unit()
    services.create_block(unit, D0 + timedelta(days=2), D0 + timedelta(days=3), "", room=r102)
    b = _booking(unit)
    assert {r.number for r in services.free_rooms_for(b)} == {"101", "102"}


def test_assign_blocked_room_raises():
    unit, (r101, r102) = _unit()
    services.create_block(unit, D0, D0, "", room=r102)
    b = _booking(unit)
    with pytest.raises(services.RoomConflict):
        services.assign_room(b, r102)
    services.assign_room(b, r101)
    b.refresh_from_db()
    assert b.room_id == r101.id


def test_room_block_counts_once_in_capacity():
    unit, (r101, r102) = _unit()
    plain_unit, _rooms = _unit()
    services.create_block(unit, D0, D0 + timedelta(days=1), "", room=r102)
    UnitBlock.objects.create(unit=plain_unit, start_date=D0, end_date=D0 + timedelta(days=1))
    end = D0 + timedelta(days=2)
    assert availability.range_available(unit, D0, end) == availability.range_available(
        plain_unit, D0, end
    )


def test_block_on_occupied_room_conflicts():
    unit, (r101, r102) = _unit()
    _booking(unit, room=r101)
    with pytest.raises(services.RoomConflict):
        services.create_block(unit, D0 + timedelta(days=1), D0 + timedelta(days=4), "", room=r101)
    assert not UnitBlock.objects.filter(room=r101).exists()


def test_block_with_foreign_room_conflicts():
    unit, _rooms = _unit()
    other, (foreign, _x) = _unit()
    with pytest.raises(services.RoomConflict):
        services.create_block(unit, D0, D0, "", room=foreign)


def test_room_block_rendered_in_room_lane():
    unit, (r101, r102) = _unit()
    services.create_block(unit, D0, D0 + timedelta(days=1), "Renovierung", room=r102)
    blocks = list(UnitBlock.objects.filter(unit=unit))
    rows = availability.room_lane_rows(unit, [r101, r102], D0, 7, [], blocks)
    lane_102 = next(r for r in rows if r["room_id"] == r102.id)
    assert any(c.get("kind") == "block" for c in lane_102["cells"]), lane_102
    # в «ohne Zimmer» блока нет
    assert not [r for r in rows if r["room_id"] is None]


def test_category_block_still_in_unassigned_lane():
    unit, (r101, r102) = _unit()
    UnitBlock.objects.create(unit=unit, start_date=D0, end_date=D0)
    blocks = list(UnitBlock.objects.filter(unit=unit))
    rows = availability.room_lane_rows(unit, [r101, r102], D0, 7, [], blocks)
    assert [r for r in rows if r["room_id"] is None]
