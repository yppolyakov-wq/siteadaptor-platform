"""KA-12 B2-8d (8d-1): даты поступления денег заявки → Mindest-Ist / Ist среза УСт.

Строки фолио заявки только датируют деньги; деньги заявки по-прежнему читаются
через `prepaid_cents` (заявка не в `FOLIO_KINDS`)."""

from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core import folio, money_contract
from apps.core.models import DealPayment
from apps.finance import ustva
from apps.finance.expenses import ExpenseEntry
from apps.finance.models import RevenueEntry
from apps.finance.services import issue_invoice
from apps.finance.state_machine import InvoiceSM
from apps.jobs import services as job_services

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(small_business=False, invoice_terms_days=14)
MAR = (date(2026, 3, 1), date(2026, 3, 31))
APR = (date(2026, 4, 1), date(2026, 4, 30))


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _at(day):
    return timezone.make_aware(datetime.combine(day, time(12)))


def _job(deposit=5000):
    job = job_services.create_job(title="Bad", name="Kunde")
    job_services.set_lines(
        job, [{"text": "Arbeit", "qty": 1, "unit_price": "100.00"}], vat_rate=Decimal("19")
    )
    job.refresh_from_db()
    job.status = "accepted"
    job.deposit_cents = deposit
    job.save()
    return job


def _date_rows(job, day):
    DealPayment.objects.filter(deal_kind="job", deal_id=job.pk).update(created_at=_at(day))


def _invoice(job, day):
    job.refresh_from_db()
    inv = job_services.quote_to_invoice(job)
    issue_invoice(inv, tenant=TENANT)
    RevenueEntry.objects.filter(source="job").update(date=day)
    inv.refresh_from_db()
    return inv


def _slice(regime, period):
    von, bis = period
    entries = RevenueEntry.objects.filter(date__gte=von, date__lte=bis)
    expenses = ExpenseEntry.objects.filter(date__gte=von, date__lte=bis)
    tenant = SimpleNamespace(tax_regime=regime, small_business=False)
    return ustva.ustva_slice(tenant, von, bis, entries, expenses)


def _vat(gross):
    return (Decimal(gross) * 19 / 119).quantize(Decimal("0.01"))


def test_soll_job_deposit_taxed_on_receipt_and_deducted_at_invoice():
    job = _job()
    money_contract.settle_payment("job", job, source="bank", deposit_only=True)
    _date_rows(job, date(2026, 3, 15))
    _invoice(job, date(2026, 4, 10))
    mar, apr = _slice("soll", MAR), _slice("soll", APR)
    assert mar["ust"] == _vat("50.00")
    assert mar["ust"] + apr["ust"] == _vat(job.gross)


def test_webhook_deposit_is_dated_once():
    from django.db import connection

    from apps.jobs.payments import mark_deposit_paid

    job = _job()
    for _ in range(2):
        mark_deposit_paid(
            tenant_schema=connection.schema_name, job_id=str(job.id), payment_intent="pi_j"
        )
    rows = DealPayment.objects.filter(deal_kind="job", deal_id=job.pk)
    assert rows.count() == 1 and rows[0].amount_cents == 5000 and rows[0].method == "stripe"


def test_paid_advance_invoice_dates_job_deposit_and_drops_note(settings):
    from apps.finance import advance

    settings.ADVANCE_INVOICES_ENABLED = True
    job = _job()
    adv = advance.create_advance_invoice("job", job, TENANT)
    InvoiceSM().apply(adv, "paid", source="bank")
    assert DealPayment.objects.filter(deal_kind="job", deal_id=job.pk, amount_cents=5000).exists()
    today = timezone.localdate()
    res = _slice("soll", (today, today))
    assert res["ust"] == _vat("50.00")
    assert not any("Aufträgen" in str(n) for n in res["notes"])


def test_ist_deposit_then_balance_by_payment_dates():
    job = _job()
    money_contract.settle_payment("job", job, source="bank", deposit_only=True)
    _date_rows(job, date(2026, 3, 15))
    inv = _invoice(job, date(2026, 4, 10))
    InvoiceSM().apply(inv, "paid", source="bank")
    rows = list(DealPayment.objects.filter(deal_kind="job", deal_id=job.pk).order_by("created_at"))
    assert [r.purpose for r in rows] == ["deposit", "balance"]
    DealPayment.objects.filter(pk=rows[1].pk).update(created_at=_at(date(2026, 4, 20)))
    mar, apr = _slice("ist", MAR), _slice("ist", APR)
    assert mar["ust"] == _vat("50.00")
    assert mar["ust"] + apr["ust"] == _vat(job.gross)


def test_job_money_is_unchanged_by_dated_rows():
    """Охранный замок: заявка не в FOLIO_KINDS — её деньги книга не читает."""
    assert "job" not in folio.FOLIO_KINDS
    job = _job()
    before = money_contract.due("job", job)
    DealPayment.objects.create(
        deal_kind="job", deal_id=job.pk, purpose="full", amount_cents=99999, source="manual"
    )
    folio.forget(job)
    assert money_contract.due("job", job) == before


def test_legacy_paid_job_gets_no_balance_row():
    job = _job()
    type(job).objects.filter(pk=job.pk).update(payment_state="paid")
    job.refresh_from_db()
    money_contract.record_job_balance(job, source="invoice")
    assert not DealPayment.objects.filter(deal_kind="job", deal_id=job.pk).exists()


def test_full_manual_payment_dates_payable_not_more():
    job = _job(deposit=0)
    money_contract.settle_payment("job", job, source="manual")
    row = DealPayment.objects.get(deal_kind="job", deal_id=job.pk)
    assert row.amount_cents == int(job.payable_gross * 100) and row.purpose == "full"
    folio.record_job_payment(job, amount_cents=500, purpose="balance")
    assert DealPayment.objects.filter(deal_kind="job", deal_id=job.pk).count() == 1
