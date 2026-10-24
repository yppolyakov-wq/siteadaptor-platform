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

from apps.finance.services import invoice_from_order, invoice_from_stay
from apps.loyalty.models import Voucher
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


def _order(code):
    from apps.catalog.tests.factories import ProductFactory

    product = ProductFactory(base_price=Decimal("11.90"), vat_rate=Decimal("19.00"))
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


# --- KA-12 B2-1: точное voucher_paid_cents ---------------------------------------------


def test_spend_points_record_certificate_part_exactly():
    """Сертификат с остатком пишет voucher_paid_cents, промокод — нет."""
    Voucher.objects.create(code="WERT11", label="Gutschein", balance_cents=1100)
    Voucher.objects.create(code="PROMO11", label="Promo", discount_percent=10)
    assert _order("WERT11").voucher_paid_cents == 1100
    assert _order("PROMO11").voucher_paid_cents == 0


def test_stay_booking_ticket_record_certificate_part():
    from apps.booking import services as booking_services
    from apps.booking.models import Resource
    from apps.events import services as event_services
    from apps.events.models import Event
    from apps.stays import services as stay_services
    from apps.stays.models import StayUnit

    Voucher.objects.create(code="WERTX", label="Gutschein", balance_cents=50000, max_uses=0)
    today = timezone.localdate()
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=8000)
    stay = stay_services.book_stay(
        unit,
        arrival=today + timedelta(days=9),
        departure=today + timedelta(days=10),
        name="Gast",
        voucher_code="WERTX",
    )
    assert stay.voucher_paid_cents == stay.discount_cents > 0

    start = timezone.now().replace(microsecond=0) + timedelta(days=7)
    res = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    booking = booking_services.book(
        res,
        start=start,
        end=start + timedelta(hours=1),
        name="Gast",
        price_cents=3000,
        voucher_code="WERTX",
    )
    assert booking.voucher_paid_cents == booking.discount_cents > 0

    event = Event.objects.create(
        title="Tour",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        status=Event.STATUS_PUBLISHED,
        capacity=10,
        price_cents=2000,
    )
    ticket = event_services.book_ticket(event, name="Gast", email="g@t.de", voucher_code="WERTX")
    assert ticket.voucher_paid_cents == ticket.discount_cents > 0


def test_owner_can_add_discount_on_top_of_certificate():
    """С точным полем скидка владельца поверх сертификата — Rabatt, сертификат — оплата."""
    from apps.core import deal_discount

    Voucher.objects.create(code="WERT12", label="Gutschein", balance_cents=1000)
    order = _order("WERT12")  # 23,80 − 10,00
    from apps.orders import editing

    editing.set_discount(order, cents=1500)  # +5,00 € скидки владельца
    order.refresh_from_db()
    invoice = invoice_from_order(order)
    rabatt = [ln for ln in invoice.lines if ln["text"] == "Rabatt"]
    assert len(rabatt) == 1
    assert invoice.gross == Decimal("18.80")  # 23,80 − 5,00 Rabatt
    assert invoice.prepaid_cents == 1000  # сертификат — оплата
    with pytest.raises(editing.OrderLocked):
        editing.set_discount(order, cents=500)  # ниже суммы сертификата — нельзя
    assert deal_discount.certificate_locked(order, 0) is True
    assert deal_discount.certificate_locked(order, 1000) is False
