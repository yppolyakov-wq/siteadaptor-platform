"""A5a: сезонные/выходные тарифы — pricing.quote_total + сохранение в брони."""

from datetime import date

import pytest

from apps.stays import pricing
from apps.stays.models import SeasonRate, StayBooking, StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db


def _unit(**kw):
    defaults = {"name": "Zimmer", "quantity": 1, "price_cents": 10000, "max_guests": 4}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def test_base_price_when_no_rates():
    unit = _unit(price_cents=10000)
    # Mo–Do (2026-06-15 = Montag), 3 ночи × 100 €
    total = pricing.quote_total_cents(unit, date(2026, 6, 15), date(2026, 6, 18))
    assert total == 30000


def test_weekend_surcharge_applies_to_fri_sat():
    unit = _unit(price_cents=10000, weekend_price_cents=15000)
    # 2026-06-19 Fr, 20 Sa, 21 So → ночи Fr,Sa,So; выходная цена на Fr+Sa
    total = pricing.quote_total_cents(unit, date(2026, 6, 19), date(2026, 6, 22))
    assert total == 15000 + 15000 + 10000  # Fr+Sa weekend, So base


def test_season_rate_overrides_base_and_weekend():
    unit = _unit(price_cents=10000, weekend_price_cents=15000)
    SeasonRate.objects.create(
        unit=unit, start_date=date(2026, 12, 20), end_date=date(2026, 12, 31), price_cents=20000
    )
    # 2 ночи в сезоне (вкл. выходные) → сезон перебивает всё
    total = pricing.quote_total_cents(unit, date(2026, 12, 25), date(2026, 12, 27))
    assert total == 40000


def test_book_stay_stores_total_with_rates():
    unit = _unit(price_cents=10000, weekend_price_cents=15000)
    booking = book_stay(
        unit, arrival=date(2026, 6, 19), departure=date(2026, 6, 21), name="K", email="k@test.de"
    )
    # Fr+Sa = 2×150 €
    assert booking.total_cents == 30000
    assert StayBooking.objects.get(pk=booking.pk).total_cents == 30000
