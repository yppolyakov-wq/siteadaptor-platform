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
from apps.catalog.images import (
    apply_gallery_op,
    gallery_add,
    gallery_remove,
    gallery_replace,
    save_product_image,
    validate_image,
)
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


def test_media_gallery_per_slide_controls_only_in_preview():
    """Галерея детальной: пер-слайд 📷/🗑 + плитка «＋» рендерятся ТОЛЬКО в превью
    редактора (is_preview+edit_pk); на публичной витрине контролов нет."""
    from django.template.loader import render_to_string

    ctx = {
        "images": [{"id": "a", "url": "/a.png"}, {"id": "b", "url": "/b.png"}],
        "edit_pk": "PK1",
        "edit_model": "product",
    }
    editor = render_to_string("storefront/_media_gallery.html", {**ctx, "is_preview": True})
    assert 'data-photo-op="replace"' in editor and 'data-photo-op="remove"' in editor
    assert 'data-photo-op="add"' in editor and 'data-img-id="a"' in editor
    public = render_to_string("storefront/_media_gallery.html", {**ctx, "is_preview": False})
    assert "data-photo-op" not in public  # на публичной — никаких контролов


def test_media_gallery_empty_state_has_add_tile_in_preview():
    """Пустая галерея в редакторе (фото удалили / их нет) → плитка «＋ добавить» (op=add),
    чтобы не было тупика. На публичной без фото — никаких контролов."""
    from django.template.loader import render_to_string

    ctx = {"images": [], "edit_pk": "PK1", "edit_model": "event"}
    editor = render_to_string("storefront/_media_gallery.html", {**ctx, "is_preview": True})
    assert 'data-photo-op="add"' in editor and 'data-edit-model="event"' in editor
    assert 'data-photo-op="replace"' not in editor  # слайдов нет — только «＋»
    public = render_to_string("storefront/_media_gallery.html", {**ctx, "is_preview": False})
    assert "data-photo-op" not in public


# --- Пер-слайд управление галереей (gallery_replace/add/remove/apply_gallery_op) ---
@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_gallery_replace_by_id_in_place_keeps_count_and_primary():
    imgs = [
        {"id": "a", "url": "/a.png", "path": "", "is_primary": True, "sort_order": 0},
        {"id": "b", "url": "/b.png", "path": "", "is_primary": False, "sort_order": 1},
    ]
    out = gallery_replace(imgs, "b", _png(), folder="products")
    assert len(out) == 2  # замена В МЕСТЕ
    assert out[1]["id"] != "b" and out[1]["url"] != "/b.png"  # слот b заменён
    assert out[1]["is_primary"] is False and out[1]["sort_order"] == 1  # позиция/флаг сохранены
    assert out[0]["id"] == "a" and out[0]["is_primary"] is True  # главное не тронуто


@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_gallery_replace_empty_id_replaces_primary():
    """📷 на карточке (без id) → заменяет ГЛАВНОЕ фото в месте."""
    imgs = [
        {"id": "a", "url": "/a.png", "path": "", "is_primary": False, "sort_order": 0},
        {"id": "b", "url": "/b.png", "path": "", "is_primary": True, "sort_order": 1},
    ]
    out = gallery_replace(imgs, "", _png(), folder="products")
    assert len(out) == 2
    assert out[1]["url"] != "/b.png" and out[1]["is_primary"] is True  # заменено именно главное
    assert out[0]["url"] == "/a.png"


@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_gallery_replace_empty_gallery_adds_primary():
    out = gallery_replace([], "", _png(), folder="products")
    assert len(out) == 1 and out[0]["is_primary"] is True


@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_gallery_replace_stale_id_appends():
    imgs = [{"id": "a", "url": "/a.png", "path": "", "is_primary": True, "sort_order": 0}]
    out = gallery_replace(imgs, "missing", _png(), folder="products")
    assert len(out) == 2 and out[0]["id"] == "a"  # загруженный файл не потерян
    assert out[1]["is_primary"] is False


@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_gallery_add_appends_non_primary():
    imgs = [{"id": "a", "url": "/a.png", "path": "", "is_primary": True, "sort_order": 0}]
    out = gallery_add(imgs, _png(), folder="products")
    assert len(out) == 2 and out[1]["is_primary"] is False and out[1]["sort_order"] == 1


@pytest.mark.django_db
def test_gallery_remove_drops_and_promotes_primary():
    imgs = [
        {"id": "a", "url": "/a.png", "path": "", "is_primary": True, "sort_order": 0},
        {"id": "b", "url": "/b.png", "path": "", "is_primary": False, "sort_order": 1},
    ]
    out = gallery_remove(imgs, "a")  # удаляем ГЛАВНОЕ
    assert (
        len(out) == 1 and out[0]["id"] == "b" and out[0]["is_primary"] is True
    )  # primary переназначен


@override_settings(MEDIA_ROOT="/tmp/test_media_gallery")
@pytest.mark.django_db
def test_apply_gallery_op_dispatch_and_errors():
    imgs = [{"id": "a", "url": "/a.png", "path": "", "is_primary": True, "sort_order": 0}]
    # remove без файла — ок
    assert apply_gallery_op(imgs, op="remove", image_id="a", uploaded=None, folder="products") == []
    # replace/add без файла → ValueError (эндпоинт вернёт 400)
    with pytest.raises(ValueError):
        apply_gallery_op(imgs, op="replace", image_id="a", uploaded=None, folder="products")
    with pytest.raises(ValueError):
        apply_gallery_op(imgs, op="add", image_id="", uploaded=None, folder="products")
    # неизвестный op → ValueError
    with pytest.raises(ValueError):
        apply_gallery_op(imgs, op="frobnicate", image_id="", uploaded=_png(), folder="products")


@pytest.mark.django_db
def test_validate_rejects_corrupt_png_as_validationerror():
    """Битый PNG (валидная сигнатура, ломаный IDAT) → ValidationError (чистый 400),
    а не SyntaxError из Pillow (иначе 500 на канве замены фото)."""
    # Минимальный PNG с правильной сигнатурой, но сломанной CRC в IDAT.
    import base64

    corrupt = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    bad = SimpleUploadedFile("broken.png", corrupt, content_type="image/png")
    with pytest.raises(ValidationError):
        validate_image(bad)


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
