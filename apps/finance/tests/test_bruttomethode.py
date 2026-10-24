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
