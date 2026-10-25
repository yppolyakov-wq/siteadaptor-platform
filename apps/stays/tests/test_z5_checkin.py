"""KA-12 Zimmer Z-5d (О-7): Check-in / Check-out — отметки стойки, не статус FSM.

Замки: заселение только подтверждённой брони в дни проживания, повтор без второго
штампа; выезд = штатный «fulfilled» (выручка, комната → dirty) + отметка, ранний
выезд запрещён; «Abgereist» старой кнопкой и свой статус выезда ставят отметку,
автоматика — нет; заселённый гость — не неявка (все поверхности) и его даты не
переносятся в будущее; сбой журнала не откатывает отметку."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import transactions as core_transactions
from apps.core.fsm import GuestCheckedIn
from apps.core.models import Membership
from apps.finance.models import RevenueEntry
from apps.stays import front_desk, services, tasks, views
from apps.stays.models import Room, StayBooking, StayUnit
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _booking(arr=0, dep=2, *, confirm=True, room=True):
    unit = StayUnit.objects.create(name=f"DZ {uuid.uuid4().hex[:6]}", price_cents=10000)
    b = services.book_stay(
        unit,
        arrival=TODAY + timedelta(days=arr),
        departure=TODAY + timedelta(days=dep),
        name="Gast Stoik",
    )
    if room:
        r = Room.objects.create(unit=unit, number="101")
        services.sync_room_quantity(unit)
        services.assign_room(b, r)
    if confirm:
        StayBookingSM().apply(b, "confirmed")
    return b


# --- check_in -------------------------------------------------------------------------


def test_check_in_on_arrival_day_and_repeat_is_refused():
    b = _booking()
    front_desk.check_in(b)
    b.refresh_from_db()
    stamp = b.checked_in_at
    assert stamp is not None
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.check_in(b)
    b.refresh_from_db()
    assert b.checked_in_at == stamp


def test_check_in_with_stale_instance_does_not_restamp():
    b = _booking()
    stale = StayBooking.objects.get(pk=b.pk)
    front_desk.check_in(b)
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.check_in(stale)


def test_check_in_pending_refused():
    b = _booking(confirm=False)
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.check_in(b)


def test_check_in_before_arrival_refused():
    b = _booking(arr=1, dep=3)
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.check_in(b)


def test_check_in_custom_active_status_allowed():
    tenant = TenantFactory.build(
        site_config={
            "status_defs": {
                "stay": [{"code": "anzahlung", "role": "active", "blocks_capacity": True}]
            }
        }
    )
    b = _booking()
    StayBooking.objects.filter(pk=b.pk).update(status="anzahlung")
    b.refresh_from_db()
    front_desk.check_in(b, tenant=tenant)
    b.refresh_from_db()
    assert b.checked_in_at is not None


def test_undo_check_in_and_not_after_fulfilled():
    b = _booking(arr=-2, dep=0)
    StayBooking.objects.filter(pk=b.pk).update(checked_in_at=timezone.now())
    b.refresh_from_db()
    front_desk.undo_check_in(b)
    b.refresh_from_db()
    assert b.checked_in_at is None
    StayBooking.objects.filter(pk=b.pk).update(checked_in_at=timezone.now())
    b.refresh_from_db()
    front_desk.check_out(b)
    b.refresh_from_db()
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.undo_check_in(b)


def test_audit_db_failure_keeps_stamp(monkeypatch):
    """Падение INSERT журнала (DatabaseError) глушится audit_event в своём savepoint —
    отметка остаётся, транзакция не помечена needs_rollback."""
    from django.db import DatabaseError

    from apps.audit.models import AuditEvent

    def boom(*a, **kw):
        raise DatabaseError("audit table down")

    monkeypatch.setattr(AuditEvent.objects, "create", boom)
    b = _booking()
    front_desk.check_in(b)
    b.refresh_from_db()
    assert b.checked_in_at is not None


# --- check_out ------------------------------------------------------------------------


def test_check_out_on_departure_day_books_revenue_and_dirty_room():
    b = _booking(arr=-2, dep=0)
    front_desk.check_out(b)
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_FULFILLED and b.checked_out_at is not None
    assert RevenueEntry.objects.filter(source="stay", source_ref=str(b.pk)).exists()
    assert Room.objects.get(pk=b.room_id).housekeeping == Room.HK_DIRTY


def test_double_check_out_books_revenue_once():
    b = _booking(arr=-2, dep=0)
    front_desk.check_out(b)
    stale = StayBooking.objects.get(pk=b.pk)
    front_desk.check_out(stale)  # идемпотентно (src == dst)
    assert RevenueEntry.objects.filter(source="stay", source_ref=str(b.pk)).count() == 1


def test_early_check_out_refused():
    b = _booking(arr=-1, dep=2)
    with pytest.raises(front_desk.FrontDeskError):
        front_desk.check_out(b)
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_CONFIRMED


def test_old_abgereist_button_stamps_too():
    b = _booking(arr=-2, dep=0)
    core_transactions.apply_action("stay", b, "fulfilled")
    b.refresh_from_db()
    assert b.checked_out_at is not None


def test_auto_fulfil_does_not_stamp():
    b = _booking(arr=-3, dep=-1)
    tasks.auto_fulfil_departed()
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_FULFILLED and b.checked_out_at is None


def test_custom_done_status_stamps():
    from apps.core import status_effects
    from apps.core.status_registry import StatusDescriptor

    b = _booking(arr=-2, dep=0)
    status_effects.apply_custom_effects(
        "stay",
        b,
        StatusDescriptor("confirmed", "active", "in_progress"),
        StatusDescriptor("abgereist", "done", "done", builtin=False),
    )
    b.refresh_from_db()
    assert b.checked_out_at is not None


def test_failing_settle_rolls_back_status_and_stamp(monkeypatch):
    from apps.core import money_contract

    def boom(*a, **kw):
        raise RuntimeError("settle down")

    monkeypatch.setattr(money_contract, "settle_on_delivery", boom)
    b = _booking(arr=-2, dep=0)
    with pytest.raises(RuntimeError):
        front_desk.check_out(b)
    b = StayBooking.objects.get(pk=b.pk)
    assert b.status == StayBooking.STATUS_CONFIRMED and b.checked_out_at is None


# --- гарды ----------------------------------------------------------------------------


def test_no_show_of_checked_in_guest_refused_everywhere():
    b = _booking()
    front_desk.check_in(b)
    b.refresh_from_db()
    with pytest.raises(GuestCheckedIn):
        core_transactions.apply_action("stay", b, "no_show")
    with pytest.raises(GuestCheckedIn):
        StayBookingSM().apply(b, "no_show")
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_CONFIRMED


def test_cancel_of_checked_in_guest_allowed():
    b = _booking()
    front_desk.check_in(b)
    b.refresh_from_db()
    core_transactions.apply_action("stay", b, "cancelled")
    b.refresh_from_db()
    assert b.status == StayBooking.STATUS_CANCELLED


def test_move_of_checked_in_guest_to_future_refused():
    b = _booking(arr=0, dep=2)
    front_desk.check_in(b)
    b.refresh_from_db()
    with pytest.raises(services.GuestCheckedInMove):
        services.move_stay(
            b, arrival=TODAY + timedelta(days=1), departure=TODAY + timedelta(days=3)
        )
    services.move_stay(b, arrival=TODAY, departure=TODAY + timedelta(days=4))  # продление — ок
    b.refresh_from_db()
    assert b.departure == TODAY + timedelta(days=4)


# --- вьюха ----------------------------------------------------------------------------


def _user(role=Membership.ROLE_OWNER, *, perms=None):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": role, "permissions": perms or {}})
    return user


def _act(b, action, user=None, **extra):
    request = RequestFactory().post(
        f"/dashboard/stays/{b.pk}/action/", {"action": action, "next": "/dashboard/x/", **extra}
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    response = views.stay_action(request, b.pk)
    return response, [str(m) for m in get_messages(request)]


def test_view_check_in_and_out_by_staff():
    b = _booking(arr=0, dep=1)
    response, _ = _act(b, "check_in", _user(Membership.ROLE_STAFF))
    assert response["Location"] == "/dashboard/x/"
    b.refresh_from_db()
    assert b.checked_in_at is not None


def test_view_without_rezeption_right_refused():
    b = _booking()
    user = _user(Membership.ROLE_STAFF, perms={"remove": ["rezeption.edit"]})
    _response, msgs = _act(b, "check_in", user)
    b.refresh_from_db()
    assert b.checked_in_at is None and msgs


def test_view_no_show_of_checked_in_has_clear_message():
    b = _booking()
    front_desk.check_in(b)
    _response, msgs = _act(b, "no_show")
    assert any("eingecheckt" in m for m in msgs)


def test_view_update_dates_of_checked_in_refused():
    b = _booking(arr=0, dep=2)
    front_desk.check_in(b)
    _act(
        b,
        "update",
        arrival=(TODAY + timedelta(days=1)).isoformat(),
        departure=(TODAY + timedelta(days=3)).isoformat(),
        adults="1",
    )
    b.refresh_from_db()
    assert b.arrival == TODAY


def test_booking_detail_shows_front_desk_block():
    b = _booking()
    request = RequestFactory().get(f"/dashboard/stays/buchung/{b.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = views.booking_detail(request, b.pk).content.decode()
    assert 'value="check_in"' in body and "data-front-desk" in body
