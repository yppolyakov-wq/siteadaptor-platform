"""KA-12 B2-7a: сертификату при отмене/возврате сделки возвращается ровно списанное.

Раньше возвращался `discount_cents` — а там после DC-5 и Minderung сидят и скидка
владельца, и уступка: сертификат получал больше, чем с него сняли. И возврат заказа
(`returned`) сертификат не возвращал вовсе."""

from decimal import Decimal

import pytest

from apps.loyalty.models import Voucher
from apps.orders.services import create_order
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


def _order(code):
    from apps.catalog.tests.factories import ProductFactory

    product = ProductFactory(base_price=Decimal("20.00"))
    return create_order(items=[(product, None, 2)], name="Gast", voucher_code=code)


def test_cancel_returns_only_certificate_part_not_owner_discount():
    from apps.core import deal_discount

    Voucher.objects.create(code="WERT30", label="Gutschein", balance_cents=3000)
    order = _order("WERT30")  # 40 € − 30 € сертификат
    assert order.voucher_paid_cents == 3000
    deal_discount.set_discount("order", order, cents=3500)  # +5 € скидки владельца
    order.refresh_from_db()
    OrderSM().apply(order, "cancelled")
    assert Voucher.objects.get(code="WERT30").balance_cents == 3000  # не 3500


def test_returned_order_gives_certificate_back():
    Voucher.objects.create(code="WERT20", label="Gutschein", balance_cents=2000)
    order = _order("WERT20")
    for status in ("confirmed", "ready", "picked_up", "returned"):
        OrderSM().apply(order, status)
        order.refresh_from_db()
    assert Voucher.objects.get(code="WERT20").balance_cents == 2000


def test_custom_cancel_status_returns_the_same_amount():
    """Кастом-статус с ролью cancelled (FB-3 B) идёт через status_effects — та же сумма."""
    from apps.core import deal_discount, status_effects

    Voucher.objects.create(code="WERT15", label="Gutschein", balance_cents=1500)
    order = _order("WERT15")
    deal_discount.set_discount("order", order, cents=2000)
    order.refresh_from_db()
    status_effects.unredeem_for(order)
    assert Voucher.objects.get(code="WERT15").balance_cents == 1500
