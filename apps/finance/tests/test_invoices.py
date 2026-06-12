"""Track D / D4b: Rechnung — последовательная нумерация без дыр, §19,
иммутабельность issued, сторно с сохранением номера, PDF."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.fsm import IllegalTransition
from apps.finance import views
from apps.finance.models import Invoice
from apps.finance.pdf import build_invoice_pdf
from apps.finance.services import compute_totals, issue_invoice
from apps.finance.state_machine import InvoiceSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _draft(**kwargs):
    kwargs.setdefault("lines", [{"text": "Brot", "qty": 2, "unit_price": "3.50"}])
    kwargs.setdefault("net", Decimal("7.00"))
    kwargs.setdefault("vat_amount", Decimal("1.33"))
    kwargs.setdefault("gross", Decimal("8.33"))
    return Invoice.objects.create(**kwargs)


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/finance/rechnungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw")
    return request


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- суммы и §19 -------------------------------------------------------------------


def test_compute_totals_and_small_business():
    lines = [
        {"text": "A", "qty": 2, "unit_price": "3.50"},
        {"text": "B", "qty": 1, "unit_price": "10.00"},
    ]
    net, vat, gross = compute_totals(lines, Decimal("19.00"))
    assert (net, vat, gross) == (Decimal("17.00"), Decimal("3.23"), Decimal("20.23"))
    net, vat, gross = compute_totals(lines, Decimal("19.00"), small_business=True)
    assert vat == Decimal("0.00") and gross == net  # §19 — без НДС


# --- нумерация ----------------------------------------------------------------------


def test_sequential_numbering_without_gaps():
    first, second, third = _draft(), _draft(), _draft()
    deleted_draft = _draft()
    deleted_draft.delete()  # удалённый черновик дыру не оставляет (номера нет)

    assert issue_invoice(first).number == 1
    assert issue_invoice(second).number == 2
    # сторно сохраняет номер; следующий счёт продолжает последовательность
    InvoiceSM().apply(second, "cancelled")
    second.refresh_from_db()
    assert second.number == 2 and second.status == "cancelled"
    assert issue_invoice(third).number == 3
    assert first.number_display == "RE-00001"


# --- FSM и иммутабельность ----------------------------------------------------------


def test_sm_paths_and_immutability():
    invoice = issue_invoice(_draft())
    with pytest.raises(IllegalTransition):
        InvoiceSM().apply(_draft(), "paid")  # draft → paid запрещён
    invoice = InvoiceSM().apply(invoice, "paid")
    assert invoice.status == "paid"
    assert not invoice.is_editable

    # вьюха: удалить можно только черновик
    response = views.invoice_detail(_req("post", {"action": "delete"}), pk=invoice.pk)
    assert response.status_code == 302
    assert Invoice.objects.filter(pk=invoice.pk).exists()  # issued/paid не удаляется


# --- вьюхи и PDF --------------------------------------------------------------------


def test_create_draft_via_view_small_business():
    tenant = TenantFactory.build(small_business=True)
    response = views.invoices(
        _req(
            "post",
            {
                "recipient": "Max Mustermann\nHauptstr. 1",
                "vat_rate": "19.00",  # игнорируется при §19
                "line_text_1": "Beratung",
                "line_qty_1": "2",
                "line_price_1": "50,00",
                "note": "Danke!",
            },
            tenant=tenant,
        )
    )
    assert response.status_code == 302
    invoice = Invoice.objects.get()
    assert invoice.status == "draft" and invoice.number is None
    assert invoice.net == Decimal("100.00")
    assert invoice.vat_amount == Decimal("0.00") and invoice.gross == Decimal("100.00")


def test_invoice_pdf_renders():
    tenant = TenantFactory.build(small_business=True, vat_id="DE123456789")
    invoice = issue_invoice(_draft(recipient="Max Mustermann"))
    pdf = build_invoice_pdf(invoice, tenant)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000

    InvoiceSM().apply(invoice, "cancelled")
    invoice.refresh_from_db()
    assert build_invoice_pdf(invoice, tenant).startswith(b"%PDF")  # сторно-водяной знак

    response = views.invoice_pdf(_req(tenant=tenant), pk=invoice.pk)
    assert response["Content-Type"] == "application/pdf"
    assert "RE-00001" in response["Content-Disposition"]
