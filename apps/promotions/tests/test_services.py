"""Тесты сервисов резервирования (happy-path, лимиты, возврат остатка)."""

import pytest

from apps.promotions.models import Reservation
from apps.promotions.services import (
    OutOfStock,
    ReservationLimitReached,
    cancel,
    confirm,
    reserve,
)
from apps.promotions.tests.factories import PromotionFactory


@pytest.mark.django_db
def test_reserve_decrements_stock_and_creates_pending():
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="Anna", email="anna@test.de", quantity=2)
    assert res.status == "pending"
    assert res.reference_code.startswith("R-")
    assert res.expires_at is not None
    promo.refresh_from_db()
    assert promo.available_quantity == 3


@pytest.mark.django_db
def test_reserve_auto_confirm():
    promo = PromotionFactory(available_quantity=5, auto_confirm=True)
    res = reserve(promo, name="Bob", email="bob@test.de", quantity=1)
    assert res.status == "confirmed"
    assert res.confirmed_at is not None


@pytest.mark.django_db
def test_reserve_out_of_stock():
    promo = PromotionFactory(available_quantity=1)
    with pytest.raises(OutOfStock):
        reserve(promo, name="X", email="x@test.de", quantity=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 1  # остаток не тронут


@pytest.mark.django_db
def test_reserve_inactive_promotion_rejected():
    promo = PromotionFactory(status="paused", available_quantity=5)
    with pytest.raises(OutOfStock):
        reserve(promo, name="X", email="x@test.de", quantity=1)


@pytest.mark.django_db
def test_max_per_customer_enforced():
    promo = PromotionFactory(available_quantity=10, max_per_customer=2)
    reserve(promo, name="Cara", email="cara@test.de", quantity=2)
    with pytest.raises(ReservationLimitReached):
        reserve(promo, name="Cara", email="cara@test.de", quantity=1)


@pytest.mark.django_db
def test_cancel_returns_stock_and_is_idempotent():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Dan", email="dan@test.de", quantity=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 3

    cancel(res)
    promo.refresh_from_db()
    assert promo.available_quantity == 5  # возврат
    assert Reservation.objects.get(pk=res.pk).status == "cancelled"

    cancel(res)  # повтор — без двойного возврата
    promo.refresh_from_db()
    assert promo.available_quantity == 5


@pytest.mark.django_db
def test_confirm_then_fulfill():
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="Eva", email="eva@test.de")
    confirm(res)
    res.refresh_from_db()
    assert res.status == "confirmed"
    assert res.confirmed_at is not None
