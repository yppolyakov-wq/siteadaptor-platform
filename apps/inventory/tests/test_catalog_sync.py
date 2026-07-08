"""T1: правки остатка в каталоге (форма товара/варианта) пишут склад-леджер →
реконсиляция «Zähler ↔ Ledger» остаётся сходящейся (раньше каталог обходил леджер)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import Product, ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.inventory import services
from apps.inventory.models import StockMovement

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


def _post(user, path, data):
    req = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    return req


def _form(**over):
    base = {
        "name_de": "Mehl",
        "name_en": "",
        "description_de": "",
        "description_en": "",
        "base_price": "2.00",
        "currency": "EUR",
        "sku": "",
        "is_active": "on",
    }
    base.update(over)
    return base


# --- unit: log_catalog_change ------------------------------------------------


def test_log_catalog_change_logs_delta():
    p = ProductFactory(stock_quantity=10)
    mv = services.log_catalog_change(product=p, old=10, new=7)
    assert mv.delta == -3 and mv.source == "catalog" and mv.kind == "adjustment"


def test_log_catalog_change_new_product_opening():
    mv = services.log_catalog_change(product=ProductFactory(stock_quantity=5), old=None, new=5)
    assert mv.delta == 5


def test_log_catalog_change_none_or_zero_is_noop():
    p = ProductFactory(stock_quantity=None)
    assert services.log_catalog_change(product=p, old=3, new=None) is None
    assert services.log_catalog_change(product=p, old=5, new=5) is None


# --- integration: catalog views ---------------------------------------------


def test_product_create_logs_opening_and_reconciles(user):
    views.product_create(
        _post(user, "/catalog/products/new/", _form(sku="MEHL-1", stock_quantity="20"))
    )
    p = Product.objects.get(sku="MEHL-1")
    assert p.stock_quantity == 20
    assert services.reconciliation(p)["ok"] is True
    assert StockMovement.objects.filter(product=p, source="catalog", delta=20).exists()


def test_product_edit_logs_delta_and_stays_reconciled(user):
    p = ProductFactory(name={"de": "Mehl", "en": ""}, base_price="2.00", stock_quantity=None)
    views.product_edit(_post(user, "/x/", _form(stock_quantity="10")), pk=p.pk)
    p.refresh_from_db()
    assert p.stock_quantity == 10 and services.reconciliation(p)["ok"] is True
    views.product_edit(_post(user, "/x/", _form(stock_quantity="4")), pk=p.pk)
    p.refresh_from_db()
    assert p.stock_quantity == 4 and services.reconciliation(p)["ok"] is True  # всё ещё сходится
    assert StockMovement.objects.filter(product=p, source="catalog").count() == 2  # +10, −6


def test_variant_add_and_update_log_movements(user):
    product = ProductFactory(base_price="9.90")
    views.variant_add(
        _post(user, "/x/", {"label": "M", "price": "5,50", "stock": "12"}), pk=product.pk
    )
    v = ProductVariant.objects.get(product=product, label="M")
    assert StockMovement.objects.filter(
        product=product, variant=v, source="catalog", delta=12
    ).exists()
    views.variant_update(
        _post(user, "/x/", {"price": "5,50", "stock": "8", "sort": "0"}), pk=product.pk, vid=v.pk
    )
    assert StockMovement.objects.filter(
        product=product, variant=v, source="catalog", delta=-4
    ).exists()
