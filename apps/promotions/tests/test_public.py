"""Тесты публичной витрины брони (без логина)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Reservation
from apps.promotions.tests.factories import PromotionFactory


def _req(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request


@pytest.mark.django_db
def test_promotion_qr_returns_svg():
    promo = PromotionFactory(status="active")
    resp = public_views.promotion_qr(_req(RequestFactory().get("/")), pk=promo.pk)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/svg+xml"
    assert b"<svg" in resp.content


def test_set_language_sets_cookie():
    from django.conf import settings

    resp = public_views.set_language(RequestFactory().get("/lang/", {"lang": "en"}))
    assert resp.status_code == 302
    assert resp.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"


@pytest.mark.django_db
def test_storefront_home_lists_active():
    PromotionFactory(status="active", title={"de": "Sommeraktion"})
    PromotionFactory(status="draft", title={"de": "Versteckt"})
    resp = public_views.storefront_home(_req(RequestFactory().get("/")))
    assert resp.status_code == 200
    assert b"Sommeraktion" in resp.content
    assert b"Versteckt" not in resp.content  # черновик не показываем


@pytest.mark.django_db
def test_promotion_detail_active():
    promo = PromotionFactory(status="active")
    resp = public_views.promotion_detail(_req(RequestFactory().get("/p/x/")), pk=promo.pk)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_reserve_creates_and_redirects():
    promo = PromotionFactory(status="active", available_quantity=5, auto_confirm=False)
    req = _req(
        RequestFactory().post(
            f"/p/{promo.pk}/reserve/",
            {"name": "Anna", "email": "anna@test.de", "quantity": "2", "form_token": "tok1"},
        )
    )
    resp = public_views.reservation_create(req, pk=promo.pk)
    assert resp.status_code == 302
    assert resp.url.startswith("/r/")
    res = Reservation.objects.get()
    assert res.quantity == 2
    assert res.status == "pending"
    promo.refresh_from_db()
    assert promo.available_quantity == 3


@pytest.mark.django_db
def test_reserve_honeypot_silently_ignored():
    promo = PromotionFactory(status="active", available_quantity=5)
    req = _req(
        RequestFactory().post(
            f"/p/{promo.pk}/reserve/",
            {"name": "Bot", "quantity": "1", "website": "http://spam", "form_token": "t"},
        )
    )
    resp = public_views.reservation_create(req, pk=promo.pk)
    assert resp.status_code == 302
    assert Reservation.objects.count() == 0  # бронь не создана


@pytest.mark.django_db
def test_reserve_duplicate_token_blocked():
    promo = PromotionFactory(status="active", available_quantity=5)
    data = {"name": "Eva", "quantity": "1", "form_token": "dup"}
    public_views.reservation_create(
        _req(RequestFactory().post(f"/p/{promo.pk}/reserve/", data)), pk=promo.pk
    )
    # повторная отправка с тем же токеном — дубль
    public_views.reservation_create(
        _req(RequestFactory().post(f"/p/{promo.pk}/reserve/", data)), pk=promo.pk
    )
    assert Reservation.objects.count() == 1


@pytest.mark.django_db
def test_reserve_out_of_stock_message():
    promo = PromotionFactory(status="active", available_quantity=0)
    req = _req(
        RequestFactory().post(
            f"/p/{promo.pk}/reserve/",
            {"name": "X", "quantity": "1", "form_token": "t2"},
        )
    )
    resp = public_views.reservation_create(req, pk=promo.pk)
    assert resp.status_code == 200  # ре-рендер с сообщением
    assert Reservation.objects.count() == 0
