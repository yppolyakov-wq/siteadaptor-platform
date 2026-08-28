"""VAT-4: счёт из заказа со смешанными ставками сходится с самим заказом.

Дефект, найденный разведкой 2026-08-26: `invoice_from_order` считал ВЕСЬ счёт по
одной преобладающей ставке. Заказ 11,90 € @19 % + 10,70 € @7 % (демо-кит cafe со
смешанным чеком — ровно этот случай) давал счёт 23,80 € вместо 22,60 €: ошибка
5 % в пользу бизнеса. Это же ломало сопоставление платежа в ERP-2 (сверка по
равной сумме) и Mahnung — требование на сумму, которой клиент не покупал.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product
from apps.finance.services import compute_totals, invoice_from_order, invoice_from_stay
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def mixed_order():
    category = Category.objects.create(name="Theke")
    food = Product.objects.create(
        category=category, name="Kuchen", base_price=Decimal("10.70"), vat_rate=Decimal("7.00")
    )
    drink = Product.objects.create(
        category=category, name="Cocktail", base_price=Decimal("11.90"), vat_rate=Decimal("19.00")
    )
    return create_order(items=[(food, None, 1), (drink, None, 1)], name="Gast")


def test_invoice_total_matches_the_order(mixed_order):
    invoice = invoice_from_order(mixed_order)

    assert invoice.gross == mixed_order.total
    assert invoice.gross == Decimal("22.60")
    # 10,00 + 10,00 нетто, налог 0,70 + 1,90
    assert invoice.net == Decimal("20.00")
    assert invoice.vat_amount == Decimal("2.60")


def test_every_invoice_line_carries_its_rate(mixed_order):
    """У каждой строки счёта своя ставка — по ней PDF печатает разбивку."""
    invoice = invoice_from_order(mixed_order)

    assert {line["vat_rate"] for line in invoice.lines} == {"7.00", "19.00"}
    assert all(line.get("vat_rate") for line in invoice.lines)


def test_single_rate_invoice_is_unchanged():
    """Замок совместимости: обычный заказ считается ровно как раньше."""
    category = Category.objects.create(name="Theke")
    product = Product.objects.create(
        category=category, name="Brot", base_price=Decimal("11.90"), vat_rate=Decimal("19.00")
    )
    order = create_order(items=[(product, None, 2)], name="Gast")

    invoice = invoice_from_order(order)

    assert invoice.gross == order.total == Decimal("23.80")
    assert invoice.vat_rate == Decimal("19.00")


def test_compute_totals_without_line_rates_behaves_as_before():
    """Старые вызовы (строки без ставки) идут по переданной ставке."""
    lines = [{"text": "Arbeit", "qty": 2, "unit_price": "50.00"}]

    net, vat, gross = compute_totals(lines, Decimal("19.00"))

    assert (net, vat, gross) == (Decimal("100.00"), Decimal("19.00"), Decimal("119.00"))


def test_small_business_zeroes_mixed_lines():
    """§19: ставки строк не создают налога."""
    lines = [
        {"text": "Speisen", "qty": 1, "unit_price": "100.00", "vat_rate": "7.00"},
        {"text": "Getränke", "qty": 1, "unit_price": "100.00", "vat_rate": "19.00"},
    ]

    net, vat, gross = compute_totals(lines, Decimal("19.00"), small_business=True)

    assert (net, vat, gross) == (Decimal("200.00"), Decimal("0.00"), Decimal("200.00"))


def test_stay_invoice_matches_the_booking_with_mixed_rates():
    """Бронь: проживание 7 %, завтрак 19 %, Kurtaxe без налога — итог сходится.

    Раньше все строки шли по ставке проживания, а курортный сбор добавлялся
    брутто и всё равно облагался 7 % — счёт выходил больше самой брони.
    """
    import uuid
    from datetime import timedelta

    from django.utils import timezone

    from apps.stays import services as stay_services
    from apps.stays.models import StayUnit

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
    )
    booking.extras = [
        {"label": "Frühstück", "price_cents": 2400, "vat_rate": "19.00"},
    ]
    booking.kurtaxe_cents = 300
    booking.total_cents = booking.total_cents + 2400 + 300
    booking.save(update_fields=["extras", "kurtaxe_cents", "total_cents"])

    invoice = invoice_from_stay(booking)

    assert invoice.gross == Decimal(booking.total_cents) / 100
