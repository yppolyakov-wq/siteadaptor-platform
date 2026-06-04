"""Тесты авто-погашения по скану (настройка бизнеса)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import views
from apps.promotions.models import Reservation, Voucher
from apps.promotions.services import generate_vouchers, reserve
from apps.promotions.tests.factories import PromotionFactory


class _Tenant:
    def __init__(self, auto):
        self.auto_redeem_on_scan = auto


def _req(auto, user):
    r = RequestFactory().get("/")
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.user = user
    r.tenant = _Tenant(auto)
    return r


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_reservation_auto_fulfilled_on_scan(user):
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="A", email="a@test.de")  # pending
    views.redeem_detail(_req(True, user), code=res.reference_code)
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"


@pytest.mark.django_db
def test_reservation_not_auto_when_disabled(user):
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="B", email="b@test.de")
    views.redeem_detail(_req(False, user), code=res.reference_code)
    assert Reservation.objects.get(pk=res.pk).status == "pending"


@pytest.mark.django_db
def test_voucher_auto_redeemed_on_scan(user):
    v = generate_vouchers(label="−10 %", count=1, max_uses=1)[0]
    r = RequestFactory().get("/", {"code": v.code})
    SessionMiddleware(lambda x: None).process_request(r)
    MessageMiddleware(lambda x: None).process_request(r)
    r.user = user
    r.tenant = _Tenant(True)
    views.voucher_redeem(r)
    assert Voucher.objects.get(pk=v.pk).used_count == 1
