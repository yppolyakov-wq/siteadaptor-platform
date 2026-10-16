"""Тесты beat-логики: просрочка броней и планировщик статусов акций.

Тестируем чистые helper'ы в текущей (public) схеме — обход схем арендаторов
в самих задачах тривиален.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions.models import Reservation
from apps.promotions.services import reserve
from apps.promotions.tasks import expire_due_reservations, roll_due_promotions
from apps.promotions.tests.factories import PromotionFactory


@pytest.mark.django_db
def test_expire_due_returns_stock():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="A", email="a@test.de", quantity=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 3

    # делаем бронь просроченной
    Reservation.objects.filter(pk=res.pk).update(expires_at=timezone.now() - timedelta(hours=1))

    n = expire_due_reservations()
    assert n == 1
    res.refresh_from_db()
    assert res.status == "expired"
    promo.refresh_from_db()
    assert promo.available_quantity == 5  # остаток вернулся


@pytest.mark.django_db
def test_expire_ignores_future_and_terminal():
    promo = PromotionFactory(available_quantity=5)
    fresh = reserve(promo, name="B", email="b@test.de", quantity=1)  # expires в будущем
    n = expire_due_reservations()
    assert n == 0
    fresh.refresh_from_db()
    assert fresh.status == "pending"


@pytest.mark.django_db
def test_roll_activates_scheduled():
    promo = PromotionFactory(
        status="scheduled", starts_at=timezone.now() - timedelta(minutes=1), ends_at=None
    )
    out = roll_due_promotions()
    assert out["activated"] == 1
    promo.refresh_from_db()
    assert promo.status == "active"


@pytest.mark.django_db
def test_roll_ends_active():
    promo = PromotionFactory(status="active", ends_at=timezone.now() - timedelta(minutes=1))
    out = roll_due_promotions()
    assert out["ended"] == 1
    promo.refresh_from_db()
    assert promo.status == "ended"


@pytest.mark.django_db
def test_roll_skips_not_yet_started():
    promo = PromotionFactory(status="scheduled", starts_at=timezone.now() + timedelta(hours=1))
    out = roll_due_promotions()
    assert out["activated"] == 0
    promo.refresh_from_db()
    assert promo.status == "scheduled"


# --- Блок Е2: демо-акции не истекают ---------------------------------------------


@pytest.mark.django_db
def test_demo_promotion_is_extended_instead_of_ended(monkeypatch):
    from types import SimpleNamespace

    from apps.promotions import limits

    now = timezone.now()
    soon = now + timedelta(minutes=30)
    demo = PromotionFactory(status="active", ends_at=soon, metadata={"demo": True})
    own = PromotionFactory(status="active", ends_at=soon, metadata={})
    gone = PromotionFactory(status="active", ends_at=now - timedelta(minutes=1), metadata={})
    monkeypatch.setattr(limits, "tenant_for_current_schema", lambda: SimpleNamespace(is_demo=True))
    roll_due_promotions(now)
    demo.refresh_from_db()
    own.refresh_from_db()
    gone.refresh_from_db()
    assert demo.status == "active"
    assert demo.ends_at == soon + timedelta(days=1)  # время суток сохранено
    assert own.ends_at == soon  # владелец сам добавил акцию в демо — не трогаем
    assert gone.status == "ended"
    roll_due_promotions(now)  # идемпотентно: повтор ничего не сдвигает
    demo.refresh_from_db()
    assert demo.ends_at == soon + timedelta(days=1)


@pytest.mark.django_db
def test_demo_extension_only_for_demo_tenants(monkeypatch):
    from types import SimpleNamespace

    from apps.promotions import limits

    now = timezone.now()
    soon = now + timedelta(minutes=30)
    promo = PromotionFactory(status="active", ends_at=soon, metadata={"demo": True})
    monkeypatch.setattr(limits, "tenant_for_current_schema", lambda: SimpleNamespace(is_demo=False))
    roll_due_promotions(now)
    promo.refresh_from_db()
    assert promo.ends_at == soon
