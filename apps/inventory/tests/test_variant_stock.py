"""T2: склад по вариантам — движение/реконсиляция/кабинет на уровне ProductVariant."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
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


def _req(method="get", data=None):
    req = getattr(RequestFactory(), method)("/dashboard/stock/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(business_type="retail")
    return req


def _variant(stock=None):
    p = ProductFactory(base_price=Decimal("9.90"), stock_quantity=None)  # товар вариантный
    return ProductVariant.objects.create(product=p, label="M", stock_quantity=stock)


def test_apply_manual_movement_moves_variant_counter():
    v = _variant(stock=5)
    mv = services.apply_manual_movement(
        product=v.product, variant=v, kind=StockMovement.KIND_RECEIPT, delta=4
    )
    v.refresh_from_db()
    assert v.stock_quantity == 9
    assert mv.variant_id == v.id and mv.delta == 4


def test_variant_reconciliation_independent_from_product():
    v = _variant(stock=10)
    services.record_opening_balance(product=v.product, variant=v)  # леджер = 10
    rec = services.reconciliation(v.product, v)
    assert rec["tracked"] and rec["ok"] and rec["ledger"] == 10
    # движение варианта не влияет на product-level ledger (variant IS NULL)
    assert services.ledger_balance(v.product, variant=None) == 0


def test_reconciliation_rows_list_variants_not_product():
    v1 = _variant(stock=3)
    ProductVariant.objects.create(product=v1.product, label="L", stock_quantity=7)
    services.record_opening_balance(product=v1.product, variant=v1)
    rows = services.reconciliation_rows()
    labels = [r["label"] for r in rows]
    assert any("· M" in x for x in labels) and any("· L" in x for x in labels)
    # сам вариантный товар (stock None) отдельной строкой не идёт
    assert str(v1.product) not in labels


def test_cabinet_receipt_on_variant_via_entity():
    v = _variant(stock=2)
    views.stock(_req("post", {"action": "receipt", "entity": f"v{v.id}", "qty": "6"}))
    v.refresh_from_db()
    assert v.stock_quantity == 8
    assert StockMovement.objects.filter(variant=v, kind="receipt", delta=6).exists()


def test_cabinet_stocktake_on_variant_sets_absolute():
    v = _variant(stock=10)
    views.stock(_req("post", {"action": "stocktake", "entity": f"v{v.id}", "counted": "6"}))
    v.refresh_from_db()
    assert v.stock_quantity == 6
    assert StockMovement.objects.filter(variant=v, kind="stocktake", delta=-4).exists()
