"""2026-11-09: честная «ab … / Nacht» номера для каталога города (stays.from_price).

Замки: цена — тем же расчётом, что «ab» витрины отеля; дешёвый день со стоп-продажей
не участвует; цена по дням и сезон ниже базы опускают «ab»; минимальный срок считается
целиком; ничего не забронировать → None (портал показывает номер без цены);
запросы не растут с горизонтом линейно сверх разумного."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aggregator import tasks
from apps.stays import pricing, public_views
from apps.stays.from_price import lowest_nightly_cents
from apps.stays.models import NightRate, SeasonRate, StayUnit, UnitBlock

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 1)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kw)


def _d(n):
    return TODAY + timedelta(days=n)


def test_base_price_when_nothing_else_is_set():
    assert lowest_nightly_cents(_unit(), today=TODAY) == 10000


def test_storefront_and_portal_share_one_formula():
    unit = _unit()
    SeasonRate.objects.create(unit=unit, start_date=_d(3), end_date=_d(5), price_cents=7000)
    assert public_views._unit_from_price_cents(unit, _d(3), _d(5), []) == (
        pricing.from_price_cents(unit, _d(3), _d(5), [])
    )


def test_cheaper_season_lowers_the_from_price():
    unit = _unit()
    SeasonRate.objects.create(unit=unit, start_date=_d(10), end_date=_d(20), price_cents=6000)
    assert lowest_nightly_cents(unit, today=TODAY) == 6000


def test_day_price_lowers_and_stop_sell_day_is_skipped():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(5), price_cents=5000)
    NightRate.objects.create(unit=unit, day=_d(8), price_cents=3000, stop_sell=True)
    assert lowest_nightly_cents(unit, today=TODAY) == 5000


def test_minimum_stay_is_priced_as_a_whole_and_rounded_up():
    unit = _unit(min_nights=3)
    NightRate.objects.create(unit=unit, day=_d(5), price_cents=1)
    # лучший заезд держит дешёвую ночь + две по 100 € → (1 + 20000) / 3, вверх
    assert lowest_nightly_cents(unit, today=TODAY) == 6667


def test_fully_booked_unit_has_no_price_and_listing_shows_none():
    unit = _unit()
    UnitBlock.objects.create(unit=unit, start_date=_d(0), end_date=_d(120))
    assert lowest_nightly_cents(unit, today=TODAY) is None
    snap = tasks._stay_snapshot(unit.id)
    assert snap is not None and snap["new_price"] is None  # номер в каталоге, без цены


def test_snapshot_uses_honest_price_and_translations():
    unit = _unit(description="<p>Ruhig &amp; hell</p>", name_i18n={"en": "Room"})
    SeasonRate.objects.create(unit=unit, start_date=_d(2), end_date=_d(4), price_cents=8000)
    snap = tasks._stay_snapshot(unit.id)
    assert str(snap["new_price"]) == "80"
    assert snap["title"]["en"] == "Room" and snap["teaser"]["de"] == "Ruhig & hell"


def test_query_count_is_bounded(django_assert_max_num_queries):
    """Свободный номер на 60 дней: ~5 запросов на заезд (цена дня, наличие, акция) —
    настройки читаются ОДИН раз (StaySettings.memo); было 484 запроса."""
    unit = StayUnit.objects.prefetch_related("season_rates").get(pk=_unit().pk)
    with django_assert_max_num_queries(320):
        lowest_nightly_cents(unit, today=TODAY)


def test_settings_memo_does_not_leak_outside_the_calculation():
    from apps.stays.models import StaySettings

    unit = _unit()
    lowest_nightly_cents(unit, today=TODAY)
    obj = StaySettings.load()
    obj.kurtaxe_cents = 333
    obj.save()
    assert StaySettings.load().kurtaxe_cents == 333  # вне memo — свежее чтение


def test_season_or_booking_change_schedules_one_reprice(django_capture_on_commit_callbacks):
    from unittest import mock

    from django.db import connection

    unit = _unit()
    with mock.patch.object(connection, "schema_name", "t_hotel"):
        with mock.patch.object(tasks.reprice_stay_listings, "apply_async") as send:
            with django_capture_on_commit_callbacks(execute=True):
                SeasonRate.objects.create(
                    unit=unit, start_date=_d(1), end_date=_d(2), price_cents=9000
                )
                UnitBlock.objects.create(unit=unit, start_date=_d(3), end_date=_d(3))
    keys = {c.kwargs["kwargs"]["dedupe_key"] for c in send.call_args_list}
    assert send.called and len(keys) == 1  # обе правки окна — один проход
    assert send.call_args.kwargs["countdown"] == 30
