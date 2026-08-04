"""P4 «ценовой слой»: акции на номера — кандидат авто-скидки + лимит (2026-08-03)."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions import price_layer
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.stays import services as stay_services
from apps.stays.models import StayBooking, StaySettings, StayUnit
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db


def _unit(price_cents=10000):
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=price_cents)


def _stay_promo(unit, percent=20, quantity=5, rules=None):
    promo = PromotionFactory(product=None, available_quantity=quantity)
    Promotion.objects.filter(pk=promo.pk).update(
        status="active",
        stay_unit=unit,
        discount_percent=percent,
        target_rules=rules or {},
    )
    promo.refresh_from_db()
    return promo


def _book(unit, days_ahead=7, nights=2, **kw):
    arrival = timezone.localdate() + timedelta(days=days_ahead)
    return stay_services.book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=nights),
        name="Gast",
        email="g@t.de",
        **kw,
    )


def test_stay_promo_wins_and_claims_campaign_limit():
    unit = _unit()
    promo = _stay_promo(unit, percent=20, quantity=5)
    booking = _book(unit, nights=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 4
    assert booking.promotion_id == promo.pk
    assert booking.auto_discount_cents == 4000  # 20% от 2 ночей × 100 €
    assert "Aktion −20%" in booking.auto_discount_label


def test_bigger_g4_rule_beats_promo_and_limit_untouched():
    """Правила не суммируются — побеждает больший процент; проигравшая акция
    лимит НЕ тратит."""
    unit = _unit()
    promo = _stay_promo(unit, percent=10, quantity=5)
    settings = StaySettings.load()
    settings.auto_discount_rules = [{"kind": "los", "threshold": 2, "percent": 30}]
    settings.save()
    booking = _book(unit, nights=2)
    promo.refresh_from_db()
    assert promo.available_quantity == 5  # акция проиграла — лимит цел
    assert booking.promotion_id is None
    assert booking.auto_discount_cents == 6000  # 30% LOS


def test_stay_window_rules_gate_arrival():
    unit = _unit()
    far = (timezone.localdate() + timedelta(days=30)).isoformat()
    promo = _stay_promo(unit, rules={"stay_from": far})
    booking = _book(unit, days_ahead=7)  # заезд ДО окна акции
    promo.refresh_from_db()
    assert promo.available_quantity == 5
    assert booking.promotion_id is None and booking.auto_discount_cents == 0


def test_exhausted_limit_rolls_back_whole_booking():
    unit = _unit()
    promo = _stay_promo(unit, quantity=0)  # лимит уже исчерпан
    with pytest.raises(price_layer.OutOfStock):
        _book(unit)
    assert StayBooking.objects.count() == 0  # брони нет — атомарный откат
    promo.refresh_from_db()
    assert promo.available_quantity == 0


def test_cancel_returns_campaign_limit_once():
    unit = _unit()
    promo = _stay_promo(unit, quantity=5)
    booking = _book(unit)
    StayBookingSM().apply(booking, StayBooking.STATUS_CONFIRMED)
    StayBookingSM().apply(booking, StayBooking.STATUS_CANCELLED)
    promo.refresh_from_db()
    assert promo.available_quantity == 5
