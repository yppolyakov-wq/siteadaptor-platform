"""KA-H8 (аудит KA-5e): билеты и события — деньги и данные.

E1 отмена события отменяет билеты · E2 отмена билета сторнирует выручку, маржа тура
без отменённых · E3 выручка = к оплате по снимку ставки · E4 ручной билет с Waiver
без 500 · E5 check-in неоплаченного только через FSM · E6 ручное «bezahlt» закрывает
рассрочку."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import views
from apps.events.models import Event, InstallmentCharge, InstallmentPlan, Ticket
from apps.events.services import book_ticket, cancel_event_tickets_now
from apps.events.state_machine import EventSM, TicketSM
from apps.finance.models import RevenueEntry

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=7),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 10000,
        "capacity": 10,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _ticket(event, **kw):
    return book_ticket(event, name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de", **kw)


def _req(data=None, method="post"):
    rf = RequestFactory()
    request = rf.post("/x/", data or {}) if method == "post" else rf.get("/x/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    return request


def _entry(ticket, suffix=""):
    return RevenueEntry.objects.filter(source="event", source_ref=f"{ticket.id}{suffix}").first()


# --- E3: выручка ------------------------------------------------------------------------


def test_revenue_uses_payable_after_voucher():
    ticket = _ticket(_event())
    Ticket.objects.filter(pk=ticket.pk).update(discount_cents=3000)
    ticket.refresh_from_db()
    TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    assert _entry(ticket).amount == Decimal("70.00")


def test_revenue_uses_ticket_vat_snapshot():
    ticket = _ticket(_event())
    Ticket.objects.filter(pk=ticket.pk).update(vat_rate=Decimal("7.00"))
    ticket.refresh_from_db()
    TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    assert _entry(ticket).vat_rate == Decimal("7.00")


def test_revenue_small_business_zero_rate():
    ticket = _ticket(_event())
    with mock.patch(
        "apps.booking.revenue._tenant", return_value=SimpleNamespace(small_business=True)
    ):
        TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    assert _entry(ticket).vat_rate == Decimal("0")


# --- E2: сторно --------------------------------------------------------------------------


def test_cancel_confirmed_ticket_reverses_revenue_with_rate():
    ticket = _ticket(_event())
    Ticket.objects.filter(pk=ticket.pk).update(vat_rate=Decimal("7.00"))
    ticket.refresh_from_db()
    ticket = TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    reversal = _entry(ticket, ":reversal")
    assert reversal.amount == Decimal("-100.00") and reversal.vat_rate == Decimal("7.00")


def test_cancel_pending_writes_no_reversal():
    ticket = _ticket(_event())
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    assert not RevenueEntry.objects.filter(source="event").exists()


def test_reversal_once_builtin_and_custom_path():
    from apps.core import status_effects

    ticket = _ticket(_event())
    ticket = TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    ticket = TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    status_effects.record_reversal_for("ticket", ticket)
    assert RevenueEntry.objects.filter(source="event", amount__lt=0).count() == 1


def test_tour_margin_excludes_cancelled_tickets():
    from apps.events.tour_finance import _ticket_refs

    event = _event()
    keep = _ticket(event)
    gone = _ticket(event)
    TicketSM().apply(gone, Ticket.STATUS_CANCELLED)
    refs = _ticket_refs(event)
    assert str(keep.pk) in refs and str(gone.pk) not in refs


# --- E1: отмена события ------------------------------------------------------------------


def test_cancel_event_cancels_active_tickets_not_attended():
    event = _event()
    pending = _ticket(event)
    confirmed = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    attended = TicketSM().apply(
        TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED), Ticket.STATUS_ATTENDED
    )
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    event.refresh_from_db()
    summary = cancel_event_tickets_now(event, tenant=SimpleNamespace(owner_email=""))
    assert summary["cancelled"] == 2
    statuses = dict(Ticket.objects.values_list("pk", "status"))
    assert statuses[pending.pk] == statuses[confirmed.pk] == Ticket.STATUS_CANCELLED
    assert statuses[attended.pk] == Ticket.STATUS_ATTENDED


def test_cancel_event_idempotent_second_run_noop():
    event = _event()
    TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    event.refresh_from_db()
    cancel_event_tickets_now(event, tenant=SimpleNamespace(owner_email=""))
    again = cancel_event_tickets_now(event, tenant=SimpleNamespace(owner_email=""))
    assert again["cancelled"] == 0


def test_cancel_event_customer_email_says_cancelled():
    from apps.notifications.models import Notification

    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    event.refresh_from_db()
    cancel_event_tickets_now(event, tenant=SimpleNamespace(owner_email=""))
    note = (
        Notification.objects.filter(dedupe_key__contains=str(ticket.id))
        .filter(dedupe_key__contains="cancelled")
        .first()
    )
    assert note is not None and "abgesagt" in note.payload["body"]


def test_cancel_event_owner_summary_lists_manual_installment():
    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    Ticket.objects.filter(pk=ticket.pk).update(payment_state=Ticket.PAYMENT_PAID)
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    event.refresh_from_db()
    with mock.patch("apps.notifications.services.notify") as notify:
        summary = cancel_event_tickets_now(
            event, tenant=SimpleNamespace(owner_email="o@t.de", stripe_connect_id="")
        )
    assert ticket.reference_code in summary["manual"]
    assert ticket.reference_code in notify.call_args.kwargs["body"]


def test_event_sm_cancel_enqueues_fanout_on_commit(django_capture_on_commit_callbacks):
    event = _event()
    with (
        mock.patch("apps.events.tasks.cancel_event_tickets.delay") as delay,
        mock.patch("apps.aggregator.tasks.sync_aggregator_event.delay"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        EventSM().apply(event, Event.STATUS_CANCELLED)
    assert delay.call_args.kwargs["event_id"] == str(event.id)


def test_post_event_mail_skips_cancelled_event():
    from apps.events.tasks import send_due_post_event

    event = _event(starts_at=timezone.now() - timedelta(days=3))
    TicketSM().apply(_ticket_any(event), Ticket.STATUS_CONFIRMED)
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    assert send_due_post_event() == 0


def _ticket_any(event):
    """Билет в прошлом/неопубликованном событии — в обход проверок продажи."""
    from apps.promotions.models import Customer

    return Ticket.objects.create(
        event=event,
        customer=Customer.objects.create(name="G", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"E-{uuid.uuid4().hex[:6].upper()}",
        price_cents=1000,
    )


def test_beat_skips_charges_of_cancelled_ticket():
    from apps.events.payments import charge_due_installments

    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    plan = InstallmentPlan.objects.create(
        ticket=ticket, stripe_customer_id="cus_1", stripe_payment_method_id="pm_1"
    )
    InstallmentCharge.objects.create(
        plan=plan, amount_cents=1000, due_date=timezone.localdate(), sequence=2
    )
    Ticket.objects.filter(pk=ticket.pk).update(status=Ticket.STATUS_CANCELLED)
    with mock.patch("apps.billing.connect.charge_off_session") as charge:
        charge_due_installments(connect_id="acct_1")
    charge.assert_not_called()


# --- E4/E5/E6 ----------------------------------------------------------------------------


def test_manual_ticket_waiver_event_shows_error_not_500():
    event = _event(waiver_required=True)
    resp = views.ticket_add(_req({"name": "Gast"}), pk=event.pk)
    assert resp.status_code == 302
    assert not Ticket.objects.filter(event=event).exists()


def test_checkin_pending_without_confirm_does_not_attend():
    ticket = _ticket(_event())
    views.checkin(_req(), code=ticket.reference_code)
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_PENDING and ticket.checked_in_at is None


def test_checkin_pending_with_confirm_goes_through_fsm():
    ticket = _ticket(_event())
    views.checkin(_req({"confirm_first": "1"}), code=ticket.reference_code)
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_ATTENDED and ticket.checked_in_at is not None
    assert _entry(ticket) is not None  # подтверждение через FSM → выручка


def test_checkin_cancelled_event_refused():
    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    Event.objects.filter(pk=event.pk).update(status=Event.STATUS_CANCELLED)
    views.checkin(_req(), code=ticket.reference_code)
    ticket.refresh_from_db()
    assert ticket.checked_in_at is None


def test_mark_paid_settles_installment_plan():
    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    plan = InstallmentPlan.objects.create(ticket=ticket)
    InstallmentCharge.objects.create(
        plan=plan, amount_cents=1000, due_date=timezone.localdate() + timedelta(days=30), sequence=2
    )
    views.ticket_action(_req({"target": "paid"}), pk=event.pk, tid=ticket.pk)
    plan.refresh_from_db()
    assert plan.status == InstallmentPlan.STATUS_COMPLETED
    assert not plan.charges.filter(status=InstallmentCharge.STATUS_SCHEDULED).exists()


def test_mark_paid_refused_on_cancelled_ticket():
    event = _event()
    ticket = _ticket(event)
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    views.ticket_action(_req({"target": "paid"}), pk=event.pk, tid=ticket.pk)
    ticket.refresh_from_db()
    assert ticket.payment_state != Ticket.PAYMENT_PAID


# --- правки по ревью ---------------------------------------------------------------------


def test_event_cancel_requires_owner_and_confirmation(monkeypatch):
    from apps.core import roles

    event = _event()
    monkeypatch.setattr(roles, "is_owner", lambda user: False)
    views.event_action(_req({"target": "cancelled", "confirm_cancel": "1"}), pk=event.pk)
    event.refresh_from_db()
    assert event.status == Event.STATUS_PUBLISHED
    monkeypatch.setattr(roles, "is_owner", lambda user: True)
    views.event_action(_req({"target": "cancelled"}), pk=event.pk)  # без подтверждения
    event.refresh_from_db()
    assert event.status == Event.STATUS_PUBLISHED
    with (
        mock.patch("apps.events.tasks.cancel_event_tickets.delay"),
        mock.patch("apps.aggregator.tasks.sync_aggregator_event.delay"),
    ):
        views.event_action(_req({"target": "cancelled", "confirm_cancel": "1"}), pk=event.pk)
    event.refresh_from_db()
    assert event.status == Event.STATUS_CANCELLED


def test_paid_guest_cancel_keeps_retained_revenue():
    ticket = _ticket(_event())
    ticket = TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED, retained_cents=10000)
    assert _entry(ticket, ":reversal") is None  # всё удержано — сторно нет


def test_deposit_guest_cancel_reverses_only_rest():
    ticket = _ticket(_event())
    ticket = TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED, retained_cents=3000)
    assert _entry(ticket, ":reversal").amount == Decimal("-70.00")


def test_waitlist_not_notified_for_cancelled_event():
    from apps.events.services import notify_event_waitlist

    event = _event(status=Event.STATUS_CANCELLED)
    assert notify_event_waitlist(event) == 0


def test_mark_paid_refused_on_refunded_ticket():
    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    Ticket.objects.filter(pk=ticket.pk).update(payment_state=Ticket.PAYMENT_REFUNDED)
    views.ticket_action(_req({"target": "paid"}), pk=event.pk, tid=ticket.pk)
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_REFUNDED


def test_beat_skips_charge_settled_manually():
    from apps.events.installments import settle_manually
    from apps.events.payments import charge_due_installments

    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    plan = InstallmentPlan.objects.create(
        ticket=ticket, stripe_customer_id="cus_1", stripe_payment_method_id="pm_1"
    )
    InstallmentCharge.objects.create(
        plan=plan, amount_cents=1000, due_date=timezone.localdate(), sequence=2
    )
    settle_manually(plan)
    with mock.patch("apps.billing.connect.charge_off_session") as charge:
        charge_due_installments(connect_id="acct_1")
    charge.assert_not_called()


def test_beat_passes_idempotency_key():
    from apps.events.payments import charge_due_installments

    event = _event()
    ticket = TicketSM().apply(_ticket(event), Ticket.STATUS_CONFIRMED)
    plan = InstallmentPlan.objects.create(
        ticket=ticket, stripe_customer_id="cus_1", stripe_payment_method_id="pm_1"
    )
    c = InstallmentCharge.objects.create(
        plan=plan, amount_cents=1000, due_date=timezone.localdate(), sequence=2
    )
    with mock.patch("apps.billing.connect.charge_off_session", return_value="pi_1") as charge:
        charge_due_installments(connect_id="acct_1")
    assert charge.call_args.kwargs["idempotency_key"] == f"installment:{c.id}:0"
