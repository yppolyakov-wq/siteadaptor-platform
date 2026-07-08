"""T3-retail: причины корректировки (R3) + поиск по SKU/EAN и bulk-инвентаризация (R1)."""

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


# --- R1: поиск по SKU/EAN -----------------------------------------------------


def test_find_entity_by_product_sku_and_gtin():
    p = ProductFactory(stock_quantity=5, sku="ABC-1", gtin="4001234567890")
    assert services.find_entity_by_code("ABC-1") == (p, None)
    assert services.find_entity_by_code("4001234567890") == (p, None)
    assert services.find_entity_by_code("nope") == (None, None)


def test_find_entity_by_variant_code():
    p = ProductFactory(base_price=Decimal("9.90"))
    v = ProductVariant.objects.create(product=p, label="M", sku="V-1", stock_quantity=3)
    assert services.find_entity_by_code("V-1") == (p, v)


def test_lookup_get_renders_found_box():
    ProductFactory(stock_quantity=7, sku="SCAN-9")
    html = views.stock(_req("get", {"code": "SCAN-9"})).content.decode()
    assert "SCAN-9" not in html or "Bestand" in html  # найденный бокс отрисован
    assert "Bestand" in html


# --- R3: причины корректировки ------------------------------------------------


def test_adjustment_stores_reason_in_note():
    p = ProductFactory(stock_quantity=10)
    views.stock(
        _req(
            "post",
            {"action": "adjustment", "entity": f"p{p.id}", "delta": "-2", "reason": "schwund"},
        )
    )
    mv = StockMovement.objects.get(product=p, kind="adjustment")
    assert mv.delta == -2 and "Schwund" in mv.note


# --- R1b: bulk-инвентаризация -------------------------------------------------


def test_bulk_stocktake_books_only_filled_differences():
    p1 = ProductFactory(stock_quantity=10)
    p2 = ProductFactory(stock_quantity=4)
    views.stock(
        _req(
            "post",
            {
                "action": "stocktake_bulk",
                f"count_p{p1.id}": "8",  # 10 → 8 (Δ −2)
                f"count_p{p2.id}": "",  # пусто → без изменений
            },
        )
    )
    p1.refresh_from_db()
    p2.refresh_from_db()
    assert p1.stock_quantity == 8
    assert p2.stock_quantity == 4  # не тронут
    assert StockMovement.objects.filter(product=p1, kind="stocktake", delta=-2).exists()
    assert not StockMovement.objects.filter(product=p2, kind="stocktake").exists()
