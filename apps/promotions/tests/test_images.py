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
