"""KA-12 E10 батч 2: ни один список кабинета не обрезается молча.

План — `docs/ka-12-w5-e10-lists-plan-2026-10-26.md`. Каждый замок кладёт больше строк, чем
помещается на страницу (50), и проверяет, что владелец видит итог и может пролистать дальше.
"""

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, tenant=None):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    n = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"o-{n}", password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    request.user = user
    request.tenant = tenant or TenantFactory(slug=f"e10l{next(_N)}", name="E10")
    return request


def test_bank_unmatched_rows_are_paged_not_cut():
    from apps.finance import views
    from apps.finance.models import BankTransaction

    BankTransaction.objects.bulk_create(
        BankTransaction(
            date=date(2026, 1, 1) + timedelta(days=i),
            amount=Decimal("10.00"),
            purpose=f"Zahlung {i}",
            import_hash=f"h{i:030d}",
        )
        for i in range(120)
    )
    body = views.bank_import(_req("/dashboard/finance/bank/")).content.decode()
    assert "1–50" in body and "120" in body
    last = views.bank_import(_req("/dashboard/finance/bank/?seite=3")).content.decode()
    assert "Zahlung 0" in last  # самая старая — на последней странице, а не потеряна


def test_open_bills_are_paged_with_own_param():
    from apps.finance import views
    from apps.finance.expenses import ExpenseEntry

    for i in range(60):
        ExpenseEntry.objects.create(
            source="manual",
            amount=Decimal("5"),
            category="fees",
            due_date=date(2026, 1, 1) + timedelta(days=i),
            note=f"Rechnung-{i:02d}",
        )
    body = views.expenses(_req("/dashboard/finance/ausgaben/")).content.decode()
    assert "?offen=2" in body
    second = views.expenses(_req("/dashboard/finance/ausgaben/?offen=2")).content.decode()
    assert "Rechnung-59" in second


def test_auftragsbuch_counts_all_orders_without_slot():
    from apps.crm.models import Customer
    from apps.orders.models import Order
    from apps.orders.views import auftragsbuch_context

    c = Customer.objects.create(name="K", email=f"k{next(_N)}@test.de")
    for _ in range(55):
        Order.objects.create(customer=c, reference_code=f"AB{next(_N):06d}", total=Decimal("1.00"))
    ctx = auftragsbuch_context(_req("/dashboard/verkaeufe/"))
    assert len(ctx["ab_ohne"]) == 50
    assert ctx["ab_ohne_total"] == 55


def test_promotion_list_is_paged():
    from apps.promotions import views
    from apps.promotions.models import Promotion

    for i in range(55):
        Promotion.objects.create(title={"de": f"Deal {i}"}, status="active")
    body = views.promotion_list(_req("/promotions/")).content.decode()
    assert "1–50" in body and "55" in body


def test_stock_csv_exports_all_movements():
    from apps.catalog.tests.factories import ProductFactory
    from apps.inventory.models import StockMovement
    from apps.inventory.views import _export_csv

    p = ProductFactory()
    StockMovement.objects.bulk_create(
        StockMovement(product=p, kind="adjust", delta=1) for _ in range(5003)
    )
    rows = _export_csv().content.decode().strip().splitlines()
    assert len(rows) == 5003 + 1  # + заголовок


def test_checkins_are_paged():
    from apps.crm.models import Customer
    from apps.stays import views
    from apps.stays.models import GuestRegistration, StayBooking, StayUnit

    unit = StayUnit.objects.create(name="Zimmer", price_cents=8000)
    c = Customer.objects.create(name="G", email=f"g{next(_N)}@test.de")
    today = timezone.localdate()
    for i in range(55):
        b = StayBooking.objects.create(
            unit=unit,
            customer=c,
            arrival=today + timedelta(days=i * 3),
            departure=today + timedelta(days=i * 3 + 1),
            reference_code=f"S{next(_N):06d}",
        )
        GuestRegistration.objects.create(
            booking=b,
            last_name=f"Gast{i:02d}",
            first_name="A",
            signed_name="A",
            signed_at=timezone.now(),
        )
    body = views.checkins(_req("/dashboard/stays/checkins/")).content.decode()
    assert "1–50" in body and "55" in body
