"""KA-12 B2-5 (E1.11): онлайн-оплата ОСТАТКА после Anzahlung (номер/запись/билет).

До этого «Jetzt bezahlen» существовал только для неоплаченного депозита: после
Anzahlung остаток можно было заплатить лишь на месте."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone

from apps.core import balance_pay, folio, money_contract
from apps.core.models import DealPayment
from apps.core.tests.dates import future_month_start
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)


def _tenant(**kw):
    base = {
        "payments_enabled": True,
        "stripe_connect_id": "acct_test",
        "schema_name": connection.schema_name,
        "business_type": "hotel",
        "stripe_payment_methods": None,
        "site_config": {},
        "disabled_modules": [],
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def connect_on(monkeypatch):
    from apps.billing import connect

    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)
    calls = []

    def fake_session(**kw):
        calls.append(kw)
        return "https://checkout.test/s"

    monkeypatch.setattr(connect, "connected_checkout_session", fake_session)
    return calls


def _stay(state=StayBooking.PAYMENT_DEPOSIT, *, arrival=D0, status=None):
    unit = StayUnit.objects.create(
        name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=10000, deposit_cents=3000
    )
    return StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        status=status or StayBooking.STATUS_CONFIRMED,
        price_cents=10000,
        total_cents=20000,
        deposit_cents=3000,
        payment_state=state,
    )


def test_rest_payable_gates(connect_on):
    t = _tenant()
    assert balance_pay.rest_payable("stay", _stay(), t)
    assert not balance_pay.rest_payable("stay", _stay(StayBooking.PAYMENT_PENDING), t)
    assert not balance_pay.rest_payable("stay", _stay(StayBooking.PAYMENT_PAID), t)
    assert not balance_pay.rest_payable("stay", _stay(), _tenant(payments_enabled=False))
    assert not balance_pay.rest_payable("stay", _stay(), _tenant(stripe_connect_id=""))
    past = timezone.localdate() - timedelta(days=10)
    assert not balance_pay.rest_payable("stay", _stay(arrival=past), t)
    cancelled = _stay(status=StayBooking.STATUS_CANCELLED)
    assert not balance_pay.rest_payable("stay", cancelled, t)
    assert not balance_pay.rest_payable("order", _stay(), t)  # заказ — свой путь


def test_pay_view_redirects_deposit_booking_to_rest_checkout(connect_on, monkeypatch):
    from apps.stays import public_views

    monkeypatch.setattr(public_views, "_require_stays_active", lambda r: None)
    b = _stay()
    request = RequestFactory().get("/x/")
    request.tenant = _tenant()
    resp = public_views.stay_pay(request, b.reference_code)
    assert resp.status_code == 302 and resp["Location"] == "https://checkout.test/s"
    call = connect_on[-1]
    assert call["amount_cents"] == 17000  # остаток, а не депозит
    assert call["metadata"]["kind"] == "deal_balance"
    assert call["metadata"]["deal_kind"] == "stay"
    assert call["metadata"]["deal_id"] == str(b.pk)
    assert "expires_at" not in call  # место держит депозит — удержание не нужно


def _webhook(b, intent="pi_rest", amount=17000, schema=None):
    return balance_pay.mark_balance_paid(
        tenant_schema=schema or connection.schema_name,
        deal_kind="stay",
        deal_id=str(b.pk),
        payment_intent=intent,
        amount_cents=amount,
    )


def test_webhook_settles_rest_and_is_idempotent(monkeypatch):
    sent = []
    monkeypatch.setattr(balance_pay, "_notify_owner", lambda *a, **k: sent.append(a))
    b = _stay()
    assert _webhook(b) and _webhook(b)  # повтор вебхука
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_PAID
    assert DealPayment.objects.filter(deal_id=b.pk, stripe_payment_intent="pi_rest").count() == 1
    assert money_contract.due("stay", b) == 0
    assert sent == []  # повтор — не «переплата»


def test_webhook_overpayment_notifies_owner(monkeypatch):
    sent = []
    monkeypatch.setattr(balance_pay, "_notify_owner", lambda *a, **k: sent.append(a))
    b = _stay()
    money_contract.settle_payment("stay", b, source="manual")  # остаток уже на стойке
    b.refresh_from_db()
    _webhook(b)
    assert sent and sent[0][3] == 17000


def test_webhook_on_refunded_deal_does_not_resurrect(monkeypatch):
    sent = []
    monkeypatch.setattr(balance_pay, "_notify_owner", lambda *a, **k: sent.append(k))
    b = _stay(StayBooking.PAYMENT_REFUNDED)
    _webhook(b)
    b.refresh_from_db()
    assert b.payment_state == StayBooking.PAYMENT_REFUNDED
    assert not folio.rows("stay", b) or all(
        r.stripe_payment_intent != "pi_rest" for r in folio.rows("stay", b)
    )
    assert sent and sent[0].get("refunded") is True


def test_webhook_unknown_deal_or_kind_writes_nothing():
    b = _stay()
    assert not balance_pay.mark_balance_paid(
        tenant_schema=connection.schema_name,
        deal_kind="order",
        deal_id=str(b.pk),
        payment_intent="pi_x",
        amount_cents=100,
    )
    assert not balance_pay.mark_balance_paid(
        tenant_schema=connection.schema_name,
        deal_kind="stay",
        deal_id=str(uuid.uuid4()),
        payment_intent="pi_x",
        amount_cents=100,
    )
    assert not DealPayment.objects.filter(stripe_payment_intent="pi_x").exists()


def test_confirmation_shows_rest_button(connect_on):
    from django.template.loader import render_to_string

    b = _stay()
    request = RequestFactory().get("/")
    request.tenant = _tenant()
    html = render_to_string(
        "storefront/stay_confirmation.html", {"booking": b, "b": b}, request=request
    )
    assert "data-rest-pay" in html


def test_cabinet_pay_link_emails_customer(connect_on):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core.views import deal_pay_link
    from apps.notifications.models import Notification

    b = _stay()
    request = RequestFactory().post("/x/", {"next": "//evil.test/"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    request.tenant = _tenant()
    resp = deal_pay_link(request, "stay", b.pk)
    assert resp.status_code == 302 and not resp["Location"].startswith("//")
    note = Notification.objects.filter(type="deal_rest_link").order_by("-created_at").first()
    assert note is not None and note.recipient == b.customer.email
    body = note.payload.get("body", "")
    assert f"/{b.reference_code}/" in body and "170,00" in body


def test_cabinet_pay_link_requires_login():
    from django.contrib.auth.models import AnonymousUser

    from apps.core.views import deal_pay_link

    request = RequestFactory().post("/x/")
    request.user = AnonymousUser()
    assert deal_pay_link(request, "stay", uuid.uuid4()).status_code == 302
