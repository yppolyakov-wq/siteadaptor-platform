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
def test_landing_channel_is_read_but_not_written_to_session():
    """В5 V5-5 (решение владельца §13): посадка с ?ch= сессию НЕ пишет (TTDSG §25)."""
    req = RequestFactory().get("/", {"ch": "schaufenster"})
    req.session = {}
    assert public_views._channel(req) == "schaufenster"
    assert req.session == {}
    # корзинная сессия (attribution.remember) — читается в том же визите
    import time

    req2 = RequestFactory().get("/")
    req2.session = {"src_attr": {"ch": "schaufenster", "cl": "", "at": time.time()}}
    assert public_views._channel(req2) == "schaufenster"


@pytest.mark.django_db
def test_reservation_default_channel_is_empty():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="B", email="b@test.de")
    assert res.source_channel == ""
    assert Reservation.objects.filter(source_channel="").count() == 1
