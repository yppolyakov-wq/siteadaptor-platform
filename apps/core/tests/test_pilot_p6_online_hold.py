"""KA-P6 (аудит KA-5d Z7, KA-5e E10): брошенная онлайн-оплата не держит номер /
время / место бессрочно. Уход на Stripe ставит срок удержания (24 ч — максимум жизни
сессии Stripe, сама сессия закрывается чуть раньше); оплата снимает удержание из
выборки, просрочка отменяет сделку штатным путём FSM (`expire_payment_holds`)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import payment_holds
from apps.core.tests.test_ka_h4_refunds import (  # noqa: F401
    _booking,
    _stay,
    _tenant,
    _ticket,
    _urlconf,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def sessions(monkeypatch):
    calls = []

    def _fake(**kw):
        calls.append(kw)
        return "https://checkout.example/x"

    monkeypatch.setattr("apps.billing.connect.connected_checkout_session", _fake)
    return calls


def _checkout(kind, obj):
    tenant = _tenant()
    if kind == "stay":
        from apps.stays import payments

        obj.deposit_cents = 5000
        obj.save(update_fields=["deposit_cents"])
        return payments.stay_deposit_checkout_url(obj, tenant, success_url="/", cancel_url="/")
    if kind == "booking":
        from apps.booking import payments

        obj.deposit_cents = 1000
        obj.save(update_fields=["deposit_cents"])
        return payments.deposit_checkout_url(obj, tenant, success_url="/", cancel_url="/")
    from apps.events import payments

    return payments.ticket_checkout_url(obj, tenant, success_url="/", cancel_url="/")


@pytest.mark.parametrize("kind,make", [("stay", _stay), ("booking", _booking), ("ticket", _ticket)])
def test_checkout_sets_hold_and_session_expiry(sessions, kind, make):
    obj = make()
    before = timezone.now()
    _checkout(kind, obj)
    obj.refresh_from_db()
    assert obj.payment_due_at is not None
    assert before + timedelta(hours=23) < obj.payment_due_at <= before + timedelta(hours=25)
    expires = sessions[0]["expires_at"]
    assert expires < obj.payment_due_at.timestamp()  # сессия закрывается раньше удержания


def test_abandoned_checkout_is_cancelled_after_hold(sessions):
    stay = _stay()
    _checkout("stay", stay)
    stay.refresh_from_db()
    later = stay.payment_due_at + timedelta(minutes=1)
    assert payment_holds.expire_overdue(_tenant(), now=later, kinds=("stay",)) == 1
    stay.refresh_from_db()
    assert stay.status == "cancelled"


def test_paid_checkout_survives(sessions):
    stay = _stay()
    _checkout("stay", stay)
    stay.refresh_from_db()
    stay.payment_state = "paid"
    stay.save(update_fields=["payment_state"])
    later = stay.payment_due_at + timedelta(minutes=1)
    assert payment_holds.expire_overdue(_tenant(), now=later, kinds=("stay",)) == 0


def test_longer_existing_hold_is_not_shortened(sessions):
    stay = _stay()
    far = timezone.now() + timedelta(days=14)  # счёт фирме: срок оплаты 14 дней
    type(stay).objects.filter(pk=stay.pk).update(payment_due_at=far)
    stay.refresh_from_db()
    _checkout("stay", stay)
    stay.refresh_from_db()
    assert stay.payment_due_at == far


def test_late_payment_on_released_stay_is_refunded(sessions, monkeypatch):
    from apps.stays import payments
    from apps.stays.state_machine import StayBookingSM
    from apps.tenants.tests.factories import TenantFactory

    refunds = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: refunds.append(kw))
    TenantFactory(schema_name="public", stripe_connect_id="acct_1")
    stay = _stay()
    StayBookingSM().apply(stay, "cancelled")  # удержание истекло
    from django.db import connection

    payments.mark_stay_paid(
        tenant_schema=connection.schema_name, booking_id=str(stay.id), payment_intent="pi_late"
    )
    stay.refresh_from_db()
    assert stay.payment_state == "refunded" and refunds
