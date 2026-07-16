"""Склад-2 E3.2: кабинет закупок — Bestellungen/Lieferanten/Wareneingang."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.inventory import purchasing
from apps.inventory.models import Bestellung, Lieferant, Lot, StockMovement
from apps.inventory.views_purchasing import purchasing_view
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "chef"


def _req(method="get", data=None, tenant=None, query=""):
    req = getattr(RequestFactory(), method)(f"/dashboard/purchasing/{query}", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory.build(business_type="bakery")
    return req


def test_get_renders_overview():
    html = purchasing_view(_req()).content.decode()
    assert "Einkauf" in html and "Bestellungen" in html and "Lieferanten" in html


def test_create_supplier_and_po():
    purchasing_view(_req("post", {"action": "create_supplier", "name": "Großhandel Nord"}))
    supplier = Lieferant.objects.get(name="Großhandel Nord")
    resp = purchasing_view(_req("post", {"action": "create_po", "supplier": str(supplier.pk)}))
    assert resp.status_code == 302
    po = Bestellung.objects.get()
    assert po.supplier_id == supplier.pk and po.status == "draft"
    assert f"?po={po.pk}" in resp["Location"]  # редирект в деталь


def test_add_line_and_order_and_receive_flow():
    product = ProductFactory(stock_quantity=2, cost_price=Decimal("1.50"))
    po = purchasing.create_po()
    # добавить строку через вьюху (запятая как десятичный разделитель EK)
    purchasing_view(
        _req(
            "post",
            {
                "action": "add_line",
                "po": str(po.pk),
                "entity": f"p{product.pk}",
                "qty": "6",
                "unit_cost": "1,80",
            },
        )
    )
    line = po.positions.get()
    assert line.qty == 6 and line.unit_cost == Decimal("1.80")
    # bestellt → приёмка (частично 4, пустое qty = остаток)
    purchasing_view(_req("post", {"action": "set_status", "po": str(po.pk), "status": "ordered"}))
    purchasing_view(
        _req(
            "post",
            {"action": "receive_line", "po": str(po.pk), "line": str(line.pk), "qty": "4"},
        )
    )
    product.refresh_from_db()
    assert product.stock_quantity == 6  # 2 + 4
    purchasing_view(
        _req("post", {"action": "receive_line", "po": str(po.pk), "line": str(line.pk)})
    )  # пустое qty → принять остаток (2)
    product.refresh_from_db()
    line.refresh_from_db()
    po.refresh_from_db()
    assert product.stock_quantity == 8 and line.qty_received == 6
    assert po.status == "received"  # авто-закрытие
    assert StockMovement.objects.filter(product=product, source="purchase").count() == 2


def test_receive_with_lots_creates_charge():
    tenant = TenantFactory.build(business_type="bakery", site_config={"lots_enabled": True})
    product = ProductFactory(stock_quantity=0)
    po = purchasing.create_po()
    line = purchasing.add_po_line(po, product=product, qty=5)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing_view(
        _req(
            "post",
            {
                "action": "receive_line",
                "po": str(po.pk),
                "line": str(line.pk),
                "lot_code": "CH-9",
                "lot_mhd": "2030-03-01",
            },
            tenant=tenant,
        )
    )
    lot = Lot.objects.get(product=product)
    assert lot.lot_code == "CH-9" and lot.qty_remaining == 5
    assert lot.mhd.isoformat() == "2030-03-01"


def test_po_from_suggestions_via_view():
    # товар под порогом с Sollbestand → черновик из предложений
    ProductFactory(stock_quantity=1, reorder_point=5, reorder_target=20)
    resp = purchasing_view(_req("post", {"action": "po_from_suggestions"}))
    assert resp.status_code == 302
    po = Bestellung.objects.get()
    assert po.positions.get().qty == 19  # 20 − 1


def test_po_from_suggestions_empty_no_orphan_draft():
    # нет предложений → пустой черновик не создаётся
    purchasing_view(_req("post", {"action": "po_from_suggestions"}))
    assert Bestellung.objects.count() == 0


def test_remove_line_only_in_draft():
    product = ProductFactory(stock_quantity=0)
    po = purchasing.create_po()
    line = purchasing.add_po_line(po, product=product, qty=2)
    purchasing_view(_req("post", {"action": "remove_line", "po": str(po.pk), "line": str(line.pk)}))
    assert po.positions.count() == 0
