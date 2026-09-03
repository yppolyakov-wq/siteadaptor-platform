"""SH-23b: счёт юрлицу выпускается автоматически (решение владельца Р-1),
несёт срок оплаты (Р-2) и уходит клиенту письмом с PDF.

План — `docs/order-feedback-plan-2026-09-03.md` §6.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.finance.models import Invoice
from apps.finance.services import issue_invoice, issue_invoice_for_deal
from apps.notifications.models import Notification
from apps.orders import services as order_services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    return TenantFactory(**kw)


def _order(tenant, email="firma@example.de"):
    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("10.00"), stock_quantity=10
    )
    return order_services.create_order(
        items=[(product, 2)],
        name="Muster GmbH",
        email=email,
        customer_type="company",
        billing_company="Muster GmbH",
        payment_method="invoice",
    )


def test_issue_sets_the_due_date_from_the_business_setting():
    """Р-2: срок по умолчанию 14 дней, настройка бизнеса сильнее."""
    tenant = _tenant(invoice_terms_days=30)
    invoice = Invoice.objects.create(recipient="Muster GmbH", lines=[], gross=Decimal("20.00"))
    issue_invoice(invoice, tenant=tenant)
    invoice.refresh_from_db()
    assert invoice.payment_terms_days == 30
    assert invoice.due_date == (invoice.issued_at + timedelta(days=30)).date()


def test_issue_keeps_an_explicit_due_date():
    tenant = _tenant(schema_name="sh23i", slug="sh23i")
    due = timezone.localdate() + timedelta(days=3)
    invoice = Invoice.objects.create(recipient="X", lines=[], gross=Decimal("5.00"), due_date=due)
    issue_invoice(invoice, tenant=tenant)
    invoice.refresh_from_db()
    assert invoice.due_date == due


def test_auto_invoice_is_issued_once_and_mailed_with_pdf():
    tenant = _tenant(schema_name="sh23j", slug="sh23j", invoice_b2b_enabled=True)
    order = _order(tenant)
    invoice = issue_invoice_for_deal("order", order, tenant)
    assert invoice is not None
    assert invoice.status == "issued" and invoice.number  # Р-1: сразу выставлен
    assert invoice.deal_kind == "order" and invoice.deal_id == order.reference_code
    assert invoice.due_date is not None
    note = Notification.objects.filter(type="invoice_issued").first()
    assert note is not None and note.recipient == "firma@example.de"
    attachments = note.payload.get("attachments") or []
    assert attachments and attachments[0]["mime"] == "application/pdf"
    invoice.refresh_from_db()
    assert invoice.sent_at is not None

    # идемпотентность: повторный вызов не плодит второй счёт
    again = issue_invoice_for_deal("order", order, tenant)
    assert again.pk == invoice.pk
    assert Invoice.objects.count() == 1


def test_auto_invoice_without_customer_email_still_issues():
    """Письмо слать некуда — счёт всё равно выставлен (владелец отдаст лично)."""
    tenant = _tenant(schema_name="sh23k", slug="sh23k", invoice_b2b_enabled=True)
    order = _order(tenant, email="")
    invoice = issue_invoice_for_deal("order", order, tenant)
    assert invoice.status == "issued"
    assert not Notification.objects.filter(type="invoice_issued").exists()


def test_open_items_carry_the_due_date():
    from apps.finance import bank as bank_mod

    tenant = _tenant(schema_name="sh23l", slug="sh23l", invoice_b2b_enabled=True)
    order = _order(tenant)
    order.payment_due_at = timezone.now() + timedelta(days=14)
    order.save(update_fields=["payment_due_at"])
    invoice = issue_invoice_for_deal("order", order, tenant)
    rows = bank_mod.open_items(tenant)
    by_kind = {r["kind"]: r for r in rows}
    assert by_kind["order"]["due_date"] == order.payment_due_at.date()
    assert by_kind["invoice"]["due_date"] == invoice.due_date
