"""KA-12 Zimmer Z-5b (DF-Z3, О-8 — запрет; Р-4 блок категории через сервис).

Замки: ёмкость (quantity / удаление комнаты) не опускается ниже проданного на
любую ночь от сегодня; занятая (в т. ч. как extra_rooms) комната не удаляется;
отказ quantity не теряет остальные поля формы; блок категории на распроданных
ночах — NoCapacity (раньше молча давал овербукинг)."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core.models import Membership
from apps.stays import capacity, services, views
from apps.stays.models import Customer, Room, StayBooking, StayUnit, UnitBlock
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
D0 = TODAY + timedelta(days=10)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(quantity=3, rooms=0):
    unit = StayUnit.objects.create(
        name=f"DZ {uuid.uuid4().hex[:6]}", quantity=quantity, price_cents=9000
    )
    made = [Room.objects.create(unit=unit, number=str(101 + i)) for i in range(rooms)]
    if rooms:
        services.sync_room_quantity(unit)
        unit.refresh_from_db()
    return unit, made


def _booking(unit, arrival=D0, nights=2, rooms=1, room=None, status="confirmed"):
    return StayBooking.objects.create(
        unit=unit,
        room=room,
        rooms=rooms,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        arrival=arrival,
        departure=arrival + timedelta(days=nights),
        guests=2,
        status=status,
        reference_code=f"S-{uuid.uuid4().hex[:8].upper()}",
    )


# --- sold_by_night ------------------------------------------------------------------


def test_sold_by_night_counts_rooms_skips_cancelled_and_past():
    unit, _ = _unit()
    _booking(unit, rooms=2)
    _booking(unit, nights=1)
    _booking(unit, status="cancelled")
    _booking(unit, arrival=TODAY - timedelta(days=5), nights=2)  # прошлое
    sold = capacity.sold_by_night(unit, TODAY)
    assert sold == {D0: 3, D0 + timedelta(days=1): 2}


def test_sold_by_night_clips_current_stay_to_today():
    unit, _ = _unit()
    _booking(unit, arrival=TODAY - timedelta(days=1), nights=3)
    assert capacity.sold_by_night(unit, TODAY) == {TODAY: 1, TODAY + timedelta(days=1): 1}


# --- set_quantity -------------------------------------------------------------------


def test_set_quantity_below_sold_refused():
    unit, _ = _unit(quantity=3)
    _booking(unit, rooms=2)
    with pytest.raises(capacity.CapacityBelowSold) as exc:
        capacity.set_quantity(unit, 1, TODAY)
    assert (exc.value.day, exc.value.sold) == (D0, 2)
    unit.refresh_from_db()
    assert unit.quantity == 3


def test_set_quantity_equal_to_sold_passes_and_past_does_not_count():
    unit, _ = _unit(quantity=3)
    _booking(unit, rooms=2)
    _booking(unit, arrival=TODAY - timedelta(days=10), rooms=3, nights=2)
    capacity.set_quantity(unit, 2, TODAY)
    unit.refresh_from_db()
    assert unit.quantity == 2


def test_set_quantity_locks_unit():
    unit, _ = _unit(quantity=3)
    with CaptureQueriesContext(connection) as ctx:
        capacity.set_quantity(unit, 2, TODAY)
    assert any("FOR UPDATE" in q["sql"] and "stays_stayunit" in q["sql"] for q in ctx)


# --- delete_room --------------------------------------------------------------------


def test_delete_room_assigned_to_future_booking_refused():
    unit, (r101, _r102, _r103) = _unit(rooms=3)
    b = _booking(unit, room=r101)
    with pytest.raises(capacity.RoomAssigned) as exc:
        capacity.delete_room(r101, TODAY)
    assert exc.value.booking == b
    assert Room.objects.filter(pk=r101.pk).exists()


def test_delete_room_assigned_as_extra_room_refused():
    unit, (r101, r102, _r103) = _unit(rooms=3)
    b = _booking(unit, rooms=2, room=r101)
    b.extra_rooms.add(r102)
    with pytest.raises(capacity.RoomAssigned):
        capacity.delete_room(r102, TODAY)


def test_delete_room_of_past_booking_ok():
    unit, (r101, _r102) = _unit(rooms=2)
    _booking(unit, arrival=TODAY - timedelta(days=5), nights=2, room=r101)
    capacity.delete_room(r101, TODAY)
    assert not Room.objects.filter(pk=r101.pk).exists()
    unit.refresh_from_db()
    assert unit.quantity == 1


def test_delete_unassigned_room_below_sold_refused():
    unit, (_r101, r102) = _unit(rooms=2)
    _booking(unit, rooms=2)  # продано 2, комнаты не назначены
    with pytest.raises(capacity.CapacityBelowSold):
        capacity.delete_room(r102, TODAY)
    unit.refresh_from_db()
    assert unit.quantity == 2 and Room.objects.filter(pk=r102.pk).exists()


def test_delete_room_locks_unit_then_room():
    unit, (r101, _r102) = _unit(rooms=2)
    with CaptureQueriesContext(connection) as ctx:
        capacity.delete_room(r101, TODAY)
    locks = [q["sql"] for q in ctx if "FOR UPDATE" in q["sql"]]
    assert "stays_stayunit" in locks[0] and "stays_room" in locks[1]


# --- create_block (сервис) ----------------------------------------------------------


def test_category_block_on_sold_out_night_refused():
    unit, _ = _unit(quantity=1)
    _booking(unit)
    with pytest.raises(services.NoCapacity):
        services.create_block(unit, D0, D0, "Wartung")
    assert not UnitBlock.objects.exists()
    services.create_block(unit, D0 + timedelta(days=5), D0 + timedelta(days=5), "Wartung")
    assert UnitBlock.objects.count() == 1


def test_category_block_counts_existing_blocks():
    unit, _ = _unit(quantity=2)
    _booking(unit, nights=1)
    services.create_block(unit, D0, D0, "a")
    with pytest.raises(services.NoCapacity):
        services.create_block(unit, D0, D0, "b")


def test_room_block_on_room_assigned_as_extra_room_conflicts():
    unit, (r101, r102, _r103) = _unit(rooms=3)
    b = _booking(unit, rooms=2, room=r101)
    b.extra_rooms.add(r102)
    with pytest.raises(services.RoomConflict):
        services.create_block(unit, D0, D0, "Reparatur", room=r102)


# --- кабинет ------------------------------------------------------------------------


def _user():
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": Membership.ROLE_OWNER})
    return user


def _post(data):
    request = RequestFactory().post("/dashboard/stays/units/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    views.units(request)
    return [str(m) for m in get_messages(request)]


def test_unit_settings_quantity_below_sold_keeps_other_fields():
    unit, _ = _unit(quantity=3)
    _booking(unit, rooms=2)
    msgs = _post(
        {
            "action": "unit_settings",
            "unit": str(unit.pk),
            "description": "Neu beschrieben",
            "quantity": "1",
            "price_eur": "90",
            "min_nights": "1",
            "max_guests": "2",
        }
    )
    unit.refresh_from_db()
    assert unit.quantity == 3 and unit.description == "Neu beschrieben"
    assert any("weniger geht nicht" in m and "2" in m for m in msgs)


def test_unit_settings_without_quantity_field_keeps_quantity():
    """W0: форма без поля quantity не сбрасывает ёмкость в 1."""
    unit, _ = _unit(quantity=4)
    _post({"action": "unit_settings", "unit": str(unit.pk), "description": "x"})
    unit.refresh_from_db()
    assert unit.quantity == 4


def test_room_delete_view_refuses_assigned_room():
    unit, (r101, _r102) = _unit(rooms=2)
    b = _booking(unit, room=r101)
    msgs = _post({"action": "room_delete", "room": str(r101.pk)})
    assert Room.objects.filter(pk=r101.pk).exists()
    assert any(b.reference_code in m for m in msgs)


def test_room_delete_view_garbage_pk_is_404_not_500():
    from django.http import Http404

    with pytest.raises(Http404):
        _post({"action": "room_delete", "room": "1 OR 1"})


def test_units_block_action_on_sold_out_night_refused():
    unit, _ = _unit(quantity=1)
    _booking(unit)
    msgs = _post(
        {
            "action": "block",
            "unit": str(unit.pk),
            "start_date": D0.isoformat(),
            "end_date": D0.isoformat(),
        }
    )
    assert not UnitBlock.objects.exists()
    assert any("Überbuchung" in m for m in msgs)
