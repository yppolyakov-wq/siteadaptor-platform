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


def test_multi_season_booking_prices_each_night(  # noqa: D103
):
    """Фидбэк владельца 2026-07-30: бронь через 2+ сезона считается ПОНОЧНО —
    каждая ночь берёт свой сезон (не один сезон по дате заезда)."""
    unit = _unit(price_cents=10000, weekend_price_cents=0)
    SeasonRate.objects.create(  # Nebensaison
        unit=unit, start_date=date(2026, 12, 1), end_date=date(2026, 12, 23), price_cents=8000
    )
    SeasonRate.objects.create(  # Weihnachten/Hochsaison
        unit=unit, start_date=date(2026, 12, 24), end_date=date(2027, 1, 6), price_cents=20000
    )
    # 22.12 → 27.12: ночи 22,23 (Neben 80 €) + 24,25,26 (Hoch 200 €)
    total = pricing.quote_total_cents(unit, date(2026, 12, 22), date(2026, 12, 27))
    assert total == 8000 * 2 + 20000 * 3


def test_booking_spanning_season_and_base_price():
    """Часть ночей в сезоне, часть — вне: вне сезона действует базовая цена."""
    unit = _unit(price_cents=10000, weekend_price_cents=0)
    SeasonRate.objects.create(
        unit=unit, start_date=date(2026, 7, 1), end_date=date(2026, 7, 3), price_cents=15000
    )
    # 30.06 → 04.07: ночи 30.06 (база), 01,02,03.07 (сезон)
    total = pricing.quote_total_cents(unit, date(2026, 6, 30), date(2026, 7, 4))
    assert total == 10000 + 15000 * 3


def test_price_breakdown_lists_every_night_with_source():
    """Разбивка «за что платим»: строка на ночь + пометка сезона/выходных."""
    unit = _unit(price_cents=10000, weekend_price_cents=15000)
    SeasonRate.objects.create(
        unit=unit,
        label="Hochsaison",
        start_date=date(2026, 12, 24),
        end_date=date(2026, 12, 31),
        price_cents=20000,
    )
    rows = pricing.price_breakdown(unit, date(2026, 12, 23), date(2026, 12, 26))
    assert [r["cents"] for r in rows] == [10000, 20000, 20000]
    assert rows[0]["label"] == ""  # 23.12 — базовая цена (Mi)
    assert rows[1]["label"] == "Hochsaison" and rows[2]["label"] == "Hochsaison"
    assert sum(r["cents"] for r in rows) == pricing.quote_total_cents(
        unit, date(2026, 12, 23), date(2026, 12, 26)
    )


def test_book_stay_stores_total_with_rates():
    unit = _unit(price_cents=10000, weekend_price_cents=15000)
    booking = book_stay(
        unit, arrival=date(2026, 6, 19), departure=date(2026, 6, 21), name="K", email="k@test.de"
    )
    # Fr+Sa = 2×150 €
    assert booking.total_cents == 30000
    assert StayBooking.objects.get(pk=booking.pk).total_cents == 30000


def test_stay_to_invoice_backs_out_gross_to_net():
    from apps.finance.models import Invoice
    from apps.stays.services import stay_to_invoice

    unit = _unit(price_cents=10700)  # 107 € брутто/ночь
    booking = book_stay(
        unit, arrival=date(2026, 6, 15), departure=date(2026, 6, 16), name="K", email="k@test.de"
    )
    inv = stay_to_invoice(booking)
    # 107 € брутто при 7 % → нетто 100, НДС 7
    assert inv.gross == 107
    assert inv.net == 100
    assert inv.vat_amount == 7
    assert inv.vat_rate == 7
    assert inv.status == Invoice.STATUS_DRAFT
    booking.refresh_from_db()
    assert booking.invoice_id == inv.id


def test_stay_to_invoice_is_idempotent():
    from apps.stays.services import stay_to_invoice

    unit = _unit(price_cents=9000)
    booking = book_stay(
        unit, arrival=date(2026, 7, 1), departure=date(2026, 7, 3), name="K", email="k@test.de"
    )
    first = stay_to_invoice(booking)
    second = stay_to_invoice(booking)
    assert first.id == second.id


def test_stay_to_invoice_small_business_no_vat():
    from apps.stays.services import stay_to_invoice

    unit = _unit(price_cents=10000)
    booking = book_stay(
        unit, arrival=date(2026, 8, 1), departure=date(2026, 8, 2), name="K", email="k@test.de"
    )
    inv = stay_to_invoice(booking, small_business=True)
    assert inv.gross == 100 and inv.net == 100 and inv.vat_amount == 0 and inv.vat_rate == 0
