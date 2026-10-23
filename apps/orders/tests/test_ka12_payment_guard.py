"""KA-12 E2.6: онлайн-/Vorkasse-заказ выдаётся только после оплаты."""

import pytest

from apps.core.fsm import PaymentRequired
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _ready(method, state="unpaid", code="O-PG0001"):
    customer = Customer.objects.create(name="Kim", email="kim@example.com")
    return Order.objects.create(
        customer=customer,
        reference_code=code,
        status="ready",
        payment_method=method,
        payment_state=state,
        total=12,
    )


@pytest.mark.parametrize("method", ["stripe", "vorkasse"])
@pytest.mark.parametrize("dst", ["picked_up", "shipped"])
def test_unpaid_prepay_order_cannot_be_handed_over(method, dst):
    order = _ready(method)
    with pytest.raises(PaymentRequired):
        OrderSM().apply(order, dst)
    order.refresh_from_db()
    assert order.status == "ready"


@pytest.mark.parametrize("method", ["", "on_site", "invoice"])
def test_pay_later_orders_pass_and_on_site_settles(method):
    order = _ready(method)
    OrderSM().apply(order, "picked_up")
    order.refresh_from_db()
    assert order.status == "picked_up"
    if method in ("", "on_site"):
        assert order.payment_state == "paid"  # X1: оплата при выдаче


def test_paid_online_order_passes():
    order = _ready("stripe", state="paid")
    OrderSM().apply(order, "picked_up")
    order.refresh_from_db()
    assert order.status == "picked_up"


def test_board_action_answers_409_with_message():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    order = _ready("vorkasse")
    req = RequestFactory().post("/", {"action": "picked_up"}, headers={"X-Requested-With": "fetch"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = get_user_model().objects.create_user(username="pg-own", password="pw12345678")
    req.tenant = TenantFactory.build()
    resp = views.kanban_action.__wrapped__(req, kind="order", pk=order.pk)
    assert resp.status_code == 409 and "Zahlungseingang" in resp.content.decode()


# --- E2.5: счётчики = список по их ссылке ----------------------------------------


def test_counters_match_list_filters():
    import datetime

    from django.http import QueryDict
    from django.utils import timezone

    from apps.orders import counters

    customer = Customer.objects.create(name="Lea", email="lea@example.com")
    now = timezone.now()
    Order.objects.create(
        customer=customer,
        reference_code="O-C1",
        status="new",
        pickup_slot=now,
        payment_method="stripe",
        payment_state="unpaid",
    )
    Order.objects.create(
        customer=customer,
        reference_code="O-C2",
        status="ready",
        pickup_slot=now + datetime.timedelta(days=2),
    )
    Order.objects.create(
        customer=customer,
        reference_code="O-C3",
        status="cancelled",
        pickup_slot=now,
        payment_method="vorkasse",
        payment_state="unpaid",
    )
    got = {key: (count, query) for key, _i, _l, count, query in counters.counters()}
    # «unbezahlt» = то же правило, что Offene Posten (on_site до выдачи — тоже долг)
    assert got["pickup_today"][0] == 1 and got["new"][0] == 1 and got["unpaid"][0] == 2
    for key, (count, query) in got.items():
        params = QueryDict(query.lstrip("?"))
        qs = Order.objects.all()
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        assert counters.apply_list_filters(qs, params).count() == count, key


def test_zero_total_prepay_order_is_not_blocked():
    order = _ready("stripe", code="O-PG0002")
    order.total = 0
    order.save(update_fields=["total"])
    OrderSM().apply(order, "picked_up")
    order.refresh_from_db()
    assert order.status == "picked_up"
