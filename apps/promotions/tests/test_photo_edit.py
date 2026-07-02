"""UE3-2: галерея акции на канве витрины — promotion_photo_edit (реюз
catalog.images.apply_gallery_op; folder="promotions"). Закрывает пробел:
promotion была единственной моделью канвы без фото-эдита."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.promotions import views
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _req(pk, *, op=None, image_id=None, with_file=True):
    data = {"pk": str(pk)}
    if op:
        data["op"] = op
    if image_id is not None:
        data["image_id"] = image_id
    req = RequestFactory().post("/promotions/photo-edit/", data=data)
    if with_file:
        buf = BytesIO()
        Image.new("RGB", (40, 40), "#abc").save(buf, format="PNG")
        req.FILES["image"] = SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = SimpleNamespace(schema_name="public")
    return req


def test_replace_into_empty_gallery_adds_primary(tmp_path, settings):
    """Пустая галерея (карточка показывает фолбэк-фото товара) → replace честно
    ДОБАВЛЯЕТ главное фото акции, фолбэк перестаёт использоваться."""
    settings.MEDIA_ROOT = str(tmp_path)
    p = PromotionFactory(images=[])
    assert views.promotion_photo_edit(_req(p.pk)).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 1 and p.images[0]["is_primary"]


def test_replace_primary_in_place_no_duplicate(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    p = PromotionFactory(images=[{"id": "x", "url": "/old.png", "is_primary": True}])
    assert views.promotion_photo_edit(_req(p.pk)).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 1  # замена В МЕСТЕ, без дубля
    assert p.images[0]["is_primary"] and p.images[0]["url"] != "/old.png"


def test_add_appends_slide(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    p = PromotionFactory(images=[{"id": "x", "url": "/old.png", "is_primary": True}])
    assert views.promotion_photo_edit(_req(p.pk, op="add")).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 2
    assert p.images[0]["is_primary"] and not p.images[1]["is_primary"]  # primary цел


def test_remove_by_id(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    p = PromotionFactory(images=[{"id": "x", "url": "/old.png", "is_primary": True}])
    assert (
        views.promotion_photo_edit(
            _req(p.pk, op="remove", image_id="x", with_file=False)
        ).status_code
        == 204
    )
    p.refresh_from_db()
    assert p.images == []


def test_replace_without_file_400():
    p = PromotionFactory(images=[])
    before = p.images
    assert views.promotion_photo_edit(_req(p.pk, with_file=False)).status_code == 400
    p.refresh_from_db()
    assert p.images == before


def test_garbage_pk_400():
    assert views.promotion_photo_edit(_req("not-a-uuid")).status_code == 400
