"""R10b: первый платёж рассрочки + захват мандата (вебхук создаёт план).

Stripe замокан. Проверяем `installments.create_plan` (график, 1-я доля paid,
payment_state) и идемпотентность вебхук-обработчика `create_installment_plan`.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.events import installments
from apps.events.models import Event, InstallmentPlan, Ticket
from apps.events.services import book_ticket

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Teures Retreat",
        "starts_at": timezone.now() + timedelta(days=90),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 150000,
        "allow_installments": True,
        "installment_mode": Event.INSTALLMENT_FIXED,
        "installment_count": 3,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_create_plan_marks_first_charge_paid():
    event = _event()
    ticket = book_ticket(event, name="A", email="a@test.de")
    plan = installments.create_plan(
        ticket, payment_intent="pi_1", customer_id="cus_1", payment_method_id="pm_1"
    )
    charges = list(plan.charges.all())
    assert len(charges) == 3
    assert charges[0].status == "paid" and charges[0].stripe_payment_intent == "pi_1"
    assert all(c.status == "scheduled" for c in charges[1:])
    assert sum(c.amount_cents for c in charges) == ticket.payable_cents
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_INSTALLMENT
    assert plan.stripe_payment_method_id == "pm_1"
    assert plan.paid_cents == charges[0].amount_cents


def test_create_plan_idempotent():
    event = _event()
    ticket = book_ticket(event, name="B", email="b@test.de")
    p1 = installments.create_plan(ticket, payment_intent="pi_1")
    p2 = installments.create_plan(ticket, payment_intent="pi_1")
    assert p1.pk == p2.pk
    assert InstallmentPlan.objects.filter(ticket=ticket).count() == 1


def test_webhook_create_installment_plan():
    """create_installment_plan (вебхук): достаёт мандат из PI и строит план."""
    from django.db import connection

    from apps.events import payments

    event = _event()
    ticket = book_ticket(event, name="C", email="c@test.de")
    fake_tenant = mock.Mock(stripe_connect_id="acct_9")

    with (
        mock.patch.object(
            payments.connect, "mandate_from_payment_intent", return_value=("cus_9", "pm_9")
        ) as m,
        mock.patch("apps.tenants.models.Tenant.objects") as objs,
    ):
        objs.filter.return_value.first.return_value = fake_tenant
        ok = payments.create_installment_plan(
            tenant_schema=connection.schema_name,
            ticket_id=str(ticket.id),
            payment_intent="pi_x",
        )
    assert ok is True
    m.assert_called_once()
    plan = InstallmentPlan.objects.get(ticket=ticket)
    assert plan.stripe_customer_id == "cus_9" and plan.stripe_payment_method_id == "pm_9"
    assert plan.charges.filter(status="paid").count() == 1


def test_first_installment_cents_gating():
    event = _event(installment_min_cents=200000)
    # сумма ниже минимума → 0 (рассрочка не предлагается)
    assert installments.first_installment_cents(event, 150000) == 0
    event2 = _event()
    assert installments.first_installment_cents(event2, 150000) == 50000  # 150000/3


# --- R10c: off-session списания --------------------------------------------


def _plan_with_due(today):
    event = _event()
    ticket = book_ticket(event, name="P", email="p@test.de")
    plan = installments.create_plan(
        ticket, payment_intent="pi_1", customer_id="cus_1", payment_method_id="pm_1"
    )
    # сдвинуть наступившие доли на «сегодня» (по умолчанию fixed помесячно в будущем)
    plan.charges.filter(sequence__gt=1).update(due_date=today)
    return plan


def test_charge_due_pays_scheduled_charges():
    from apps.events import payments

    today = timezone.localdate()
    plan = _plan_with_due(today)
    with mock.patch.object(payments.connect, "charge_off_session", return_value="pi_off") as m:
        res = payments.charge_due_installments("acct_1", today=today)
    assert m.call_count == 2  # 2-я и 3-я доли
    assert res == {"charged": 2, "failed": 0}
    plan.refresh_from_db()
    assert plan.status == "completed"
    plan.ticket.refresh_from_db()
    assert plan.ticket.payment_state == Ticket.PAYMENT_PAID


def test_charge_due_failure_increments_attempts_and_emails():
    import stripe

    from apps.events import payments

    today = timezone.localdate()
    plan = _plan_with_due(today)
    err = stripe.error.CardError("declined", None, "card_declined")
    with (
        mock.patch.object(payments.connect, "charge_off_session", side_effect=err),
        mock.patch("apps.events.notifications.enqueue_installment_failed") as notify_mock,
    ):
        res = payments.charge_due_installments("acct_1", today=today)
    assert res["charged"] == 0 and res["failed"] == 2
    assert notify_mock.called
    c2 = plan.charges.get(sequence=2)
    assert c2.attempts == 1 and c2.status == "scheduled"  # ещё ретраи (max=3)


def test_charge_due_escalates_after_max_attempts(settings):
    import stripe

    from apps.events import payments

    settings.INSTALLMENT_MAX_ATTEMPTS = 1  # сразу эскалация
    today = timezone.localdate()
    plan = _plan_with_due(today)
    err = stripe.error.CardError("declined", None, "card_declined")
    with (
        mock.patch.object(payments.connect, "charge_off_session", side_effect=err),
        mock.patch("apps.events.notifications.enqueue_installment_failed"),
    ):
        payments.charge_due_installments("acct_1", today=today)
    plan.refresh_from_db()
    assert plan.status == "failed"
    assert plan.charges.get(sequence=2).status == "failed"


# --- R10e: отмена билета стопит план ---------------------------------------


def test_cancel_ticket_stops_installment_plan():
    from apps.events.state_machine import TicketSM

    event = _event()
    ticket = book_ticket(event, name="X", email="x@test.de")
    plan = installments.create_plan(ticket, payment_intent="pi_1")
    assert plan.status == "active"
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    plan.refresh_from_db()
    assert plan.status == "cancelled"
