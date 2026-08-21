"""Фидбэк 2026-08-04: артикулы + «Zusammenführen» (слияние товаров в карточку)."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import merge, views
from apps.catalog.models import ModifierGroup, ModifierOption, Product, ProductVariant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _p(name, price="10.00", stock=5, sku=""):
    from apps.inventory.services import log_catalog_change

    product = Product.objects.create(
        name={"de": name}, base_price=Decimal(price), stock_quantity=stock, sku=sku
    )
    # честный путь кабинета: стартовый остаток попадает в леджер (T1)
    log_catalog_change(product=product, old=None, new=stock)
    return product


def _req(method="post", data=None):
    request = getattr(RequestFactory(), method)("/catalog/products/merge/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"m-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    return request


def test_merge_moves_identity_price_stock_and_ledger():
    """Прочие товары становятся вариантами главного: артикул/EAN/цена/остаток
    переезжают; старый товар гаснет с нулём остатка; леджер сходится с обеих
    сторон (реконсиляция T1)."""
    from apps.inventory.services import reconciliation

    main = _p("T-Shirt", sku="TS-MAIN")
    other = _p("T-Shirt Blau", price="12.00", stock=7, sku="TS-BLau-01")
    other.gtin = "4001234567890"
    other.save(update_fields=["gtin"])
    merged, refused = merge.merge_products(main, [other])
    assert merged == 1 and refused == []
    variant = ProductVariant.objects.get(product=main)
    assert variant.label == "T-Shirt Blau"
    assert variant.sku == "TS-BLau-01" and variant.gtin == "4001234567890"
    assert variant.price == Decimal("12.00") and variant.stock_quantity == 7
    other.refresh_from_db()
    assert other.is_active is False and other.stock_quantity == 0
    assert other.metadata["merged_into"] == str(main.pk)
    # леджер: вариант получил +7, старый товар списан в 0 — обе сверки чисты
    assert reconciliation(main, variant)["ok"]
    assert reconciliation(other)["ok"]


def test_merge_refuses_product_with_variants_and_handles_label_clash():
    main = _p("Brot")
    ProductVariant.objects.create(product=main, label="Brot Dunkel")
    rich = _p("Kuchen")
    ModifierOption.objects.create(
        group=ModifierGroup.objects.create(product=rich, name="Extras"), label="Sahne"
    )
    clash = _p("Brot Dunkel", stock=None)  # label уже занят вариантом главного
    merged, refused = merge.merge_products(main, [rich, clash])
    assert merged == 1 and refused == ["Kuchen"]
    assert ProductVariant.objects.filter(product=main, label="Brot Dunkel (2)").exists()


def test_merge_view_confirm_then_apply():
    main, other = _p("Hose", sku="H-1"), _p("Hose Grau", sku="H-2")
    ids = [str(main.pk), str(other.pk)]
    body = views.products_merge(_req(data={"ids": ids})).content.decode()
    assert "Zusammenführen" in body and str(main.pk) in body
    resp = views.products_merge(_req(data={"ids": ids, "main": str(main.pk)}))
    assert resp.status_code == 302 and str(main.pk) in resp.url
    assert ProductVariant.objects.filter(product=main, sku="H-2").exists()


def test_variant_update_saves_sku():
    """Артикул варианта редактируется из формы кабинета (раньше — только CSV)."""
    product = _p("Jacke")
    variant = ProductVariant.objects.create(product=product, label="M")
    views.variant_update(
        _req(data={"sku": "JK-M-01", "gtin": "", "sort": "0", "is_active": "on"}),
        pk=product.pk,
        vid=variant.pk,
    )
    variant.refresh_from_db()
    assert variant.sku == "JK-M-01"


def test_order_snapshots_sku_and_option_sku():
    """«Везде артикул»: позиция заказа снимкует Art.-Nr. (вариантный приоритет),
    опция с артикулом попадает в снимок модификаторов и в modifiers_label."""
    from apps.orders import services as order_services

    product = _p("Pullover", sku="P-BASE")
    variant = ProductVariant.objects.create(product=product, label="L", sku="P-L-01")
    group = ModifierGroup.objects.create(product=product, name="Extras", max_select=2)
    option = ModifierOption.objects.create(group=group, label="Geschenkbox", sku="GB-1")
    order = order_services.create_order(
        items=[(product, variant, 1, [option])], name="Anna", email="a@t.de"
    )
    item = order.items.get()
    assert item.sku == "P-L-01"
    # MX-0: снимок несёт id опции — сверяем поля, не весь dict.
    snap = item.modifiers[0]
    assert (snap["label"], snap["delta"], snap["sku"]) == ("Geschenkbox", "0", "GB-1")
    assert snap["id"]
    assert "Art.-Nr. GB-1" in item.modifiers_label
