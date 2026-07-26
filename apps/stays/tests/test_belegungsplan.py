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
