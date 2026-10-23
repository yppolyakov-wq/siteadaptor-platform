"""KA-H5 (G1): счёт из сметы заявки = согласованная сумма, без 404 без «Finanzen».

Раньше `quote_to_invoice` брал gross сметы без скидки владельца (DC-5) — в черновике
счёта сумма больше той, что принял клиент; кнопка «Rechnung» при выключенном модуле
финансов (дефолт кейтеринга) вела на 404, хотя статус уже «invoiced».
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.jobs import services, views
from apps.jobs.state_machine import JobSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(f"j-{o}", f"j-{o}@t.de", "pw12345678")
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _done_job(lines, discount_cents=0, voucher_code="", voucher_paid_cents=0, title="Feier"):
    job = services.create_job(title=title, name="Kunde")
    services.set_lines(job, lines)
    job.refresh_from_db()
    job.discount_cents = discount_cents
    job.voucher_code = voucher_code
    job.voucher_paid_cents = voucher_paid_cents
    job.save(update_fields=["discount_cents", "voucher_code", "voucher_paid_cents"])
    for dst in ("quoted", "accepted", "done"):
        JobSM().apply(job, dst)
    return job


MIXED = [
    {"text": "Buffet", "qty": 1, "unit_price": "100.00", "vat_rate": "7"},
    {"text": "Getränke", "qty": 1, "unit_price": "50.00", "vat_rate": "19"},
]


def test_owner_discount_becomes_negative_lines_and_gross_equals_payable():
    job = _done_job(MIXED, discount_cents=1000)  # 10 € Rabatt владельца
    invoice = services.quote_to_invoice(job)
    rabatt = [ln for ln in invoice.lines if Decimal(ln["unit_price"]) < 0]
    assert len(rabatt) == 2 and {Decimal(ln["vat_rate"]) for ln in rabatt} == {
        Decimal("7"),
        Decimal("19"),
    }
    assert invoice.gross == job.payable_gross
    assert invoice.deal_kind == "job" and invoice.deal_id == job.reference_code


@pytest.mark.parametrize("cents", [1, 333, 9999])
def test_owner_discount_rounding_exact(cents):
    job = _done_job(MIXED, discount_cents=cents)
    invoice = services.quote_to_invoice(job)
    assert invoice.gross == job.payable_gross


def test_wertgutschein_keeps_gross_and_notes_payment():
    from apps.loyalty.models import Voucher

    Voucher.objects.create(code="WERT50", label="Gutschein", balance_cents=5000)
    job = _done_job(MIXED, discount_cents=2000, voucher_code="WERT50", voucher_paid_cents=2000)
    invoice = services.quote_to_invoice(job)
    assert invoice.gross == job.gross
    assert not [ln for ln in invoice.lines if Decimal(ln["unit_price"]) < 0]
    assert "WERT50" in invoice.note


def test_paid_deposit_is_note_not_vat_line():
    job = _done_job(MIXED)
    job.deposit_cents = 5000
    job.payment_state = job.PAYMENT_PAID
    job.save(update_fields=["deposit_cents", "payment_state"])
    invoice = services.quote_to_invoice(job)
    assert invoice.gross == job.gross and invoice.vat_amount == job.vat_amount
    assert "50,00" in invoice.note or "50.00" in invoice.note


def test_invoice_without_finance_redirects_to_job_and_pdf_reachable():
    job = _done_job(MIXED)
    tenant = TenantFactory.build(disabled_modules=["finance"])
    resp = views.job_detail(_req(data={"action": "invoice"}, tenant=tenant), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "invoiced" and job.invoice_id
    assert resp.status_code == 302 and "/dashboard/finance/" not in resp.url
    pdf = views.job_invoice_pdf(_req("get", tenant=tenant), pk=job.pk)
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    body = views.job_detail(_req("get", tenant=tenant), pk=job.pk).content.decode()
    assert "rechnung.pdf" in body and "/dashboard/finance/rechnungen/" not in body


def test_voucher_plus_owner_discount_splits_payment_and_rabatt():
    """Ревью: сертификат 20 € + владелец поднял скидку до 30 € → 10 € Rabatt."""
    job = _done_job(MIXED, discount_cents=3000, voucher_code="WERT50", voucher_paid_cents=2000)
    invoice = services.quote_to_invoice(job)
    rabatt = sum(
        (Decimal(ln["unit_price"]) for ln in invoice.lines if Decimal(ln["unit_price"]) < 0),
        Decimal("0"),
    )
    assert rabatt < 0
    assert invoice.gross == job.gross - Decimal("10.00")
    assert "WERT50" in invoice.note and "20,00" in invoice.note


def test_owner_note_equal_to_voucher_code_is_still_rabatt():
    """DC-5 пишет заметку в voucher_code: совпадение с кодом сертификата ≠ оплата."""
    from apps.loyalty.models import Voucher

    Voucher.objects.create(code="SOMMER", label="Gutschein", balance_cents=5000)
    job = _done_job(MIXED, discount_cents=1000, voucher_code="SOMMER")
    job.accepted_at = None  # скидка владельца без принятия сертификата
    invoice = services.quote_to_invoice(job)
    assert invoice.gross == job.payable_gross


def test_long_title_does_not_cut_payment_note():
    job = _done_job(MIXED, title="X" * 200)
    job.deposit_cents = 5000
    job.payment_state = job.PAYMENT_PAID
    job.save(update_fields=["deposit_cents", "payment_state"])
    invoice = services.quote_to_invoice(job)
    assert len(invoice.note) <= 200 and ("50,00" in invoice.note or "50.00" in invoice.note)


def test_accepting_quote_with_value_voucher_records_payment(settings):
    from apps.jobs import public_views
    from apps.loyalty.models import Voucher

    Voucher.objects.create(code="WERT99", label="Gutschein", balance_cents=10000)
    job = services.create_job(title="Feier", name="Kunde")
    services.set_lines(job, MIXED)
    JobSM().apply(job, "quoted")
    job.refresh_from_db()
    req = RequestFactory().post("/x/", {"action": "accept", "voucher_code": "wert99"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build()
    public_views.angebot(req, token=job.public_token)
    job.refresh_from_db()
    assert job.discount_cents > 0 and job.voucher_paid_cents == job.discount_cents
