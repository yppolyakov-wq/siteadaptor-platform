"""KA-12 B2-4b: Minderung — часть цены возвращается, и цена сделки снижается.

Переплата (B2-4a) цену не трогает. Minderung — уступка в цене (повреждённый товар,
недоделанная услуга): деньги назад, итог сделки меньше, проведённая выручка
сторнируется на ту же сумму. Отмена после Minderung не должна сторнировать дважды."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from django.db.models import Sum

from apps.billing import connect
from apps.core import folio, money_contract, refunds
from apps.core.models import DealPayment
from apps.core.tests.dates import future_month_start
from apps.finance.models import RevenueEntry
from apps.finance.services import record_revenue
from apps.promotions.models import Customer
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)
TENANT = SimpleNamespace(stripe_connect_id="acct_test", owner_email="o@t.de", schema_name="x")


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "refund", lambda **kw: calls.append(kw))
    return calls


def _card_row(kind, obj, cents, intent="pi_main"):
    row = DealPayment.objects.create(
        deal_kind=kind,
        deal_id=obj.pk,
        purpose="full",
        method="stripe",
        amount_cents=cents,
        stripe_payment_intent=intent,
        source="webhook",
    )
    folio.forget(obj)
    return row


def _net(source, obj):
    total = (
        RevenueEntry.objects.filter(source=source, source_ref__startswith=str(obj.id)).aggregate(
            s=Sum("amount")
        )["s"]
        or 0
    )
    return Decimal(total)


def _order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.models import Order
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("11.90"), vat_rate=Decimal("19.00"))
    order = create_order(items=[(product, None, 2)], name="Gast", email="g@t.de")
    Order.objects.filter(pk=order.pk).update(status="fulfilled", payment_state="paid")
    order.refresh_from_db()
    record_revenue(source="order", source_ref=str(order.id), amount=order.total)
    _card_row("order", order, 2380)
    return order


def _stay():
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=15000)
    b = StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=D0,
        departure=D0 + timedelta(days=2),
        status=StayBooking.STATUS_CONFIRMED,
        price_cents=15000,
        total_cents=30000,
        deposit_cents=30000,
        payment_state=StayBooking.PAYMENT_PAID,
        stripe_payment_intent="pi_main",
    )
    _card_row("stay", b, 30000)
    return b


def test_order_minderung_lowers_price_refunds_and_reverses_revenue(stripe_calls):
    order = _order()
    result = refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    assert result == refunds.RefundResult.REFUNDED
    assert stripe_calls[-1]["amount_cents"] == 500
    order.refresh_from_db()
    assert order.discount_cents == 500
    assert order.total == Decimal("18.80")
    assert _net("order", order) == Decimal("18.80")
    assert money_contract.due("order", order) == 0


def test_minderung_refused_with_issued_invoice(stripe_calls):
    from apps.finance.models import Invoice
    from apps.finance.services import invoice_from_order

    order = _order()
    inv = invoice_from_order(order)
    Invoice.objects.filter(pk=inv.pk).update(
        status=Invoice.STATUS_ISSUED, deal_kind="order", deal_id=order.reference_code
    )
    result = refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    assert result == refunds.RefundResult.REFUSED
    assert stripe_calls == []


def test_minderung_rejected_by_stripe_keeps_price(monkeypatch):
    def boom(**kw):
        raise stripe.error.InvalidRequestError("nope", "amount")

    monkeypatch.setattr(connect, "refund", boom)
    order = _order()
    refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    order.refresh_from_db()
    assert order.discount_cents == 0 and order.total == Decimal("23.80")


def test_minderung_more_than_price_is_refused(stripe_calls):
    order = _order()
    assert (
        refunds.refund_partial(
            "order", order, cents=3000, method="card", tenant=TENANT, reason="minderung"
        )
        == refunds.RefundResult.REFUSED
    )


def test_stay_cancel_after_minderung_does_not_reverse_twice(stripe_calls):
    from apps.core import status_effects

    b = _stay()
    record_revenue(source="stay", source_ref=str(b.id), amount=Decimal("300.00"))
    refunds.refund_partial("stay", b, cents=5000, method="card", tenant=TENANT, reason="minderung")
    b.refresh_from_db()
    assert b.total_cents == 25000
    assert _net("stay", b) == Decimal("250.00")
    status_effects.record_reversal_for("stay", b)
    assert _net("stay", b) == 0  # не −50


def test_booking_cancel_after_minderung_does_not_reverse_twice(stripe_calls):
    from django.utils import timezone

    from apps.booking.models import Booking, Resource
    from apps.core import status_effects

    start = timezone.now() + timedelta(days=5)
    b = Booking.objects.create(
        resource=Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}"),
        customer=Customer.objects.create(name="Gast", email=f"{uuid.uuid4().hex[:6]}@t.de"),
        reference_code=f"T-{uuid.uuid4().hex[:6].upper()}",
        start=start,
        end=start + timedelta(hours=1),
        price_cents=6000,
        payment_state=Booking.PAYMENT_PAID,
        stripe_payment_intent="pi_main",
    )
    _card_row("booking", b, 6000)
    record_revenue(source="booking", source_ref=str(b.id), amount=Decimal("60.00"))
    refunds.refund_partial(
        "booking", b, cents=1000, method="card", tenant=TENANT, reason="minderung"
    )
    b.refresh_from_db()
    assert b.total_cents == 5000
    status_effects.record_reversal_for("booking", b)
    assert _net("booking", b) == 0


def test_ticket_minderung_is_refused():
    obj = SimpleNamespace(pk=uuid.uuid4(), payment_state="paid", status="confirmed")
    assert (
        refunds.refund_partial(
            "ticket", obj, cents=100, method="card", tenant=TENANT, reason="minderung"
        )
        == refunds.RefundResult.REFUSED
    )


def test_owner_form_offers_minderung_and_endpoint_applies_it(stripe_calls):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.deal_card import _refund_form
    from apps.core.models import Membership
    from apps.core.views import deal_refund

    user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:6]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    order = _order()
    request = RequestFactory().post(
        "/x/", {"amount": "5,00", "method": "card", "reason": "minderung"}
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = TENANT
    form = _refund_form(request, "order", order, TENANT)
    assert form and form["minder_eur"] == Decimal("23.80") and not form["open_eur"]
    deal_refund(request, "order", order.pk)
    order.refresh_from_db()
    assert order.discount_cents == 500


def test_stay_minderung_keeps_booked_price_when_rates_changed(stripe_calls):
    """Ревью: итог брони — от цены брони, не от сегодняшнего тарифа."""
    b = _stay()
    StayUnit.objects.filter(pk=b.unit_id).update(price_cents=40000)
    refunds.refund_partial("stay", b, cents=5000, method="card", tenant=TENANT, reason="minderung")
    b.refresh_from_db()
    assert b.total_cents == 25000
    assert money_contract.due("stay", b) == 0


def test_second_minderung_after_discount_reset_still_reverses(stripe_calls):
    """Ревью: ключ сторно уникален — повтор суммы скидки не глотает сторно."""
    from apps.core import deal_discount

    order = _order()
    refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    order.refresh_from_db()
    deal_discount.set_discount("order", order, cents=0, allow_closed=True)
    refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    reversals = RevenueEntry.objects.filter(
        source="order", source_ref__contains=":minderung:"
    ).filter(source_ref__startswith=str(order.id))
    assert reversals.count() == 2


def test_minderung_splits_across_lodging_and_meal_with_own_rates(stripe_calls):
    b = _stay()
    record_revenue(
        source="stay", source_ref=str(b.id), amount=Decimal("200.00"), vat_rate=Decimal("7.00")
    )
    record_revenue(
        source="stay",
        source_ref=f"{b.id}:meal",
        amount=Decimal("100.00"),
        vat_rate=Decimal("19.00"),
    )
    refunds.refund_partial("stay", b, cents=25000, method="card", tenant=TENANT, reason="minderung")
    rows = {
        r.vat_rate: -r.amount
        for r in RevenueEntry.objects.filter(
            source="stay", source_ref__contains=":minderung:"
        ).filter(source_ref__startswith=str(b.id))
    }
    assert rows == {Decimal("7.00"): Decimal("200.00"), Decimal("19.00"): Decimal("50.00")}


def test_minderung_after_concurrent_cancel_is_not_applied(monkeypatch):
    """Ревью: сделку отменили между захватом и Stripe — цену и выручку не трогаем."""
    order = _order()
    from apps.orders.models import Order

    def refund_and_cancel(**kw):
        Order.objects.filter(pk=order.pk).update(status="cancelled")

    monkeypatch.setattr(connect, "refund", refund_and_cancel)
    result = refunds.refund_partial(
        "order", order, cents=500, method="card", tenant=TENANT, reason="minderung"
    )
    assert result == refunds.RefundResult.UNCERTAIN
    order.refresh_from_db()
    assert order.discount_cents == 0
