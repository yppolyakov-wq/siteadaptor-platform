"""Bruttomethode: счёт из брутто-сделки равен ей до цента, налог — `split_gross`.

Раньше НДС считался от нетто в центах, и часть брутто-сумм была недостижима
(45,00 € @19 % → 45,01 €) — счёт расходился со сделкой, журналом и сверкой оплат.
Ручные счета и сметы (net) — байт-в-байт прежние."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finance.services import compute_totals, create_storno, invoice_from_booking
from apps.finance.totals import gross_line, rate_groups
from apps.orders.totals import split_gross

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("rate", ["19", "7", "0"])
def test_every_gross_amount_reachable(rate):
    for cents in list(range(1, 3000)) + [4500, 9999, 12345, 100000]:
        g = Decimal(cents) / 100
        for qty in (1, 2):
            lines = [gross_line("x", qty, g, rate)]
            net, vat, gross = compute_totals(lines, rate, basis="gross")
            assert gross == g * qty
            assert (net, vat) == split_gross(g * qty, Decimal(rate))


def test_mixed_rates_group_by_rate():
    lines = [gross_line("Essen", 1, "10.70", 7), gross_line("Getränk", 1, "11.90", 19)]
    rows = rate_groups(lines, 19, basis="gross")
    assert [(r[0], r[3]) for r in rows] == [
        (Decimal("19"), Decimal("11.90")),
        (Decimal("7"), Decimal("10.70")),
    ]


def test_net_mode_byte_identical():
    lines = [{"text": "a", "qty": 1, "unit_price": "37.82"}]
    assert compute_totals(lines, "19") == (Decimal("37.82"), Decimal("7.19"), Decimal("45.01"))


def _booking(price_cents):
    from apps.booking import services
    from apps.booking.tests.test_services import _resource, _service

    start = timezone.now() + timedelta(days=2)
    return services.book(
        _resource(),
        start=start,
        end=start + timedelta(hours=1),
        name="G",
        email="g@t.de",
        service=_service(price_cents=price_cents),
        price_cents=price_cents,
    )


@pytest.mark.parametrize("cents", [4500, 1999, 3333, 12345])
def test_invoice_from_booking_exact_and_no_residual(cents, caplog):
    b = _booking(cents)
    inv = invoice_from_booking(b)
    assert inv.price_basis == "gross" and inv.gross == Decimal(b.total_cents) / 100
    assert "rounding residual" not in caplog.text and "differs from deal" not in caplog.text


def test_storno_of_gross_invoice_copies_basis_and_mirrors_sums():
    from apps.finance.models import Invoice
    from apps.finance.services import issue_invoice

    inv = invoice_from_booking(_booking(4500))
    issue_invoice(inv)
    inv.refresh_from_db()
    storno = create_storno(inv)
    assert storno.price_basis == "gross" and storno.gross == -inv.gross
    from apps.finance.pdf import _rate_rows

    rows = _rate_rows(storno)
    assert sum(r[1] + r[2] for r in rows) == -inv.gross
    assert Invoice.objects.filter(pk=inv.pk, price_basis="gross").exists()


def test_pdf_rate_rows_of_gross_invoice_match_document():
    from apps.finance.pdf import _rate_rows

    inv = invoice_from_booking(_booking(4500))
    rows = _rate_rows(inv)
    assert rows == [(Decimal("19.00"), inv.net, inv.vat_amount)] or (
        sum(r[1] for r in rows) == inv.net and sum(r[2] for r in rows) == inv.vat_amount
    )


@pytest.mark.parametrize("bad", ["abc", "NaN", "Infinity"])
def test_garbage_amount_raises_not_zero(bad):
    from decimal import InvalidOperation

    with pytest.raises(InvalidOperation):
        rate_groups([gross_line("x", 1, "1.00", 19) | {"unit_gross": bad}], 19, basis="gross")


def test_gross_line_without_unit_gross_raises():
    with pytest.raises(ValueError):
        rate_groups(
            [{"text": "x", "qty": 1, "unit_price": "1.00", "vat_rate": "19"}], 19, basis="gross"
        )


def test_pdf_fallback_is_logged(caplog):
    from apps.finance.models import Invoice
    from apps.finance.pdf import _rate_rows

    inv = Invoice(
        price_basis="gross",
        lines=[{"text": "x", "qty": 1, "unit_price": "1", "vat_rate": "19"}],
        vat_rate=Decimal("19"),
        net=Decimal("1"),
        vat_amount=Decimal("0.19"),
        gross=Decimal("1.19"),
    )
    assert len(_rate_rows(inv)) == 1 and "unreadable lines" in caplog.text


def test_order_invoice_mixed_rates_shipping_discount_exact():
    from apps.catalog.tests.factories import ProductFactory
    from apps.finance.services import invoice_from_order
    from apps.orders import services as order_services
    from apps.orders.models import Order

    food = ProductFactory(base_price=Decimal("10.70"), stock_quantity=9, vat_rate=Decimal("7"))
    drink = ProductFactory(base_price=Decimal("11.90"), stock_quantity=9, vat_rate=Decimal("19"))
    order = order_services.create_order(items=[(food, 3), (drink, 1)], name="M", email="m@t.de")
    Order.objects.filter(pk=order.pk).update(
        discount_cents=333, shipping_cents=495, fulfillment=Order.FULFILLMENT_DELIVERY
    )
    order.refresh_from_db()
    inv = invoice_from_order(order)
    # 3 × 10,70 + 11,90 − 3,33 + 4,95 (update() не пересчитывает сохранённый total)
    assert inv.gross == Decimal("45.62")
    from apps.orders.totals import order_totals

    rows = {r["rate"]: r for r in order_totals(order)["rows"]}
    from apps.finance.totals import rate_groups as groups

    for rate, net, vat, gross in groups(inv.lines, inv.vat_rate, basis="gross"):
        assert (net, vat, gross) == (rows[rate]["net"], rows[rate]["vat"], rows[rate]["gross"])
    rates = {Decimal(ln["vat_rate"]) for ln in inv.lines if "Lieferung" in ln["text"]}
    assert rates == {Decimal("19")}
