"""KA-12 WR-8 (E1.5): поштучный возврат — товар на склад по выбору, деньги путём Minderung,
полный `returned` после частичного не кладёт на склад второй раз."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db.models import Sum

from apps.billing import connect
from apps.core import folio, refunds
from apps.core.models import DealPayment
from apps.finance.models import RevenueEntry
from apps.finance.services import record_revenue
from apps.orders import returns
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(stripe_connect_id="acct_test", owner_email="o@t.de", schema_name="x")


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "refund", lambda **kw: calls.append(kw))
    return calls


def _order(qty=3, price="10.00", stock=10):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal(price), stock_quantity=stock)
    order = create_order(items=[(product, None, qty)], name="Gast", email="g@t.de")
    Order.objects.filter(pk=order.pk).update(status="picked_up", payment_state="paid")
    order.refresh_from_db()
    record_revenue(source="order", source_ref=str(order.id), amount=order.total)
    DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="full",
        method="stripe",
        amount_cents=int(order.total * 100),
        stripe_payment_intent="pi_main",
        source="webhook",
    )
    folio.forget(order)
    product.refresh_from_db()
    return order, product


def _line(order, qty, restock=True):
    item = order.items.get()
    return returns.Line(
        item_pk=str(item.pk), qty=qty, restock=restock, expected_returned=item.returned_qty
    )


def _net(order):
    return Decimal(
        RevenueEntry.objects.filter(source="order", source_ref__startswith=str(order.id)).aggregate(
            s=Sum("amount")
        )["s"]
        or 0
    )


def test_partial_return_restocks_refunds_card_and_lowers_price(stripe_calls):
    order, product = _order()
    assert product.stock_quantity == 7
    out = returns.return_items(order, [_line(order, 1)], method="card", tenant=TENANT)
    assert out.goods == returns.GoodsResult.RETURNED and out.cents == 1000
    assert out.refund == refunds.RefundResult.REFUNDED
    assert stripe_calls[0]["amount_cents"] == 1000
    product.refresh_from_db()
    order.refresh_from_db()
    assert product.stock_quantity == 8
    assert order.total == Decimal("20.00")
    assert _net(order) == Decimal("20.00")
    item = order.items.get()
    assert (item.returned_qty, item.restocked_qty) == (1, 1)


def test_damaged_piece_is_not_restocked_and_full_return_skips_processed_pieces():
    order, product = _order()
    returns.return_items(order, [_line(order, 1, restock=False)], method="none")
    product.refresh_from_db()
    assert product.stock_quantity == 7  # повреждённая — не на склад
    OrderSM().apply(order, "returned")
    product.refresh_from_db()
    assert product.stock_quantity == 9  # полный возврат — только 2 оставшиеся штуки


def test_double_submit_is_stale_and_over_quantity_refused():
    order, product = _order()
    line = _line(order, 2)
    assert returns.return_goods(order, [line])[0] == returns.GoodsResult.RETURNED
    assert returns.return_goods(order, [line])[0] == returns.GoodsResult.STALE
    assert returns.return_goods(order, [_line(order, 5)])[0] == returns.GoodsResult.STALE
    product.refresh_from_db()
    assert product.stock_quantity == 9


def test_only_picked_up_or_shipped_orders():
    order, _ = _order()
    Order.objects.filter(pk=order.pk).update(status="confirmed")
    assert returns.return_goods(order, [_line(order, 1)])[0] == returns.GoodsResult.NOT_RETURNABLE


def test_refund_refused_when_amount_exceeds_paid_but_goods_kept(stripe_calls):
    order, product = _order()
    DealPayment.objects.filter(deal_kind="order", deal_id=order.pk).update(refunded_cents=2500)
    folio.forget(order)
    out = returns.return_items(order, [_line(order, 1)], method="card", tenant=TENANT)
    assert out.goods == returns.GoodsResult.RETURNED
    assert out.refund == refunds.RefundResult.REFUSED and stripe_calls == []
    product.refresh_from_db()
    assert product.stock_quantity == 8
