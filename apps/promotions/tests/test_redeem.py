"""Тесты погашения брони (Einlösen) и персонального QR."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views, views
from apps.promotions.models import Reservation
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory


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
def test_redeem_home_requires_login():
    req = _attach(RequestFactory().get("/promotions/redeem/"), AnonymousUser())
    assert views.redeem_home(req).status_code in (301, 302)


@pytest.mark.django_db
def test_redeem_manual_code_redirects(user):
    req = _attach(RequestFactory().post("/promotions/redeem/", {"code": "r-abc123"}), user)
    resp = views.redeem_home(req)
    assert resp.status_code == 302
    assert resp.url.endswith("/redeem/R-ABC123/")  # нормализуем в верхний регистр


@pytest.mark.django_db
def test_redeem_detail_shows_reservation(user):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Ann", email="a@test.de")
    req = _attach(RequestFactory().get("/"), user)
    resp = views.redeem_detail(req, code=res.reference_code)
    assert resp.status_code == 200
    assert res.reference_code.encode() in resp.content


@pytest.mark.django_db
def test_redeem_action_fulfills(user):
    promo = PromotionFactory(available_quantity=5, auto_confirm=True)
    res = reserve(promo, name="Bob", email="b@test.de")  # confirmed
    req = _attach(
        RequestFactory().post(
            f"/promotions/redeem/{res.reference_code}/action/", {"action": "fulfill"}
        ),
        user,
    )
    resp = views.redeem_action(req, code=res.reference_code)
    assert resp.status_code == 302
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"


@pytest.mark.django_db
def test_reservation_qr_returns_svg(user):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Cara", email="c@test.de")
    resp = public_views.reservation_qr(RequestFactory().get("/"), code=res.reference_code)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/svg+xml"
    assert b"<svg" in resp.content
