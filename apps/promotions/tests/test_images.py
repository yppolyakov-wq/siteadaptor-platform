"""Тесты загрузки фото акций в кабинете."""

import io

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.promotions import views
from apps.promotions.tests.factories import PromotionFactory


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    return SimpleUploadedFile("x.png", buf.getvalue(), content_type="image/png")


def _attach(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_upload_sets_primary(user):
    promo = PromotionFactory()
    req = RequestFactory().post(
        f"/promotions/{promo.pk}/edit/",
        {
            "title_de": "A",
            "title_en": "",
            "description_de": "",
            "description_en": "",
            "promo_type": "reservation",
            "max_per_customer": "1",
            "reservation_ttl_hours": "24",
            "images": _png(),
        },
    )
    _attach(req, user)
    resp = views.promotion_edit(req, pk=promo.pk)
    assert resp.status_code == 302
    promo.refresh_from_db()
    assert len(promo.images) == 1
    assert promo.images[0]["is_primary"] is True


@pytest.mark.django_db
def test_delete_image(user):
    promo = PromotionFactory(
        images=[{"id": "abc", "url": "/x.png", "is_primary": True, "path": "promotions/x.png"}]
    )
    req = _attach(RequestFactory().post(f"/promotions/{promo.pk}/images/abc/delete/"), user)
    resp = views.promotion_image_delete(req, pk=promo.pk, image_id="abc")
    assert resp.status_code == 302
    promo.refresh_from_db()
    assert promo.images == []


@pytest.mark.django_db
def test_set_primary(user):
    promo = PromotionFactory(
        images=[{"id": "a", "is_primary": True}, {"id": "b", "is_primary": False}]
    )
    req = _attach(RequestFactory().post(f"/promotions/{promo.pk}/images/b/primary/"), user)
    views.promotion_image_primary(req, pk=promo.pk, image_id="b")
    promo.refresh_from_db()
    assert promo.images[0]["is_primary"] is False
    assert promo.images[1]["is_primary"] is True


# --- FB-18b: правка готовой акции не теряет фото ------------------------------------


def _big_jpeg():
    """Фото «с камеры телефона»: > 5 МБ (шум не сжимается)."""
    import os

    img = Image.frombytes("RGB", (2400, 1800), os.urandom(2400 * 1800 * 3))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=100)
    data = buf.getvalue()
    assert len(data) > 5 * 1024 * 1024
    return SimpleUploadedFile("kamera.jpg", data, content_type="image/jpeg")


@pytest.mark.django_db
def test_phone_photo_over_5mb_is_shrunk_not_rejected(user):
    promo = PromotionFactory()
    req = RequestFactory().post(
        f"/promotions/{promo.pk}/edit/",
        {
            "title_de": "A",
            "promo_type": "reservation",
            "max_per_customer": "1",
            "reservation_ttl_hours": "24",
            "images": _big_jpeg(),
        },
    )
    _attach(req, user)
    assert views.promotion_edit(req, pk=promo.pk).status_code == 302
    promo.refresh_from_db()
    assert len(promo.images) == 1
    assert promo.images[0]["size"] <= 5 * 1024 * 1024


@pytest.mark.django_db
def test_photo_survives_a_field_error_on_edit(user):
    promo = PromotionFactory()
    req = RequestFactory().post(
        f"/promotions/{promo.pk}/edit/",
        {
            "title_de": "A",
            "promo_type": "reservation",
            "max_per_customer": "not-a-number",  # ошибка в поле
            "reservation_ttl_hours": "24",
            "images": _png(),
        },
    )
    _attach(req, user)
    resp = views.promotion_edit(req, pk=promo.pk)
    assert resp.status_code == 200  # форма вернулась с ошибкой
    promo.refresh_from_db()
    assert len(promo.images) == 1, "выбранное фото не должно пропасть вместе с ошибкой"
