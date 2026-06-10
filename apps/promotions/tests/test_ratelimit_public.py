"""Hardening H8: rate-limit публичных эндпоинтов витрины.

«IP» в каждом тесте — uuid через X-Forwarded-For: счётчики в Redis живут
дольше теста (TTL 10 мин), уникальный идентификатор изолирует тесты и
повторные прогоны без очистки кэша.
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Reservation, WaitlistEntry
from apps.promotions.services import generate_vouchers
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _req(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def _ip():
    return uuid.uuid4().hex


def _post(path, data, ip):
    return _req(RequestFactory().post(path, data, HTTP_X_FORWARDED_FOR=ip))


def test_waitlist_blocked_after_limit():
    promo = PromotionFactory(status="active", available_quantity=0)
    ip = _ip()
    for i in range(public_views.RL_LIMIT):
        public_views.waitlist_join(
            _post(f"/p/{promo.pk}/waitlist/", {"email": f"u{i}@t.de"}, ip), pk=promo.pk
        )
    assert WaitlistEntry.objects.count() == public_views.RL_LIMIT

    resp = public_views.waitlist_join(
        _post(f"/p/{promo.pk}/waitlist/", {"email": "extra@t.de"}, ip), pk=promo.pk
    )
    assert resp.status_code == 302
    assert WaitlistEntry.objects.count() == public_views.RL_LIMIT  # сверх лимита — нет


def test_waitlist_limit_is_per_ip():
    promo = PromotionFactory(status="active", available_quantity=0)
    ip = _ip()
    for i in range(public_views.RL_LIMIT):
        public_views.waitlist_join(
            _post(f"/p/{promo.pk}/waitlist/", {"email": f"u{i}@t.de"}, ip), pk=promo.pk
        )
    # другой клиент не задет
    public_views.waitlist_join(
        _post(f"/p/{promo.pk}/waitlist/", {"email": "other@t.de"}, _ip()), pk=promo.pk
    )
    assert WaitlistEntry.objects.filter(email="other@t.de").exists()


def test_reserve_blocked_after_limit():
    promo = PromotionFactory(status="active", available_quantity=50)
    ip = _ip()
    for i in range(public_views.RL_LIMIT):
        public_views.reservation_create(
            _post(
                f"/p/{promo.pk}/reserve/",
                {
                    "name": f"N{i}",
                    "email": f"n{i}@t.de",
                    "quantity": "1",
                    "form_token": uuid.uuid4().hex,
                },
                ip,
            ),
            pk=promo.pk,
        )
    assert Reservation.objects.count() == public_views.RL_LIMIT

    resp = public_views.reservation_create(
        _post(
            f"/p/{promo.pk}/reserve/",
            {"name": "X", "email": "x@t.de", "quantity": "1", "form_token": uuid.uuid4().hex},
            ip,
        ),
        pk=promo.pk,
    )
    assert resp.status_code == 200  # ре-рендер с ошибкой, не редирект на бронь
    assert Reservation.objects.count() == public_views.RL_LIMIT


def test_voucher_qr_blocked_after_limit():
    voucher = generate_vouchers(label="−10 %", count=1, max_uses=1)[0]
    ip = _ip()
    for _ in range(public_views.QR_RL_LIMIT):
        resp = public_views.voucher_qr(
            _req(RequestFactory().get("/", HTTP_X_FORWARDED_FOR=ip)), code=voucher.code
        )
        assert resp.status_code == 200
    resp = public_views.voucher_qr(
        _req(RequestFactory().get("/", HTTP_X_FORWARDED_FOR=ip)), code=voucher.code
    )
    assert resp.status_code == 429


def test_qr_limit_shared_across_qr_views():
    """Перебор не обойти, чередуя вьюхи: scope «qr» общий."""
    voucher = generate_vouchers(label="−10 %", count=1, max_uses=1)[0]
    ip = _ip()
    for _ in range(public_views.QR_RL_LIMIT):
        public_views.voucher_qr(
            _req(RequestFactory().get("/", HTTP_X_FORWARDED_FOR=ip)), code=voucher.code
        )
    resp = public_views.reservation_qr(
        _req(RequestFactory().get("/", HTTP_X_FORWARDED_FOR=ip)), code="WHATEVER"
    )
    assert resp.status_code == 429
