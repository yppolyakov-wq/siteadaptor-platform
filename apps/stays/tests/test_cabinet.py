"""Track E / E2: кабинет date-range-броней — календарь загрузки, действия по
FSM, перенос дат, ручная бронь, управление юнитами и блокировками."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import services, views
from apps.stays.models import StayBooking, StayUnit, UnitBlock
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/stays/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
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
    kwargs.setdefault("name", "Gast")
    return services.book_stay(
        unit,
        arrival=D0 + timedelta(days=arr_off),
        departure=D0 + timedelta(days=dep_off),
        **kwargs,
    )


# --- календарь --------------------------------------------------------------------


def test_calendar_renders_grid_and_booking():
    unit = _unit()
    booking = _book(unit, 1, 4)
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert unit.name in body
    assert booking.reference_code in body


# --- действия по FSM + перенос ----------------------------------------------------


def test_action_confirm_then_move_conflict_then_free():
    unit = _unit()
    first = _book(unit, 0, 3, email="x1@t.de")
    second = _book(unit, 5, 7, email="x2@t.de")

    resp = views.stay_action(_req("post", data={"action": "confirmed"}), pk=first.pk)
    assert resp.status_code == 302
    first.refresh_from_db()
    assert first.status == "confirmed"

    # перенос second на занятый диапазон first — даты не меняются
    views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
            },
        ),
        pk=second.pk,
    )
    second.refresh_from_db()
    assert second.arrival == D0 + timedelta(days=5)

    # перенос на свободный диапазон — ок
    views.stay_action(
        _req(
            "post",
            data={
                "action": "move",
                "arrival": (D0 + timedelta(days=10)).isoformat(),
                "departure": (D0 + timedelta(days=12)).isoformat(),
            },
        ),
        pk=second.pk,
    )
    second.refresh_from_db()
    assert second.arrival == D0 + timedelta(days=10)


# --- ручная бронь -----------------------------------------------------------------


def test_manual_create_is_confirmed():
    unit = _unit()
    resp = views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
                "name": "Telefon-Gast",
                "guests": "2",
            },
        )
    )
    assert resp.status_code == 302
    booking = StayBooking.objects.get(unit=unit)
    assert booking.status == "confirmed"
    assert booking.nights == 2
    assert booking.source_channel == "manual"


def test_manual_create_rejects_occupied():
    unit = _unit()
    _book(unit, 0, 3)
    views.stay_create(
        _req(
            "post",
            "/dashboard/stays/new/",
            {
                "unit": str(unit.pk),
                "arrival": D0.isoformat(),
                "departure": (D0 + timedelta(days=2)).isoformat(),
                "name": "Zweitgast",
            },
        )
    )
    assert StayBooking.objects.filter(unit=unit).count() == 1  # второй не создан


# --- юниты + блокировки -----------------------------------------------------------


def test_units_page_creates_unit_and_block():
    resp = views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "unit",
                "name": "Ferienwohnung Süd",
                "type": "apartment",
                "price_eur": "95,50",
                "quantity": "2",
                "min_nights": "3",
                "max_guests": "4",
                "deposit_eur": "50",
            },
        )
    )
    assert resp.status_code == 302
    unit = StayUnit.objects.get(name="Ferienwohnung Süd")
    assert unit.price_cents == 9550
    assert unit.quantity == 2 and unit.min_nights == 3 and unit.max_guests == 4
    assert unit.deposit_cents == 5000

    views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "block",
                "unit": str(unit.pk),
                "start_date": D0.isoformat(),
                "end_date": (D0 + timedelta(days=2)).isoformat(),
                "reason": "Renovierung",
            },
        )
    )
    block = UnitBlock.objects.get(unit=unit)
    assert block.reason == "Renovierung"

    body = views.units(_req(path="/dashboard/stays/units/")).content.decode()
    assert "Ferienwohnung Süd" in body and "Renovierung" in body


def test_unit_settings_saves_deposit():
    unit = _unit()
    views.units(
        _req(
            "post",
            "/dashboard/stays/units/",
            {
                "action": "unit_settings",
                "unit": str(unit.pk),
                "price_eur": "120",
                "quantity": "1",
                "min_nights": "2",
                "max_guests": "3",
                "deposit_eur": "30,00",
                "require_manual_confirm": "on",
            },
        )
    )
    unit.refresh_from_db()
    assert unit.price_cents == 12000 and unit.deposit_cents == 3000
    assert unit.min_nights == 2 and unit.require_manual_confirm is True


# --- P2.5b-аналог: отмена оплаченной возвращает депозит (E4 wires Stripe) ----------


def test_cancel_paid_stay_refunds(monkeypatch):
    unit = _unit(deposit_cents=5000)
    booking = _book(unit, 1, 4)
    StayBookingSM().apply(booking, "confirmed")
    booking.payment_state = StayBooking.PAYMENT_PAID
    booking.stripe_payment_intent = "pi_x"
    booking.save(update_fields=["payment_state", "stripe_payment_intent"])
    captured = {}
    monkeypatch.setattr(views.connect, "refund", lambda **kw: captured.update(kw))
    request = _req("post", data={"action": "cancelled"})
    request.tenant = TenantFactory.build(stripe_connect_id="acct_1")
    views.stay_action(request, pk=booking.pk)
    booking.refresh_from_db()
    assert booking.status == "cancelled"
    assert booking.payment_state == StayBooking.PAYMENT_REFUNDED
    assert captured == {"connect_id": "acct_1", "payment_intent": "pi_x"}


def test_invoice_action_creates_draft(monkeypatch):
    unit = _unit(price_cents=10700)
    booking = _book(unit, 1, 2, email="g@test.de")
    StayBookingSM().apply(booking, "confirmed")
    request = _req("post", data={"action": "invoice"})
    request.tenant = TenantFactory.build(small_business=False)
    monkeypatch.setattr(request.tenant, "is_module_active", lambda m: m == "finance")
    resp = views.stay_action(request, pk=booking.pk)
    assert resp.status_code == 302 and "/rechnungen/" in resp.url
    booking.refresh_from_db()
    assert booking.invoice_id is not None


def test_invoice_action_blocked_when_finance_off(monkeypatch):
    from apps.finance.models import Invoice

    unit = _unit()
    booking = _book(unit, 1, 2)
    StayBookingSM().apply(booking, "confirmed")
    request = _req("post", data={"action": "invoice"})
    request.tenant = TenantFactory.build()
    monkeypatch.setattr(request.tenant, "is_module_active", lambda m: False)
    views.stay_action(request, pk=booking.pk)
    assert not Invoice.objects.exists()


def test_reports_view_renders(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    unit = _unit(price_cents=10000, quantity=2)
    _book(unit, 1, 4)  # бронь в текущем окне (book_stay)
    resp = views.reports(_req(path="/dashboard/stays/reports/"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "RevPAR" in body and "%" in body
