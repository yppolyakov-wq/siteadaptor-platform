"""Батч C (Belegungsplan, концепт 2026-07-27): tape chart кабинета — плашки
броней/блокировок по дорожкам, drag-перенос (fetch, цена сохраняется), префил
walk-in по клетке, блокировка из формы, hard-delete ручной брони без денег."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import availability, services, views
from apps.stays.models import StayBooking, StayUnit, UnitBlock

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/stays/", data=None, fetch=False):
    headers = {"HTTP_X_REQUESTED_WITH": "fetch"} if fetch else {}
    request = getattr(RequestFactory(), method)(path, data or {}, **headers)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 8000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, arr_off, dep_off, **kwargs):
    kwargs.setdefault("name", "Gast Meier")
    return services.book_stay(
        unit,
        arrival=D0 + timedelta(days=arr_off),
        departure=D0 + timedelta(days=dep_off),
        **kwargs,
    )


# --- booking_bars: раскладка сегментов по дорожкам ---------------------------


def test_bars_single_booking_with_gaps():
    unit = _unit()
    b = _book(unit, 2, 5)  # ночи 2,3,4 → span 3
    bars = availability.booking_bars([unit], D0, 10, [b], [])
    lanes = bars[unit.id]
    assert len(lanes) == 1
    cells = lanes[0]
    assert cells[0] == {"gap": 2}
    seg = cells[1]
    assert seg["kind"] == "booking" and seg["span"] == 3 and seg["offset"] == 2
    assert not seg["clip_left"] and not seg["clip_right"]
    assert cells[2] == {"gap": 5}  # 10 − (2+3)


def test_bars_overlap_quantity_two_gets_two_lanes():
    unit = _unit(quantity=2)
    a = _book(unit, 1, 5)
    b = _book(unit, 3, 7)  # пересекается с a → вторая дорожка
    bars = availability.booking_bars([unit], D0, 10, [a, b], [])
    assert len(bars[unit.id]) == 2


def test_bars_back_to_back_share_lane():
    unit = _unit()
    a = _book(unit, 1, 3)
    b = _book(unit, 3, 5)  # выезд/заезд в один день — одна дорожка
    bars = availability.booking_bars([unit], D0, 10, [a, b], [])
    assert len(bars[unit.id]) == 1
    kinds = [c for c in bars[unit.id][0] if "kind" in c]
    assert len(kinds) == 2


def test_bars_clip_to_window_and_block_inclusive_end():
    unit = _unit()
    b = _book(unit, -2, 3)  # заезд до окна → clip_left
    blk = UnitBlock.objects.create(
        unit=unit, start_date=D0 + timedelta(days=8), end_date=D0 + timedelta(days=12)
    )  # конец включителен и за окном 10 → clip_right
    bars = availability.booking_bars([unit], D0, 10, [b], [blk])
    segs = [c for lane in bars[unit.id] for c in lane if "kind" in c]
    booking_seg = next(s for s in segs if s["kind"] == "booking")
    assert booking_seg["clip_left"] and booking_seg["offset"] == 0 and booking_seg["span"] == 3
    block_seg = next(s for s in segs if s["kind"] == "block")
    assert block_seg["offset"] == 8 and block_seg["span"] == 2 and block_seg["clip_right"]


# --- move_stay: целевой юнит + сохранение цены --------------------------------


def test_move_stay_to_other_unit_keeps_price():
    a, b = _unit(price_cents=8000), _unit(price_cents=20000)
    booking = _book(a, 1, 4)
    total_before = booking.total_cents
    services.move_stay(
        booking,
        arrival=booking.arrival,
        departure=booking.departure,
        unit=b,
        reprice=False,
    )
    booking.refresh_from_db()
    assert booking.unit_id == b.id
    assert booking.total_cents == total_before  # решение владельца: цена сохраняется


def test_move_stay_to_busy_unit_raises():
    a, b = _unit(), _unit()
    blocker = _book(b, 1, 4)  # noqa: F841 — занимает целевой юнит
    booking = _book(a, 1, 4)
    with pytest.raises(services.StayUnavailable):
        services.move_stay(booking, arrival=booking.arrival, departure=booking.departure, unit=b)


def test_move_stay_guest_overflow_raises():
    a, b = _unit(max_guests=4), _unit(max_guests=2)
    booking = _book(a, 1, 4, guests=4)
    with pytest.raises(services.MaxGuests):
        services.move_stay(booking, arrival=booking.arrival, departure=booking.departure, unit=b)


# --- stay_action: fetch-контракт drag'а ---------------------------------------


def test_stay_action_move_fetch_204_and_409():
    a, b = _unit(), _unit()
    booking = _book(a, 1, 4)
    total_before = booking.total_cents
    resp = views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=2)).isoformat(),
                "departure": (D0 + timedelta(days=5)).isoformat(),
                "unit": str(b.pk),
                "reprice": "0",
            },
            fetch=True,
        ),
        pk=booking.pk,
    )
    assert resp.status_code == 204
    booking.refresh_from_db()
    assert booking.unit_id == b.id and booking.arrival == D0 + timedelta(days=2)
    assert booking.total_cents == total_before

    blocker = _book(a, 10, 13)  # noqa: F841
    resp = views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=10)).isoformat(),
                "departure": (D0 + timedelta(days=13)).isoformat(),
                "unit": str(a.pk),
                "reprice": "0",
            },
            fetch=True,
        ),
        pk=booking.pk,
    )
    assert resp.status_code == 409  # snap-back на клиенте


# --- stay_create mode=block ----------------------------------------------------


def test_stay_create_block_mode_creates_unitblock():
    unit = _unit()
    resp = views.stay_create(
        _req(
            "post",
            data={
                "unit": str(unit.pk),
                "arrival": (D0 + timedelta(days=1)).isoformat(),
                "departure": (D0 + timedelta(days=4)).isoformat(),
                "name": "Renovierung",
                "mode": "block",
            },
        )
    )
    assert resp.status_code == 302
    blk = UnitBlock.objects.get(unit=unit)
    assert blk.start_date == D0 + timedelta(days=1)
    assert blk.end_date == D0 + timedelta(days=3)  # departure эксклюзивен → −1
    assert blk.reason == "Renovierung"
    assert not StayBooking.objects.exists()  # бронь НЕ создана


# --- hard-delete: только manual без денег ---------------------------------------


def test_delete_manual_unpaid_booking():
    unit = _unit()
    booking = _book(unit, 1, 4, source_channel="manual")
    resp = views.booking_delete(_req("post"), pk=booking.pk)
    assert resp.status_code == 302
    assert not StayBooking.objects.filter(pk=booking.pk).exists()


def test_delete_refused_for_paid_or_external():
    unit = _unit()
    paid = _book(unit, 1, 4, source_channel="manual")
    paid.payment_state = StayBooking.PAYMENT_PAID
    paid.save(update_fields=["payment_state"])
    views.booking_delete(_req("post"), pk=paid.pk)
    assert StayBooking.objects.filter(pk=paid.pk).exists()  # отказ

    ota = _book(unit, 5, 8, source_channel="booking_com")
    views.booking_delete(_req("post"), pk=ota.pk)
    assert StayBooking.objects.filter(pk=ota.pk).exists()  # отказ


# --- рендер календаря ------------------------------------------------------------


def test_calendar_renders_bar_with_name_code_and_drag():
    unit = _unit()
    booking = _book(unit, 1, 4)
    UnitBlock.objects.create(
        unit=unit,
        start_date=D0 + timedelta(days=6),
        end_date=D0 + timedelta(days=7),
        reason="Wartung",
    )
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert "Gast Meier" in body and booking.reference_code in body  # плашка с подписью
    assert 'draggable="true"' in body and f'data-bar-pk="{booking.pk}"' in body
    assert f"/dashboard/stays/buchung/{booking.pk}/" in body  # клик → FB-11
    assert "Wartung" in body  # блокировка плашкой
    assert 'data-free="1"' in body  # свободные клетки кликабельны (префил)
    # Багфикс 2026-07-27: drop принимает ВСЯ строка юнита — дорожки несут
    # data-unit, плашка несёт заезд (grab-offset: за какую ночь взяли, той и ложится).
    assert f'<tr data-unit="{unit.pk}">' in body
    assert f'data-arrival="{booking.arrival.isoformat()}"' in body


# --- Фидбэк 2026-07-27: правка брони + карточка под календарём -----------------


def test_stay_action_update_edits_dates_guests_note():
    unit = _unit(price_cents=10000, max_guests=4)
    booking = _book(unit, 1, 4)  # 3 ночи → 300 €
    total_before = booking.total_cents
    resp = views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": (D0 + timedelta(days=2)).isoformat(),
                "departure": (D0 + timedelta(days=6)).isoformat(),  # 4 ночи
                "unit": str(unit.pk),
                "adults": "2",
                "children": "1",
                "note": "Späte Anreise",
                "reprice": "1",
            },
        ),
        pk=booking.pk,
    )
    assert resp.status_code == 302 and f"buchung={booking.pk}" in resp.url
    booking.refresh_from_db()
    assert booking.arrival == D0 + timedelta(days=2) and booking.nights == 4
    assert booking.adults == 2 and booking.children == 1 and booking.guests == 3
    assert booking.note == "Späte Anreise"
    assert booking.total_cents == 40000 != total_before  # перерасчёт

    # Без reprice цена сохраняется (правка только заметки/гостей).
    views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": booking.arrival.isoformat(),
                "departure": booking.departure.isoformat(),
                "adults": "1",
                "children": "0",
                "note": "",
            },
        ),
        pk=booking.pk,
    )
    booking.refresh_from_db()
    assert booking.total_cents == 40000 and booking.guests == 1


def test_stay_action_update_guest_overflow_rejected():
    unit = _unit(max_guests=2)
    booking = _book(unit, 1, 3)
    views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": booking.arrival.isoformat(),
                "departure": booking.departure.isoformat(),
                "adults": "3",
                "children": "1",
            },
        ),
        pk=booking.pk,
    )
    booking.refresh_from_db()
    assert booking.guests == 1  # отказ, ничего не изменилось


def test_calendar_booking_panel_and_fragment():
    unit = _unit()
    booking = _book(unit, 1, 4)
    body = views.calendar(
        _req(data={"von": D0.isoformat(), "buchung": str(booking.pk)})
    ).content.decode()
    assert 'id="booking-panel"' in body and booking.reference_code in body
    assert 'value="update"' in body  # форма «Buchung bearbeiten» в панели

    frag = views.calendar(
        _req(data={"von": D0.isoformat(), "buchung": str(booking.pk), "box": "1"})
    ).content.decode()
    assert booking.reference_code in frag and 'value="update"' in frag
    assert 'id="belegungsplan"' not in frag  # ТОЛЬКО фрагмент карточки

    # мусорный pk — страница живёт, панель скрыта
    body = views.calendar(_req(data={"von": D0.isoformat(), "buchung": "junk"})).content.decode()
    assert 'id="booking-panel"' in body


def test_booking_detail_page_has_edit_form():
    unit = _unit()
    booking = _book(unit, 1, 4)
    body = views.booking_detail(_req(), pk=booking.pk).content.decode()
    assert 'value="update"' in body and "Buchung bearbeiten" in body


# --- PMS-R1: физические номера (Zimmer) поверх quantity -------------------------


def test_room_add_delete_syncs_quantity():
    from apps.stays.models import Room

    unit = _unit(quantity=3)
    views.units(_req("post", data={"action": "room_add", "unit": str(unit.pk), "number": "101"}))
    views.units(_req("post", data={"action": "room_add", "unit": str(unit.pk), "number": "102"}))
    unit.refresh_from_db()
    assert unit.rooms.count() == 2 and unit.quantity == 2  # ёмкость = число комнат

    # дубль номера не плодится (get_or_create)
    views.units(_req("post", data={"action": "room_add", "unit": str(unit.pk), "number": "101"}))
    assert unit.rooms.count() == 2

    room = Room.objects.get(unit=unit, number="101")
    views.units(_req("post", data={"action": "room_delete", "room": str(room.pk)}))
    unit.refresh_from_db()
    assert unit.quantity == 1


def test_unit_settings_quantity_readonly_with_rooms():
    from apps.stays.models import Room

    unit = _unit(quantity=1)
    Room.objects.create(unit=unit, number="201")
    Room.objects.create(unit=unit, number="202")
    views.units(
        _req(
            "post",
            data={
                "action": "unit_settings",
                "unit": str(unit.pk),
                "name": unit.name,
                "description": "",
                "price_eur": "80",
                "quantity": "9",  # ручной ввод игнорируется
                "min_nights": "1",
                "max_guests": "2",
            },
        )
    )
    unit.refresh_from_db()
    assert unit.quantity == 2  # ёмкость = активные комнаты, не POST


def test_units_without_rooms_keep_manual_quantity():
    unit = _unit(quantity=1)
    views.units(
        _req(
            "post",
            data={
                "action": "unit_settings",
                "unit": str(unit.pk),
                "name": unit.name,
                "description": "",
                "price_eur": "80",
                "quantity": "5",
                "min_nights": "1",
                "max_guests": "2",
            },
        )
    )
    unit.refresh_from_db()
    assert unit.quantity == 5  # ленивая активация: без комнат — как раньше


# --- PMS-R2: назначение физического номера --------------------------------------


def test_assign_room_and_conflict():
    from apps.stays.models import Room

    unit = _unit(quantity=2)
    r101 = Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    a = _book(unit, 1, 4)
    b = _book(unit, 2, 5)  # пересекается с a
    services.assign_room(a, r101)
    a.refresh_from_db()
    assert a.room_id == r101.id
    with pytest.raises(services.RoomConflict):
        services.assign_room(b, r101)  # занята пересекающейся бронью
    assert [r.number for r in services.free_rooms_for(b)] == ["102"]
    services.assign_room(a, None)  # снять
    a.refresh_from_db()
    assert a.room_id is None


def test_update_action_assigns_room_and_unit_change_clears_it():
    from apps.stays.models import Room

    unit = _unit(quantity=1)
    other = _unit()
    room = Room.objects.create(unit=unit, number="301")
    booking = _book(unit, 1, 4)
    views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": booking.arrival.isoformat(),
                "departure": booking.departure.isoformat(),
                "unit": str(unit.pk),
                "adults": "1",
                "children": "0",
                "room": str(room.pk),
            },
        ),
        pk=booking.pk,
    )
    booking.refresh_from_db()
    assert booking.room_id == room.id
    # смена категории → комната сброшена (принадлежит старой)
    views.stay_action(
        _req(
            "post",
            data={
                "action": "update",
                "arrival": booking.arrival.isoformat(),
                "departure": booking.departure.isoformat(),
                "unit": str(other.pk),
                "adults": "1",
                "children": "0",
                "room": str(room.pk),  # устаревший селект — игнор
                "reprice": "1",
            },
        ),
        pk=booking.pk,
    )
    booking.refresh_from_db()
    assert booking.unit_id == other.id and booking.room_id is None


def test_calendar_shows_ohne_zimmer_chip_and_room_on_bar():
    from apps.stays.models import Room

    unit = _unit(quantity=2)
    r = Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    with_room = _book(unit, 1, 4)
    services.assign_room(with_room, r)
    _book(unit, 2, 5)  # без номера
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert "without an assigned room" in body  # чип «ohne Zimmer»
    assert "🚪101" in body  # номер на плашке


# --- PMS-R3: шахматка построчно по комнатам + drop-назначение --------------------


def test_room_lane_rows_layout():
    from apps.stays.models import Room

    unit = _unit(quantity=2)
    r101 = Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    assigned = _book(unit, 1, 4)
    services.assign_room(assigned, r101)
    unassigned = _book(unit, 2, 5)  # noqa: F841 — без номера
    rows_out = availability.room_lane_rows(
        unit, list(unit.rooms.all()), D0, 10, list(StayBooking.objects.all()), []
    )
    labels = [r["label"] for r in rows_out]
    assert labels[0] == "101" and labels[1] == "102"  # строка на каждую комнату
    assert "" in labels  # безымянная дорожка «ohne Zimmer»
    r101_row = rows_out[0]
    assert any(c.get("kind") == "booking" for c in r101_row["cells"])  # бронь на своей строке
    r102_row = rows_out[1]
    assert r102_row["cells"] == [{"gap": 10}]  # пустая комната — пустая строка


def test_calendar_renders_room_rows_with_drop_targets():
    from apps.stays.models import Room

    unit = _unit(quantity=1)
    room = Room.objects.create(unit=unit, number="101")
    _book(unit, 1, 4)  # без номера → безымянная дорожка + чип
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert f'data-room="{room.id}"' in body  # строка комнаты — drop-цель
    assert "🚪101" in body  # подпись строки


def test_move_with_room_assigns_and_conflict_409():
    from apps.stays.models import Room

    unit = _unit(quantity=2)
    r101 = Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    a = _book(unit, 1, 4)
    b = _book(unit, 10, 13)
    services.assign_room(a, r101)
    # drop b на строку 101 в свободные даты → назначение
    resp = views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=10)).isoformat(),
                "departure": (D0 + timedelta(days=13)).isoformat(),
                "unit": str(unit.pk),
                "room": str(r101.pk),
                "reprice": "0",
            },
            fetch=True,
        ),
        pk=b.pk,
    )
    assert resp.status_code == 204
    b.refresh_from_db()
    assert b.room_id == r101.id
    # drop b на 101 в даты, пересекающиеся с a → 409 ДО переноса (даты целы)
    resp = views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=2)).isoformat(),
                "departure": (D0 + timedelta(days=5)).isoformat(),
                "unit": str(unit.pk),
                "room": str(r101.pk),
                "reprice": "0",
            },
            fetch=True,
        ),
        pk=b.pk,
    )
    assert resp.status_code == 409
    b.refresh_from_db()
    assert b.arrival == D0 + timedelta(days=10)  # перенос НЕ состоялся


# --- PMS-R4: хаускипинг-lite ------------------------------------------------------


def test_checkout_marks_room_dirty_and_clean_action():
    from apps.stays.models import Room
    from apps.stays.state_machine import StayBookingSM

    unit = _unit(quantity=1)
    room = Room.objects.create(unit=unit, number="101")
    booking = _book(unit, -3, -1)  # прошедшее проживание
    services.assign_room(booking, room)
    StayBookingSM().apply(booking, "confirmed")
    StayBookingSM().apply(booking, "fulfilled")  # выезд
    room.refresh_from_db()
    assert room.housekeeping == Room.HK_DIRTY  # выезд пометил к уборке

    body = views.calendar(_req(data={"von": (D0 - timedelta(days=5)).isoformat()})).content.decode()
    assert "🧹" in body and "Housekeeping" in body  # бейдж + панель уборки

    resp = views.room_clean(_req("post"), pk=room.pk)
    assert resp.status_code == 302
    room.refresh_from_db()
    assert room.housekeeping == Room.HK_CLEAN
