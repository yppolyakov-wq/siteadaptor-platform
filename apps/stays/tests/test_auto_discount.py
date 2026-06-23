"""G4: авто-скидки на проживание (LOS / Frühbucher / Last-Minute)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.stays import pricing
from apps.stays.models import StayBooking, StaySettings, StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db


def _unit(**kw):
    defaults = {"name": "Zimmer", "quantity": 1, "price_cents": 10000, "max_guests": 4}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def _settings(**kw):
    s = StaySettings.load()
    for k, v in kw.items():
        setattr(s, k, v)
    s.save()
    return s


def test_los_discount_applies_from_threshold():
    _settings(los_min_nights=7, los_discount_percent=10)
    far = date(2030, 6, 1)
    cents, label = pricing.auto_discount(70000, 7, far, today=date(2030, 1, 1))
    assert cents == 7000 and label
    # ниже порога — без скидки
    assert pricing.auto_discount(60000, 6, far, today=date(2030, 1, 1)) == (0, "")


def test_early_bird_discount_by_lead_time():
    _settings(early_bird_days=30, early_bird_percent=8)
    today = date(2030, 1, 1)
    arrival = today + timedelta(days=40)
    cents, label = pricing.auto_discount(10000, 2, arrival, today=today)
    assert cents == 800 and "Frühbucher" in label
    # заезд скоро — раннее бронирование не действует
    assert pricing.auto_discount(10000, 2, today + timedelta(days=10), today=today) == (0, "")


def test_last_minute_discount_by_lead_time():
    _settings(last_minute_days=3, last_minute_percent=12)
    today = date(2030, 1, 1)
    cents, label = pricing.auto_discount(10000, 2, today + timedelta(days=2), today=today)
    assert cents == 1200 and "Last-Minute" in label


def test_takes_max_when_several_apply():
    _settings(
        los_min_nights=7,
        los_discount_percent=10,
        last_minute_days=3,
        last_minute_percent=20,
    )
    today = date(2030, 1, 1)
    # 7 ночей (LOS 10 %) и заезд через 2 дня (Last-Minute 20 %) → берём 20 %
    cents, label = pricing.auto_discount(100000, 7, today + timedelta(days=2), today=today)
    assert cents == 20000 and "Last-Minute" in label


def test_no_settings_no_discount():
    assert pricing.auto_discount(50000, 10, date(2030, 6, 1), today=date(2030, 1, 1)) == (0, "")


def test_book_stay_applies_and_stores_auto_discount():
    _settings(los_min_nights=2, los_discount_percent=10)
    unit = _unit(price_cents=10000)  # 100 €/ночь, будни
    # 2 ночи Mo→Mi далеко в будущем (раннее/last-minute не настроены)
    arrival = timezone.localdate() + timedelta(days=120)
    while arrival.weekday() != 0:  # Montag — без weekend-наценки
        arrival += timedelta(days=1)
    booking = book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="K", email="k@test.de"
    )
    # room 200 € − 10 % = 180 €
    assert booking.auto_discount_cents == 2000
    assert booking.auto_discount_label
    assert booking.total_cents == 18000
    assert StayBooking.objects.get(pk=booking.pk).total_cents == 18000


def test_book_stay_no_discount_when_off():
    unit = _unit(price_cents=10000)
    arrival = timezone.localdate() + timedelta(days=120)
    while arrival.weekday() != 0:
        arrival += timedelta(days=1)
    booking = book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="K", email="k@test.de"
    )
    assert booking.auto_discount_cents == 0 and booking.total_cents == 20000
