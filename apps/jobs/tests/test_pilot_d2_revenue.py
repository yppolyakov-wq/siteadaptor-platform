"""KA-D2 (решение владельца 2026-10-23): выручка заявки/мастерской — в журнал при
ВЫСТАВЛЕНИИ счёта (до этого её в журнале не было вовсе — `status_effects`: «job —
через invoice-флоу», флоу не писал). Сторно счёта — сторно-запись. Идемпотентно."""

import uuid
from decimal import Decimal

import pytest

from apps.finance.models import Invoice, RevenueEntry
from apps.finance.services import issue_invoice
from apps.finance.state_machine import InvoiceSM
from apps.jobs import services
from apps.jobs.state_machine import JobSM

pytestmark = pytest.mark.django_db


def _done_job(lines):
    job = services.create_job(title="Bad", name="Kunde", email=f"{uuid.uuid4().hex[:6]}@t.de")
    services.set_lines(job, lines)
    job.refresh_from_db()
    for dst in ("quoted", "accepted", "done"):
        JobSM().apply(job, dst)
    job.refresh_from_db()
    return job


def _entries(invoice):
    return RevenueEntry.objects.filter(source="job", source_ref__startswith=f"inv:{invoice.pk}:")


def test_issue_writes_job_revenue_once():
    invoice = services.quote_to_invoice(
        _done_job([{"text": "Arbeit", "qty": 2, "unit_price": "50.00"}])
    )
    assert not _entries(invoice).exists()  # черновик — не выручка
    issue_invoice(invoice)
    invoice.refresh_from_db()
    assert sum(e.amount for e in _entries(invoice)) == invoice.gross
    from apps.finance.services import journal_invoice_revenue

    journal_invoice_revenue(invoice)  # повтор хука — без дубля
    assert sum(e.amount for e in _entries(invoice)) == invoice.gross


def test_mixed_rates_split_per_rate():
    invoice = services.quote_to_invoice(
        _done_job(
            [
                {"text": "Essen", "qty": 1, "unit_price": "100.00", "vat_rate": "7"},
                {"text": "Service", "qty": 1, "unit_price": "100.00", "vat_rate": "19"},
            ]
        )
    )
    issue_invoice(invoice)
    invoice.refresh_from_db()
    rates = {e.vat_rate for e in _entries(invoice)}
    assert rates == {Decimal("7.00"), Decimal("19.00")}
    assert sum(e.amount for e in _entries(invoice)) == invoice.gross


def test_cancel_reverses_journal():
    invoice = services.quote_to_invoice(
        _done_job([{"text": "Arbeit", "qty": 1, "unit_price": "80.00"}])
    )
    issue_invoice(invoice)
    invoice.refresh_from_db()
    InvoiceSM().apply(invoice, "cancelled")
    total = sum(
        e.amount
        for e in RevenueEntry.objects.filter(
            source="job", source_ref__contains=f"inv:{invoice.pk}:"
        )
    )
    assert total == 0


def test_non_job_invoice_untouched():
    invoice = Invoice.objects.create(recipient="X", lines=[], gross=Decimal("10.00"))
    issue_invoice(invoice)
    assert not RevenueEntry.objects.filter(source="job").exists()
