"""Тесты атрибуции источника (канальный QR)."""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Reservation
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory


@pytest.mark.django_db
def test_reserve_records_source_channel():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="A", email="a@test.de", source_channel="instagram")
    assert res.source_channel == "instagram"


@pytest.mark.django_db
def test_channel_qr_encodes_ch_param():
    promo = PromotionFactory(status="active")
    req = RequestFactory().get("/", {"ch": "flyer"})
    resp = public_views.promotion_qr(req, pk=promo.pk)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/svg+xml"


@pytest.mark.django_db
def test_capture_channel_persists_in_session():
    req = RequestFactory().get("/", {"ch": "schaufenster"})
    req.session = {}
    assert public_views._capture_channel(req) == "schaufenster"
    assert req.session["src_ch"] == "schaufenster"
    # без ?ch берём из сессии
    req2 = RequestFactory().get("/")
    req2.session = {"src_ch": "schaufenster"}
    assert public_views._capture_channel(req2) == "schaufenster"


@pytest.mark.django_db
def test_reservation_default_channel_is_empty():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="B", email="b@test.de")
    assert res.source_channel == ""
    assert Reservation.objects.filter(source_channel="").count() == 1
