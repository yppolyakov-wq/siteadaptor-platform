"""Тесты переходов FSM Promotion/Reservation."""

import pytest

from apps.core.fsm import IllegalTransition
from apps.promotions.models import Reservation
from apps.promotions.state_machine import PromotionSM, ReservationSM
from apps.promotions.tests.factories import CustomerFactory, PromotionFactory


@pytest.mark.django_db
def test_promotion_legal_transition():
    promo = PromotionFactory(status="draft")
    PromotionSM().apply(promo, "scheduled")
    promo.refresh_from_db()
    assert promo.status == "scheduled"


@pytest.mark.django_db
def test_promotion_illegal_transition():
    promo = PromotionFactory(status="ended")
    with pytest.raises(IllegalTransition):
        PromotionSM().apply(promo, "active")


@pytest.mark.django_db
def test_reservation_same_status_is_noop():
    promo = PromotionFactory()
    res = Reservation.objects.create(
        promotion=promo, customer=CustomerFactory(), reference_code="R-AAAAAA", status="pending"
    )
    ReservationSM().apply(res, "pending")  # no-op, без исключения
    res.refresh_from_db()
    assert res.status == "pending"


@pytest.mark.django_db
def test_reservation_expire_returns_stock():
    promo = PromotionFactory(available_quantity=8)
    res = Reservation.objects.create(
        promotion=promo,
        customer=CustomerFactory(),
        reference_code="R-BBBBBB",
        status="confirmed",
        quantity=3,
    )
    ReservationSM().apply(res, "expired")
    promo.refresh_from_db()
    assert promo.available_quantity == 11  # 8 + 3 возвращено
