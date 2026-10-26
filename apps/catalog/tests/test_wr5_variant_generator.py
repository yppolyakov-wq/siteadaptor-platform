"""KA-12 WR-5 (E3.1): генератор вариантов «размеры × цвета» и фото на цвет."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import Product, ProductVariant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(data, files=None):
    request = RequestFactory().post("/x/", {**data, **(files or {})})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    return request


def _product():
    return Product.objects.create(name={"de": "Shirt"}, base_price=Decimal("19.90"))


def test_generate_cross_product_skips_existing_and_logs_stock():
    from apps.inventory.models import StockMovement

    p = _product()
    ProductVariant.objects.create(product=p, size="M", color="Blau")
    views.variant_generate(
        _post({"sizes": "S, M, L", "colors": "Blau\nRot", "stock": "3"}), pk=p.pk
    )
    labels = set(p.variants.values_list("label", flat=True))
    assert labels == {"S · Blau", "M · Blau", "L · Blau", "S · Rot", "M · Rot", "L · Rot"}
    new = p.variants.exclude(label="M · Blau")
    assert all(v.stock_quantity == 3 and v.size and v.color for v in new)
    assert StockMovement.objects.filter(variant__in=new).count() == 5


def test_generate_only_sizes_and_cap():
    p = _product()
    views.variant_generate(_post({"sizes": "S,M,s"}), pk=p.pk)  # дубль без учёта регистра
    assert set(p.variants.values_list("label", flat=True)) == {"S", "M"}
    many = ",".join(str(i) for i in range(20))
    views.variant_generate(_post({"sizes": many, "colors": many}), pk=p.pk)  # 400 > потолка
    assert p.variants.count() == 2


def test_color_photo_sets_all_variants_of_colour(monkeypatch):
    p = _product()
    for sz in ("S", "M"):
        ProductVariant.objects.create(product=p, size=sz, color="Blau")
    other = ProductVariant.objects.create(product=p, size="S", color="Rot")
    ref = {"url": "/media/blau.webp", "is_primary": True}
    monkeypatch.setattr(views, "_uploaded_variant_image", lambda request: ref)
    views.variant_color_photo(_post({"color": "blau"}), pk=p.pk)
    assert all(v.images == [ref] for v in p.variants.filter(color="Blau"))
    other.refresh_from_db()
    assert other.images in ([], None)
