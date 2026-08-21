"""MX-1: расходы как раздел ERP — приёмка закупки пишет расход, ручной ввод,
экран Ausgaben + Ergebnis. План — docs/mx-execution-plan-2026-08-21.md §MX-1."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.finance.expenses import ExpenseEntry
from apps.finance.models import RevenueEntry
from apps.finance.views import ergebnis, expenses
from apps.inventory import purchasing
from apps.inventory.models import Bestellung

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, path="/dashboard/finance/ausgaben/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    n = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{n}", email=f"o-{n}@test.de", password="pw12345678"
    )
    return request


def test_po_receipt_writes_expense_idempotently():
    """Приёмка строки закупки → ExpenseEntry(source=purchase); частичные приёмки —
    отдельные записи; SOURCE_PURCHASE перестал быть мёртвым."""
    po = purchasing.create_po()
    product = ProductFactory(cost_price=Decimal("2.00"), stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=10)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)

    purchasing.receive_po_line(line, qty=4)
    line.refresh_from_db()
    entries = ExpenseEntry.objects.filter(source=ExpenseEntry.SOURCE_PURCHASE)
    assert entries.count() == 1
    first = entries.get()
    assert first.amount == Decimal("8.00") and first.category == ExpenseEntry.CATEGORY_GOODS

    purchasing.receive_po_line(line, qty=6)  # добор
    assert ExpenseEntry.objects.filter(source=ExpenseEntry.SOURCE_PURCHASE).count() == 2
    total = sum(e.amount for e in ExpenseEntry.objects.filter(source=ExpenseEntry.SOURCE_PURCHASE))
    assert total == Decimal("20.00")


def test_po_receipt_zero_cost_writes_nothing():
    po = purchasing.create_po()
    product = ProductFactory(cost_price=None, stock_quantity=0)
    line = purchasing.add_po_line(po, product=product, qty=3)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(line)
    assert not ExpenseEntry.objects.filter(source=ExpenseEntry.SOURCE_PURCHASE).exists()


def test_manual_expense_add_and_delete_only_manual():
    resp = expenses(_req("post", {"amount": "12,50", "category": "fees", "note": "Gema"}))
    assert resp.status_code == 302
    e = ExpenseEntry.objects.get(source=ExpenseEntry.SOURCE_MANUAL)
    assert e.amount == Decimal("12.50") and e.category == "fees"

    auto = ExpenseEntry.objects.create(
        source=ExpenseEntry.SOURCE_PURCHASE, source_ref="x:1", amount=Decimal("5")
    )
    expenses(_req("post", {"action": "delete", "id": str(auto.pk)}))
    assert ExpenseEntry.objects.filter(pk=auto.pk).exists()  # событийную не удалить
    expenses(_req("post", {"action": "delete", "id": str(e.pk)}))
    assert not ExpenseEntry.objects.filter(pk=e.pk).exists()


def test_expenses_screen_filters_by_category():
    ExpenseEntry.objects.create(source="manual", amount=Decimal("10"), category="fees")
    ExpenseEntry.objects.create(source="manual", amount=Decimal("7"), category="goods")
    resp = expenses(_req("get", path="/dashboard/finance/ausgaben/?kategorie=fees"))
    body = resp.content.decode()
    assert "10,00" in body or "10.00" in body
    assert "−17" not in body  # сумма только по категории


def test_ergebnis_revenue_minus_expenses():
    RevenueEntry.objects.create(source="manual", amount=Decimal("100"), date=date.today())
    ExpenseEntry.objects.create(source="manual", amount=Decimal("30"), date=date.today())
    resp = ergebnis(_req("get", path="/dashboard/finance/ergebnis/"))
    body = resp.content.decode()
    assert "70,00" in body or "70.00" in body
