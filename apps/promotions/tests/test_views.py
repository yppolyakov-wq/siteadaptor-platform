"""Тесты вьюх кабинета (RequestFactory — TenantMainMiddleware форсит public urlconf)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import views
from apps.promotions.models import Promotion, Reservation
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
        username="owner", email="owner@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_promotion_list_requires_login():
    req = _attach(RequestFactory().get("/promotions/"), AnonymousUser())
    resp = views.promotion_list(req)
    assert resp.status_code in (301, 302)


@pytest.mark.django_db
def test_create_promotion(user):
    req = _attach(
        RequestFactory().post(
            "/promotions/new/",
            {
                "title_de": "Sommer",
                "title_en": "",
                "description_de": "",
                "description_en": "",
                "promo_type": "reservation",
                "available_quantity": "20",
                "max_per_customer": "2",
                "reservation_ttl_hours": "24",
            },
        ),
        user,
    )
    resp = views.promotion_create(req)
    assert resp.status_code == 302
    promo = Promotion.objects.get()
    assert promo.title["de"] == "Sommer"
    assert promo.status == "draft"  # новая акция — черновик


@pytest.mark.django_db
def test_promotion_transition(user):
    promo = PromotionFactory(status="draft")
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/transition/", {"target": "active"}), user
    )
    resp = views.promotion_transition(req, pk=promo.pk)
    assert resp.status_code == 302
    promo.refresh_from_db()
    assert promo.status == "active"


@pytest.mark.django_db
def test_promotion_illegal_transition_keeps_status(user):
    promo = PromotionFactory(status="ended")
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/transition/", {"target": "active"}), user
    )
    views.promotion_transition(req, pk=promo.pk)
    promo.refresh_from_db()
    assert promo.status == "ended"  # нелегальный переход проигнорирован


@pytest.mark.django_db
def test_reservation_confirm_action(user):
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="Ann", email="ann@test.de")
    assert res.status == "pending"
    req = _attach(
        RequestFactory().post(f"/promotions/reservations/{res.pk}/action/", {"action": "confirm"}),
        user,
    )
    resp = views.reservation_action(req, pk=res.pk)
    assert resp.status_code == 302
    assert Reservation.objects.get(pk=res.pk).status == "confirmed"


@pytest.mark.django_db
def test_reservation_list_filters_by_status(user):
    promo = PromotionFactory(available_quantity=5, auto_confirm=True)
    reserve(promo, name="A", email="a@test.de")  # confirmed
    req = _attach(RequestFactory().get("/promotions/reservations/", {"status": "confirmed"}), user)
    resp = views.reservation_list(req)
    assert resp.status_code == 200
    assert b"confirmed" in resp.content
