"""P3 «ценовой слой»: акции на услуги — правила и чекаут бронью (2026-08-03)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Booking, Resource, Service
from apps.booking.state_machine import BookingSM
from apps.promotions import price_layer
from apps.promotions.models import Promotion
from apps.promotions.services import OutOfStock
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _aware(hour, weekday_shift=0):
    base = timezone.localtime(timezone.now()) + timedelta(days=1 + weekday_shift)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


def _service_promo(service, rules=None, quantity=5, price="19.00"):
    promo = PromotionFactory(
        product=None,
        available_quantity=quantity,
        price_override=Decimal(price),
    )
    Promotion.objects.filter(pk=promo.pk).update(
        status="active", service=service, target_rules=rules or {}
    )
    promo.refresh_from_db()
    return promo


def test_rules_match_weekday_hours_and_resource():
    start = _aware(11)
    wd = timezone.localtime(start).weekday()
    assert price_layer.rules_match({}, start)
    assert price_layer.rules_match({"weekdays": [wd]}, start)
    assert not price_layer.rules_match({"weekdays": [(wd + 1) % 7]}, start)
    assert price_layer.rules_match({"hour_from": 10, "hour_to": 14}, start)
    assert not price_layer.rules_match({"hour_from": 14, "hour_to": 16}, start)
    # окно «через полночь»: 22–02
    assert price_layer.rules_match({"hour_from": 22, "hour_to": 2}, _aware(23))
    assert not price_layer.rules_match({"hour_from": 22, "hour_to": 2}, _aware(12))
    assert price_layer.rules_match({"resource_id": "42"}, start, resource_id=42)
    assert not price_layer.rules_match({"resource_id": "42"}, start, resource_id=7)
    # мусор в правилах = fail-closed (промо-цену по ошибке не раздаём)
    assert not price_layer.rules_match({"hour_from": "kaputt"}, start)


def test_promo_for_service_picks_best_price_inside_window():
    service = Service.objects.create(name="Haarschnitt", price_cents=3500)
    _service_promo(service, price="25.00")
    best = _service_promo(service, price="19.00")
    found = price_layer.promo_for_service(service, _aware(11))
    assert found is not None
    promo, cents = found
    assert promo.pk == best.pk and cents == 1900
    # вне окна правил — акции нет
    wd = timezone.localtime(_aware(11)).weekday()
    Promotion.objects.filter(pk=best.pk).update(target_rules={"weekdays": [(wd + 1) % 7]})
    found2 = price_layer.promo_for_service(service, _aware(11))
    assert found2 is not None and found2[1] == 2500  # остался только дорогой


def test_purchase_service_books_slot_and_claims_limit():
    service = Service.objects.create(name="Massage", price_cents=6000)
    resource = Resource.objects.create(name="Kabine 1")
    promo = _service_promo(service, quantity=5, price="39.00")
    start = _aware(11)
    booking = price_layer.purchase_service(
        promo, resource=resource, start=start, end=start + timedelta(hours=1), name="Anna"
    )
    promo.refresh_from_db()
    assert promo.available_quantity == 4
    assert booking.price_cents == 3900  # промо-цена заморожена в брони
    assert booking.promotion_id == promo.pk
    assert booking.service_id == service.pk


def test_taken_slot_rolls_back_campaign_limit():
    """Слот занят → SlotTaken отменяет и списание лимита (одна транзакция)."""
    service = Service.objects.create(name="Massage", price_cents=6000)
    resource = Resource.objects.create(name="Kabine 1")
    promo = _service_promo(service, quantity=5)
    start = _aware(11)
    booking_services.book(
        resource, start=start, end=start + timedelta(hours=1), name="Erste", auto_confirm=True
    )
    with pytest.raises(booking_services.SlotTaken):
        price_layer.purchase_service(
            promo, resource=resource, start=start, end=start + timedelta(hours=1), name="Anna"
        )
    promo.refresh_from_db()
    assert promo.available_quantity == 5  # фантомного списания нет


def test_purchase_outside_rules_refused():
    service = Service.objects.create(name="Massage", price_cents=6000)
    resource = Resource.objects.create(name="Kabine 1")
    start = _aware(11)
    wd = timezone.localtime(start).weekday()
    promo = _service_promo(service, rules={"weekdays": [(wd + 1) % 7]})
    with pytest.raises(OutOfStock):
        price_layer.purchase_service(
            promo, resource=resource, start=start, end=start + timedelta(hours=1), name="Anna"
        )
    promo.refresh_from_db()
    assert promo.available_quantity == 5


def test_cancel_returns_campaign_limit_once():
    service = Service.objects.create(name="Massage", price_cents=6000)
    resource = Resource.objects.create(name="Kabine 1")
    promo = _service_promo(service, quantity=5)
    start = _aware(11)
    booking = price_layer.purchase_service(
        promo, resource=resource, start=start, end=start + timedelta(hours=1), name="Anna"
    )
    BookingSM().apply(booking, Booking.STATUS_CONFIRMED)
    BookingSM().apply(booking, Booking.STATUS_CANCELLED)
    promo.refresh_from_db()
    assert promo.available_quantity == 5  # вернулось ровно один раз


def test_no_show_keeps_campaign_limit():
    """No-show: слот потрачен — лимит кампании НЕ возвращается (рыночная норма)."""
    service = Service.objects.create(name="Massage", price_cents=6000)
    resource = Resource.objects.create(name="Kabine 1")
    promo = _service_promo(service, quantity=5)
    start = _aware(11)
    booking = price_layer.purchase_service(
        promo, resource=resource, start=start, end=start + timedelta(hours=1), name="Anna"
    )
    BookingSM().apply(booking, Booking.STATUS_CONFIRMED)
    BookingSM().apply(booking, Booking.STATUS_NO_SHOW)
    promo.refresh_from_db()
    assert promo.available_quantity == 4
