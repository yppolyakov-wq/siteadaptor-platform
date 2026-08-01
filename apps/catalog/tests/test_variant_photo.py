"""Фото варианта загружается из кабинета (O-1, 2026-08-01).

`ProductVariant.images` завели в M4-A и витрина подменяет им главное фото, но
загрузить его было НЕЧЕМ: в форме варианта полей не было, CSV-импорт их не пишет,
единственным писателем оставался демо-кит. Функция была мёртвой у владельца.
"""

import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.catalog import views
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _png(name="v.png"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "blue").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _post(path, data, files=None):
    req = RequestFactory().post(path, {**data, **(files or {})})
    req.tenant = TenantFactory.build()
    req.user = get_user_model()(username="o", is_active=True)
    req.session = {}
    req._messages = FallbackStorage(req)
    return req


def test_variant_add_stores_uploaded_photo():
    product = ProductFactory()
    views.variant_add(
        _post("/x/", {"label": "S · Blau", "price": "9.90"}, {"image": _png()}),
        pk=product.pk,
    )
    variant = ProductVariant.objects.get(product=product, label="S · Blau")
    assert variant.image_url  # витрина подменит им главное фото


def test_variant_update_replaces_and_removes_photo():
    product = ProductFactory()
    variant = ProductVariant.objects.create(product=product, label="M", price="9.90")
    views.variant_update(
        _post("/x/", {"sort": "0", "is_active": "1"}, {"image": _png("a.png")}),
        pk=product.pk,
        vid=variant.pk,
    )
    variant.refresh_from_db()
    first = variant.image_url
    assert first

    views.variant_update(
        _post("/x/", {"sort": "0", "is_active": "1"}, {"image": _png("b.png")}),
        pk=product.pk,
        vid=variant.pk,
    )
    variant.refresh_from_db()
    assert variant.image_url and variant.image_url != first  # замена, не добавление
    assert len(variant.images) == 1  # одно фото на вариант

    views.variant_update(
        _post("/x/", {"sort": "0", "is_active": "1", "remove_image": "1"}),
        pk=product.pk,
        vid=variant.pk,
    )
    variant.refresh_from_db()
    assert variant.images == []


def test_save_without_file_keeps_existing_photo():
    """Обычное сохранение цены/остатка не должно ронять фото (инвариант W0)."""
    product = ProductFactory()
    variant = ProductVariant.objects.create(product=product, label="L", price="9.90")
    views.variant_update(
        _post("/x/", {"sort": "0", "is_active": "1"}, {"image": _png()}),
        pk=product.pk,
        vid=variant.pk,
    )
    views.variant_update(
        _post("/x/", {"sort": "0", "is_active": "1", "price": "12.00"}),
        pk=product.pk,
        vid=variant.pk,
    )
    variant.refresh_from_db()
    assert variant.image_url
    assert str(variant.price) == "12.00"


def test_variant_forms_accept_files():
    """Без multipart файл до вьюхи не доедет — форма обязана быть enctype'ной."""
    from pathlib import Path

    html = Path("templates/catalog/product_form.html").read_text(encoding="utf-8")
    for action in ("catalog:variant-update", "catalog:variant-add"):
        idx = html.index(action)
        head = html.rindex("<form", 0, idx)
        assert 'enctype="multipart/form-data"' in html[head:idx]
