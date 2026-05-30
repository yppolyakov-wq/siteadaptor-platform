"""Тесты загрузки картинок товара (storage во временной папке)."""

import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from PIL import Image

from apps.catalog import views
from apps.catalog.images import save_product_image, validate_image
from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory


def _png(size=(20, 20)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile("pic.png", buf.read(), content_type="image/png")


def _attach(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner", email="o@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_validate_rejects_non_image():
    bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    with pytest.raises(ValidationError):
        validate_image(bad)


@pytest.mark.django_db
def test_validate_rejects_too_large():
    big = SimpleUploadedFile("x.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png")
    with pytest.raises(ValidationError):
        validate_image(big)


@override_settings(MEDIA_ROOT="/tmp/test_media_unit")
@pytest.mark.django_db
def test_save_product_image_returns_fileref():
    ref = save_product_image(_png(), is_primary=True, sort_order=0)
    assert ref["mime_type"] == "image/png"
    assert ref["is_primary"] is True
    assert ref["url"].endswith(".png")
    assert "id" in ref and "path" in ref


@override_settings(MEDIA_ROOT="/tmp/test_media_views")
@pytest.mark.django_db
def test_upload_on_create_sets_primary(user):
    req = RequestFactory().post(
        "/catalog/products/new/",
        {
            "name_de": "Brot",
            "name_en": "",
            "description_de": "",
            "description_en": "",
            "base_price": "1.50",
            "currency": "EUR",
            "sku": "B1",
            "is_active": "on",
            "images": _png(),
        },
    )
    _attach(req, user)
    resp = views.product_create(req)
    assert resp.status_code == 302
    p = Product.objects.get(sku="B1")
    assert len(p.images) == 1
    assert p.images[0]["is_primary"] is True
    assert p.primary_image is not None


@override_settings(MEDIA_ROOT="/tmp/test_media_views")
@pytest.mark.django_db
def test_image_delete_reassigns_primary(user):
    p = ProductFactory(
        images=[
            {"id": "a", "url": "a.png", "is_primary": True, "path": ""},
            {"id": "b", "url": "b.png", "is_primary": False, "path": ""},
        ]
    )
    req = RequestFactory().post(f"/catalog/products/{p.pk}/images/a/delete/")
    _attach(req, user)
    resp = views.product_image_delete(req, pk=p.pk, image_id="a")
    assert resp.status_code == 302
    p.refresh_from_db()
    assert len(p.images) == 1
    assert p.images[0]["id"] == "b"
    assert p.images[0]["is_primary"] is True  # главная переназначена


@override_settings(MEDIA_ROOT="/tmp/test_media_views")
@pytest.mark.django_db
def test_image_make_primary(user):
    p = ProductFactory(
        images=[
            {"id": "a", "url": "a.png", "is_primary": True, "path": ""},
            {"id": "b", "url": "b.png", "is_primary": False, "path": ""},
        ]
    )
    req = RequestFactory().post(f"/catalog/products/{p.pk}/images/b/primary/")
    _attach(req, user)
    views.product_image_primary(req, pk=p.pk, image_id="b")
    p.refresh_from_db()
    by_id = {i["id"]: i for i in p.images}
    assert by_id["b"]["is_primary"] is True
    assert by_id["a"]["is_primary"] is False
