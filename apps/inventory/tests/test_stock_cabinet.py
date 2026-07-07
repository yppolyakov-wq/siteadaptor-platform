"""U-D3.3: кабинет склада — приёмки/корректировки/инвентаризация/реконсиляция."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.inventory import services, views
from apps.inventory.models import StockMovement
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "chef"


def _req(method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/stock/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory.build(business_type="bakery")
    return req


def test_get_renders_overview_with_product():
    product = ProductFactory(stock_quantity=3)
    html = views.stock(_req()).content.decode()
    assert "Lager" in html
    assert str(product) in html


def test_receipt_increments_counter_and_logs_and_keeps_diff():
    product = ProductFactory(stock_quantity=2)  # legacy diff = 2 (counter 2, ledger 0)
    resp = views.stock(_req("post", {"action": "receipt", "product": str(product.id), "qty": "5"}))
    assert resp.status_code == 302
    product.refresh_from_db()
    assert product.stock_quantity == 7
    mv = StockMovement.objects.filter(product=product, kind="receipt")
    assert mv.count() == 1 and mv.first().delta == 5
    # приёмка двигает счётчик И леджер на +5 → разница (diff) неизменна
    assert services.reconciliation(product)["diff"] == 2


def test_adjustment_moves_counter_and_clamps():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "adjustment", "product": str(product.id), "delta": "-3"}))
    product.refresh_from_db()
    assert product.stock_quantity == 7
    assert StockMovement.objects.filter(product=product, kind="adjustment", delta=-3).count() == 1


def test_stocktake_sets_absolute_and_logs_difference():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "stocktake", "product": str(product.id), "counted": "8"}))
    product.refresh_from_db()
    assert product.stock_quantity == 8
    assert StockMovement.objects.filter(product=product, kind="stocktake", delta=-2).count() == 1


def test_reconcile_aligns_ledger_without_moving_counter():
    product = ProductFactory(stock_quantity=10)  # legacy: counter 10, ledger 0
    assert services.reconciliation(product)["ok"] is False
    views.stock(_req("post", {"action": "reconcile", "product": str(product.id)}))
    product.refresh_from_db()
    assert product.stock_quantity == 10  # счётчик НЕ тронут
    assert services.reconciliation(product)["ok"] is True  # ledger выровнен под счётчик


def test_reconcile_then_receipt_stays_consistent():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "reconcile", "product": str(product.id)}))  # diff→0
    views.stock(_req("post", {"action": "receipt", "product": str(product.id), "qty": "4"}))
    product.refresh_from_db()
    assert product.stock_quantity == 14
    assert services.reconciliation(product)["ok"] is True  # 14 == ledger(10+4)


def test_threshold_saved_to_site_config():
    tenant = TenantFactory()  # saved
    resp = views.stock(_req("post", {"action": "threshold", "value": "3"}, tenant=tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config.get("low_stock_threshold") == 3
