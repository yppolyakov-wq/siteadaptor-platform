"""KA-12 B2-8c: вычет Anzahlungsrechnung в итоговом счёте (§ 14 Abs. 5 S. 2 UStG).

Оплаченная предоплата вычитается по ставкам строками `InvoiceDeduction`, депозит
в «к оплате» считается один раз; неоплаченная сторнируется (Q-2) — при итоговом
счёте и при отмене сделки."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core.fsm import IllegalTransition
from apps.finance import advance
from apps.finance.models import Invoice, InvoiceDeduction
from apps.finance.services import invoice_from_stay, issue_invoice
from apps.finance.state_machine import InvoiceSM

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(small_business=False, invoice_terms_days=14)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.ADVANCE_INVOICES_ENABLED = True


def _stay(deposit=5000):
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=10)
    s = services.book_stay(unit, arrival=arrival, departure=arrival + timedelta(days=2), name="G")
    s.deposit_cents = deposit
    s.save(update_fields=["deposit_cents"])
    return s


def _final(stay):
    stay.refresh_from_db()
    inv = invoice_from_stay(stay, tenant=TENANT)
    Invoice.objects.filter(pk=inv.pk).update(deal_kind="stay", deal_id=stay.reference_code)
    inv.refresh_from_db()
    issue_invoice(inv, tenant=TENANT)
    inv.refresh_from_db()
    return inv


def _paid_advance(stay):
    adv = advance.create_advance_invoice("stay", stay, TENANT)
    InvoiceSM().apply(adv, "paid", source="bank")
    adv.refresh_from_db()
    return adv


def test_final_deducts_paid_advance_and_counts_deposit_once():
    stay = _stay()
    adv = _paid_advance(stay)
    final = _final(stay)
    rows = list(InvoiceDeduction.objects.filter(final=final))
    assert rows and sum(r.gross for r in rows) == adv.gross
    assert sum(r.net for r in rows) == adv.net
    assert final.open_amount == final.gross - Decimal("50.00")
    adv.refresh_from_db()
    assert adv.status == "paid"


def test_unpaid_advance_is_cancelled_by_final_invoice():
    stay = _stay()
    adv = advance.create_advance_invoice("stay", stay, TENANT)
    final = _final(stay)
    adv.refresh_from_db()
    assert adv.status == "cancelled"
    assert Invoice.objects.filter(cancels=adv, kind="storno").exists()
    assert not InvoiceDeduction.objects.filter(final=final).exists()


def test_received_deposit_is_synced_not_cancelled_at_final():
    stay = _stay()
    adv = advance.create_advance_invoice("stay", stay, TENANT)
    type(stay).objects.filter(pk=stay.pk).update(payment_state="deposit")  # синк не успел
    final = _final(stay)
    adv.refresh_from_db()
    assert adv.status == "paid"
    assert InvoiceDeduction.objects.filter(final=final, advance=adv).exists()


def test_deduction_is_idempotent():
    stay = _stay()
    _paid_advance(stay)
    final = _final(stay)
    count = InvoiceDeduction.objects.filter(final=final).count()
    advance.settle_for_final(final)
    assert InvoiceDeduction.objects.filter(final=final).count() == count


def test_deal_cancel_cancels_unpaid_advance_keeps_paid():
    from apps.stays.state_machine import StayBookingSM

    stay = _stay()
    adv = advance.create_advance_invoice("stay", stay, TENANT)
    StayBookingSM().apply(stay, "cancelled")
    adv.refresh_from_db()
    assert adv.status == "cancelled"

    other = _stay()
    paid = _paid_advance(other)
    other.refresh_from_db()
    StayBookingSM().apply(other, "cancelled")
    paid.refresh_from_db()
    assert paid.status == "paid"


def test_job_cancel_cancels_unpaid_advance():
    from apps.jobs import services as job_services
    from apps.jobs.state_machine import JobSM

    job = job_services.create_job(title="Bad", name="Kunde")
    job.status, job.deposit_cents = "accepted", 5000
    job.save()
    adv = advance.create_advance_invoice("job", job, TENANT)
    JobSM().apply(job, "cancelled")
    adv.refresh_from_db()
    assert adv.status == "cancelled"


def test_final_storno_frees_advance_and_new_final_deducts_again():
    stay = _stay()
    adv = _paid_advance(stay)
    final = _final(stay)
    with pytest.raises(IllegalTransition):
        InvoiceSM().apply(adv, "cancelled")
    InvoiceSM().apply(final, "cancelled")
    assert InvoiceDeduction.objects.filter(final=final).exists()  # снимок остаётся
    second = _final(stay)
    assert InvoiceDeduction.objects.filter(final=second, advance=adv).exists()


def test_deduction_rows_split_by_rate_and_hit_gross():
    adv = Invoice(
        kind="advance",
        vat_rate=Decimal("19"),
        gross=Decimal("100.00"),
        lines=[
            {"text": "a", "qty": 1, "unit_price": "46.73", "vat_rate": "7"},
            {"text": "b", "qty": 1, "unit_price": "42.02", "vat_rate": "19"},
        ],
    )
    rows = advance.deduction_rows(adv)
    assert {r[0] for r in rows} == {Decimal("7"), Decimal("19")}
    assert sum(r[3] for r in rows) == Decimal("100.00")


def test_final_pdf_renders_with_deduction():
    from apps.finance.pdf import build_invoice_pdf
    from apps.tenants.tests.factories import TenantFactory

    stay = _stay()
    _paid_advance(stay)
    final = _final(stay)
    assert build_invoice_pdf(final, TenantFactory(schema_name="public"))[:4] == b"%PDF"


def test_deduction_runs_with_flag_off(settings):
    stay = _stay()
    _paid_advance(stay)
    settings.ADVANCE_INVOICES_ENABLED = False
    final = _final(stay)
    assert InvoiceDeduction.objects.filter(final=final).exists()


def test_mixed_rate_advance_deduction_has_no_drift(caplog):
    adv = Invoice(
        kind="advance",
        vat_rate=Decimal("19"),
        lines=[
            {"text": "a", "qty": 1, "unit_price": "28.04", "vat_rate": "7"},
            {"text": "b", "qty": 1, "unit_price": "16.81", "vat_rate": "19"},
        ],
    )
    from apps.finance.services import compute_totals

    adv.net, adv.vat_amount, adv.gross = compute_totals(adv.lines, Decimal("19"))
    rows = advance.deduction_rows(adv)
    assert sum(r[1] for r in rows) == adv.net and sum(r[2] for r in rows) == adv.vat_amount
    assert "drift" not in caplog.text


def test_cancelled_deal_advance_is_not_an_open_item(monkeypatch):
    from apps.finance import bank
    from apps.tenants.tests.factories import TenantFactory

    stay = _stay()
    adv = advance.create_advance_invoice("stay", stay, TENANT)
    monkeypatch.setattr(advance, "cancel_unpaid_for_deal", lambda *a, **k: None)  # сторно «упало»
    type(stay).objects.filter(pk=stay.pk).update(status="cancelled")
    items = bank.open_items(TenantFactory(schema_name="public"))
    assert not [i for i in items if i["obj"].pk == adv.pk]


def test_clamp_keeps_certificate_when_deposit_changed(monkeypatch):
    from apps.finance import services

    stay = _stay()
    adv = _paid_advance(stay)
    type(stay).objects.filter(pk=stay.pk).update(deposit_cents=1000)
    monkeypatch.setattr(services, "certificate_cents", lambda deal: 700)
    final = _final(stay)
    assert final.prepaid_cents >= int(adv.gross * 100) + 700
