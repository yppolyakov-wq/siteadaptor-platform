"""M23b: product-feed (Google Merchant / Meta) — билдер и публичная вьюха."""

from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.catalog.feed import build_google_feed
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _build(products):
    return build_google_feed(
        products=products,
        title="Bäckerei",
        link="https://shop.test/",
        description="Produkte",
        product_url=lambda p: f"https://shop.test/sortiment/{p.pk}/",
        absolutize=lambda u: u if u.startswith("http") else f"https://shop.test{u}",
    )


def test_feed_simple_product():
    product = ProductFactory(base_price=Decimal("9.90"), name={"de": "Brot"}, stock_quantity=3)
    xml = _build([product])
    assert "<rss" in xml and 'xmlns:g="http://base.google.com/ns/1.0"' in xml
    assert f"<g:id>{product.pk}</g:id>" in xml
    assert "<g:title>Brot</g:title>" in xml
    assert "<g:price>9.90 EUR</g:price>" in xml
    assert "<g:availability>in_stock</g:availability>" in xml
    assert f"https://shop.test/sortiment/{product.pk}/" in xml


def test_feed_out_of_stock():
    product = ProductFactory(stock_quantity=0)
    assert "<g:availability>out_of_stock</g:availability>" in _build([product])


def test_feed_variants_share_item_group():
    product = ProductFactory(base_price=Decimal("5.00"), name={"de": "Tee"})
    ProductVariant.objects.create(product=product, label="100 g", price=Decimal("5.00"))
    ProductVariant.objects.create(product=product, label="250 g", price=Decimal("12.00"))
    xml = _build([product])
    assert xml.count("<item>") == 2  # по варианту
    assert f"<g:item_group_id>{product.pk}</g:item_group_id>" in xml
    assert "<g:price>12.00 EUR</g:price>" in xml
    assert "250 g" in xml


def test_feed_image_absolutized():
    product = ProductFactory(images=[{"url": "/media/p.jpg", "is_primary": True}])
    assert "<g:image_link>https://shop.test/media/p.jpg</g:image_link>" in _build([product])


def test_feed_view_renders_xml():
    product = ProductFactory(name={"de": "Brot"})
    from apps.promotions import public_views

    req = RequestFactory().get("/feed/google.xml")
    req.tenant = TenantFactory.build(name="Bäckerei Müller")
    resp = public_views.product_feed_xml(req)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/xml"
    body = resp.content.decode()
    assert "Bäckerei Müller" in body
    assert str(product.pk) in body
