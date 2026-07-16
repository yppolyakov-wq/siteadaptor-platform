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
    resp = views.stock(_req("post", {"action": "receipt", "entity": f"p{product.id}", "qty": "5"}))
    assert resp.status_code == 302
    product.refresh_from_db()
    assert product.stock_quantity == 7
    mv = StockMovement.objects.filter(product=product, kind="receipt")
    assert mv.count() == 1 and mv.first().delta == 5
    # приёмка двигает счётчик И леджер на +5 → разница (diff) неизменна
    assert services.reconciliation(product)["diff"] == 2


def test_adjustment_moves_counter_and_clamps():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "adjustment", "entity": f"p{product.id}", "delta": "-3"}))
    product.refresh_from_db()
    assert product.stock_quantity == 7
    assert StockMovement.objects.filter(product=product, kind="adjustment", delta=-3).count() == 1


def test_stocktake_sets_absolute_and_logs_difference():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "stocktake", "entity": f"p{product.id}", "counted": "8"}))
    product.refresh_from_db()
    assert product.stock_quantity == 8
    assert StockMovement.objects.filter(product=product, kind="stocktake", delta=-2).count() == 1


def test_reconcile_aligns_ledger_without_moving_counter():
    product = ProductFactory(stock_quantity=10)  # legacy: counter 10, ledger 0
    assert services.reconciliation(product)["ok"] is False
    views.stock(_req("post", {"action": "reconcile", "entity": f"p{product.id}"}))
    product.refresh_from_db()
    assert product.stock_quantity == 10  # счётчик НЕ тронут
    assert services.reconciliation(product)["ok"] is True  # ledger выровнен под счётчик


def test_reconcile_then_receipt_stays_consistent():
    product = ProductFactory(stock_quantity=10)
    views.stock(_req("post", {"action": "reconcile", "entity": f"p{product.id}"}))  # diff→0
    views.stock(_req("post", {"action": "receipt", "entity": f"p{product.id}", "qty": "4"}))
    product.refresh_from_db()
    assert product.stock_quantity == 14
    assert services.reconciliation(product)["ok"] is True  # 14 == ledger(10+4)


def test_threshold_saved_to_site_config():
    tenant = TenantFactory()  # saved
    resp = views.stock(_req("post", {"action": "threshold", "value": "3"}, tenant=tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config.get("low_stock_threshold") == 3


def test_cabinet_shows_warenwert_and_reorder(settings):
    from decimal import Decimal

    ProductFactory(base_price=Decimal("10"), stock_quantity=4, cost_price=Decimal("6.00"))
    html = views.stock(_req()).content.decode()
    assert "Warenwert" in html  # T5: Bestandswert-Plakette
    assert "24" in html  # 4 × 6.00 €
    assert "Bestellvorschläge" in html  # T5: Bestand 4 ≤ globaler Schwellwert (5)


# --- Склад-2 E1.2: Chargen/MHD в кабинете ---


def _lot_tenant():
    return TenantFactory.build(business_type="bakery", site_config={"lots_enabled": True})


def test_lots_toggle_saves_site_config():
    tenant = TenantFactory()  # saved, без тумблера
    views.stock(_req("post", {"action": "lots_toggle", "lots_enabled": "on"}, tenant=tenant))
    tenant.refresh_from_db()
    assert tenant.site_config.get("lots_enabled") is True
    views.stock(_req("post", {"action": "lots_toggle"}, tenant=tenant))  # без «on» → выкл
    tenant.refresh_from_db()
    assert tenant.site_config.get("lots_enabled") is False


def test_receipt_creates_lot_when_lots_enabled():
    from apps.inventory.models import Lot

    product = ProductFactory(stock_quantity=0)
    data = {
        "action": "receipt",
        "entity": f"p{product.id}",
        "qty": "8",
        "lot_code": "CH-77",
        "lot_mhd": "2030-01-15",
    }
    views.stock(_req("post", data, tenant=_lot_tenant()))
    product.refresh_from_db()
    assert product.stock_quantity == 8  # счётчик двинулся
    lot = Lot.objects.get(product=product)
    assert lot.lot_code == "CH-77" and lot.qty_remaining == 8
    assert lot.mhd.isoformat() == "2030-01-15"  # MHD распарсен
    assert services.lot_balance(product) == 8  # Σ партий == счётчик


def test_receipt_plain_counter_when_lots_disabled():
    from apps.inventory.models import Lot

    product = ProductFactory(stock_quantity=0)
    # тумблер выкл (build без site_config) → приёмка как раньше, без партии
    views.stock(_req("post", {"action": "receipt", "entity": f"p{product.id}", "qty": "3"}))
    product.refresh_from_db()
    assert product.stock_quantity == 3
    assert Lot.objects.filter(product=product).count() == 0


def test_verderb_lot_writes_off_charge():
    from apps.inventory.services import receive_lot

    product = ProductFactory(stock_quantity=0)
    lot, _mv = receive_lot(product=product, qty=5, mhd=None, lot_code="X")
    views.stock(
        _req("post", {"action": "verderb_lot", "lot_id": str(lot.pk)}, tenant=_lot_tenant())
    )
    lot.refresh_from_db()
    product.refresh_from_db()
    assert lot.qty_remaining == 0  # партия списана
    assert product.stock_quantity == 0  # счётчик уменьшен на списанное
    assert StockMovement.objects.filter(product=product, kind="adjustment", delta=-5).exists()


def test_mhd_overview_renders_when_lots_present():
    from apps.inventory.services import receive_lot

    product = ProductFactory(stock_quantity=0)
    receive_lot(product=product, qty=2, mhd=views._parse_date("2030-06-01"), lot_code="FRESH")
    html = views.stock(_req(tenant=_lot_tenant())).content.decode()
    assert "Haltbarkeit" in html  # секция MHD-обзора
    assert "FRESH" in html
    assert "Charge" in html  # приёмка предлагает поле партии
