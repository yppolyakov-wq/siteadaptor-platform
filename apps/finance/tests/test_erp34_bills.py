"""ERP-3/4: Eingangsrechnung + Mahnwesen + UStVA-срез + DATEV расходов.

План docs/erp-wave-plan-2026-08-21.md.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.finance import views as finance_views
from apps.finance.expenses import ExpenseEntry
from apps.finance.models import Invoice
from apps.finance.services import issue_invoice, record_revenue
from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    from apps.tenants.models import Tenant

    existing = Tenant.objects.filter(schema_name="public").first()
    return existing or TenantFactory(schema_name="public")


def _req(method, path="/dashboard/finance/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    import uuid as _uuid

    request.user = get_user_model().objects.create_user(
        username=f"u-{_uuid.uuid4().hex[:8]}", email="o@t.de", password="pw12345678"
    )
    request.tenant = tenant or _tenant()
    return request


def test_manual_bill_with_due_date_is_open_then_paid():
    request = _req(
        "post",
        data={
            "amount": "119,00",
            "category": "goods",
            "vat_rate": "19.00",
            "due_date": (timezone.localdate() + timedelta(days=14)).isoformat(),
            "note": "Lieferant X",
        },
    )
    finance_views.expenses(request)
    e = ExpenseEntry.objects.get()
    assert e.vat_rate == Decimal("19.00")
    assert e.is_open and not e.is_overdue

    request = _req("post", data={"action": "mark_paid", "id": str(e.pk)})
    finance_views.expenses(request)
    e.refresh_from_db()
    assert e.paid_at is not None and not e.is_open


def test_expense_without_due_date_counts_as_paid_immediately():
    request = _req("post", data={"amount": "10,00", "category": "other"})
    finance_views.expenses(request)
    e = ExpenseEntry.objects.get()
    assert e.paid_at is not None and not e.is_open


def _issued_invoice(gross="100.00"):
    customer = Customer.objects.create(name="K", email="k@t.de")
    inv = Invoice.objects.create(
        customer=customer, gross=Decimal(gross), net=Decimal(gross), lines=[]
    )
    issue_invoice(inv)
    return inv


def test_mahnung_sends_email_levels_up_and_dedupes_same_day():
    tenant = _tenant()
    inv = _issued_invoice()
    request = _req("post", tenant=tenant)
    finance_views.invoice_mahnung(request, pk=inv.pk)
    inv.refresh_from_db()
    assert inv.mahn_level == 1 and inv.mahned_at == timezone.localdate()
    n = Notification.objects.get(type="invoice_mahnung")
    assert "Zahlungserinnerung" in n.subject

    # Второй POST — эскалация до Mahnung 2 (свой dedupe-ключ) → письмо уходит.
    request = _req("post", tenant=tenant)
    finance_views.invoice_mahnung(request, pk=inv.pk)
    inv.refresh_from_db()
    assert inv.mahn_level == 2
    assert Notification.objects.filter(type="invoice_mahnung").count() == 2
    # Кап уровня: дальше 3 не растёт, повтор уровня 3 в тот же день дедупится.
    finance_views.invoice_mahnung(_req("post", tenant=tenant), pk=inv.pk)
    finance_views.invoice_mahnung(_req("post", tenant=tenant), pk=inv.pk)
    inv.refresh_from_db()
    assert inv.mahn_level == 3
    assert Notification.objects.filter(type="invoice_mahnung").count() == 3


def test_ustva_slice_and_datev_expenses():
    record_revenue(source="manual", amount=Decimal("119.00"), vat_rate=Decimal("19.00"))
    ExpenseEntry.objects.create(
        source="manual", amount=Decimal("23.80"), vat_rate=Decimal("19.00"), category="goods"
    )
    request = _req("get", "/dashboard/finance/ergebnis/")
    body = finance_views.ergebnis(request).content.decode()
    assert "19,00" in body  # USt из 119 брутто
    assert "3,80" in body  # Vorsteuer из 23,80
    assert "15,20" in body  # Zahllast

    request = _req("get", "/dashboard/finance/ausgaben/datev.csv")
    csv_body = finance_views.expenses_export_datev(request).content.decode("cp1252")
    assert "3400" in csv_body and "23,80" in csv_body  # Wareneingang an Kasse
