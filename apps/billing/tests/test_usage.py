"""P2.5-fee: Nutzungsgebühr (вариант B) — оборот за период + строка в Stripe-счёт."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection

from apps.billing import services, usage
from apps.billing.models import UsageFeeRecord
from apps.finance.models import RevenueEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_period_bounds_and_previous():
    assert usage.period_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert usage.period_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert usage.previous_period(date(2026, 3, 5)) == "2026-02"
    assert usage.previous_period(date(2026, 1, 10)) == "2025-12"


def _revenue(source, amount, d):
    return RevenueEntry.objects.create(source=source, amount=Decimal(amount), date=d)


def _tenant(**kw):
    return TenantFactory(schema_name=connection.schema_name, business_type="cafe", **kw)


def test_tenant_gmv_excludes_manual_and_other_periods():
    tenant = _tenant()
    _revenue("order", "100.00", date(2026, 2, 10))
    _revenue("reservation", "50.00", date(2026, 2, 20))
    _revenue("manual", "999.00", date(2026, 2, 15))  # ручное — не «vermittelt»
    _revenue("order", "30.00", date(2026, 3, 1))  # другой период
    assert usage.tenant_gmv_cents(tenant, "2026-02") == 15000  # 150,00 €


def test_bill_tenant_zero_percent_skips(settings, monkeypatch):
    settings.BILLING_APPLICATION_FEE_PERCENT = {}  # 0 % → ничего не начисляем
    tenant = _tenant(stripe_customer_id="cus_1")
    _revenue("order", "100.00", date(2026, 2, 10))
    called = {"x": False}
    monkeypatch.setattr(
        services, "create_usage_invoice_item", lambda t, **kw: called.__setitem__("x", True) or "ii"
    )
    assert usage.bill_tenant(tenant, "2026-02") == "zero"
    assert called["x"] is False
    assert not UsageFeeRecord.objects.filter(tenant=tenant).exists()


def test_bill_tenant_creates_invoice_item_and_record(settings, monkeypatch):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"cafe": "5"}
    tenant = _tenant(stripe_customer_id="cus_1")
    _revenue("order", "200.00", date(2026, 2, 10))  # 20000c → 5 % = 1000c
    captured = {}
    monkeypatch.setattr(
        services, "create_usage_invoice_item", lambda t, **kw: captured.update(kw) or "ii_1"
    )
    assert usage.bill_tenant(tenant, "2026-02") == "billed"
    assert captured["amount_cents"] == 1000
    rec = UsageFeeRecord.objects.get(tenant=tenant, period="2026-02")
    assert rec.fee_cents == 1000
    assert rec.gmv_cents == 20000
    assert rec.stripe_invoice_item_id == "ii_1"
    # идемпотентно — повтор не дублирует начисление
    assert usage.bill_tenant(tenant, "2026-02") == "already"


def test_bill_tenant_without_customer(settings):
    settings.BILLING_APPLICATION_FEE_PERCENT = {"cafe": "5"}
    tenant = _tenant(stripe_customer_id="")
    _revenue("order", "200.00", date(2026, 2, 10))
    assert usage.bill_tenant(tenant, "2026-02") == "no_customer"
    assert not UsageFeeRecord.objects.filter(tenant=tenant).exists()
