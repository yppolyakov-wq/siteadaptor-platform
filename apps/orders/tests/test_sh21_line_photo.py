"""SH-21 (фидбэк 2026-09-03 «в заказе после номера и до наименования — главное фото
товара; так же при добавлении позиции»). Источник фото по виду строки: вариант → товар →
комбо; свободная строка — плейсхолдер, сетка не схлопывается. Пикер несёт миниатюру.
План — `docs/order-feedback-plan-2026-09-03.md` §4."""

from decimal import Decimal

import pytest

from apps.catalog.models import Combo, ProductVariant
from apps.catalog.picker import _catalog_parts
from apps.catalog.tests.factories import ProductFactory
from apps.orders import services, views
from apps.orders.tests.test_cabinet import _req

pytestmark = pytest.mark.django_db

IMG_P = [{"id": "p", "url": "/media/produkt.webp", "is_primary": True}]
IMG_V = [{"id": "v", "url": "/media/variante.webp", "is_primary": True}]


def test_order_item_image_url_precedence():
    product = ProductFactory(base_price=Decimal("3.00"), images=IMG_P, stock_quantity=9)
    variant = ProductVariant.objects.create(
        product=product, label="XL", price=Decimal("4.00"), images=IMG_V, stock_quantity=9
    )
    order = services.create_order(
        items=[(product, 1), (product, variant, 1)],
        custom_lines=[("Frei", "1.00", 1)],
        name="K",
    )
    urls = [it.image_url for it in order.items.all()]
    assert urls == ["/media/produkt.webp", "/media/variante.webp", ""]


def test_combo_line_uses_combo_photo():
    combo = Combo.objects.create(
        name="Menü", price=Decimal("20.00"), images=[{"url": "/media/kombo.webp", "is_primary": True}]
    )
    order = services.create_order(items=(), combos=[(combo, [], 1)], name="K")
    assert order.items.first().image_url == "/media/kombo.webp"


def test_order_card_renders_a_photo_cell_for_every_line_including_free_ones():
    product = ProductFactory(base_price=Decimal("3.00"), images=IMG_P, stock_quantity=9)
    order = services.create_order(items=[(product, 1)], custom_lines=[("Frei", "1.00", 1)], name="K")
    body = views.order_detail(_req(path=f"/dashboard/orders/{order.pk}/"), order.pk).content.decode()
    rows = body.split('class="dl-row py-2')[1:]
    assert len(rows) == 2
    assert all("dl-photo" in r for r in rows)
    assert "/media/produkt.webp" in rows[0]
    assert "<img" not in rows[1].split("dl-name")[0]  # свободная строка — плейсхолдер без <img>
    assert "data-part-picker" in body  # SH-21: пикер списком с миниатюрами
    assert "/media/produkt.webp" in body.split("data-part-picker")[1]


def test_picker_parts_carry_thumbnails_and_the_value_contract_is_unchanged():
    product = ProductFactory(base_price=Decimal("3.00"), images=IMG_P, name={"de": "Brot"})
    variant = ProductVariant.objects.create(product=product, label="XL", price=Decimal("4.00"), images=IMG_V)
    parts = {p["value"]: p for p in _catalog_parts()}
    assert parts[f"v:{variant.pk}"]["image"] == "/media/variante.webp"
    assert parts[f"v:{variant.pk}"]["title"] == "Brot · XL"
    bare = ProductFactory(base_price=Decimal("1.00"), images=[], name={"de": "Ohne"})
    parts = {p["value"]: p for p in _catalog_parts()}
    assert parts[f"p:{bare.pk}"]["image"] == ""
