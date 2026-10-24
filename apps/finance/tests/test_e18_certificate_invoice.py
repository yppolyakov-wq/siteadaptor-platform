"""KA-12 E1.8 (MC-Z9): сертификат с остатком в счёте — оплата, а не Rabatt.

Wertgutschein (Mehrzweckgutschein) — средство платежа: счёт идёт на полную цену,
налог считается с полной цены, а сертификат вычитается как уже полученные деньги.
Раньше счёт из брони/записи/заказа ставил его минус-строкой «Rabatt» и резал базу
НДС — так же, как у заявок до KA-H5. Обычный промокод остаётся Rabatt.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.finance.services import invoice_from_order, invoice_from_stay
from apps.loyalty.models import Voucher
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


def _order(code):
    category = Category.objects.create(name="Theke")
    product = Product.objects.create(
        category=category, name="Brot", base_price=Decimal("11.90"), vat_rate=Decimal("19.00")
    )
    return create_order(items=[(product, None, 2)], name="Gast", voucher_code=code)


def test_order_certificate_is_a_payment_not_a_discount():
    Voucher.objects.create(code="WERT10", label="Gutschein", balance_cents=1000)
    order = _order("WERT10")
    assert order.discount_cents == 1000  # 23,80 − 10,00

    invoice = invoice_from_order(order)

    assert not any("Rabatt" in line["text"] for line in invoice.lines)
    assert invoice.gross == Decimal("23.80")  # полная цена
    assert invoice.vat_amount == Decimal("3.80")  # налог с полной цены
    assert invoice.prepaid_cents == 1000  # сертификат уже «получен»
    assert "WERT10" in invoice.note


def test_order_promo_code_stays_a_discount():
    Voucher.objects.create(code="SOMMER", label="Promo", discount_percent=10)
    order = _order("SOMMER")
    assert order.discount_cents

    invoice = invoice_from_order(order)

    assert any(line["text"] == "Rabatt" for line in invoice.lines)
    assert invoice.gross == order.total
    assert invoice.prepaid_cents == 0


def test_stay_certificate_is_a_payment_not_a_discount():
    from apps.stays import services as stay_services
    from apps.stays.models import StayUnit

    Voucher.objects.create(code="WERT30", label="Gutschein", balance_cents=3000)
    unit = StayUnit.objects.create(
        name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=10000, vat_rate=Decimal("7.00")
    )
    today = timezone.localdate()
    booking = stay_services.book_stay(
        unit,
        arrival=today + timedelta(days=3),
        departure=today + timedelta(days=5),
        name="Clara Gast",
        email="clara@t.de",
        voucher_code="WERT30",
    )
    assert booking.discount_cents == 3000

    invoice = invoice_from_stay(booking)

    assert not any("Rabatt" in line["text"] for line in invoice.lines)
    assert invoice.gross == Decimal(booking.total_cents + 3000) / 100
    assert invoice.prepaid_cents == 3000
