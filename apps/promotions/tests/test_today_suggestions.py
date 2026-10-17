"""Д1-3 (T-8.10c): «Was heute starten?» — движок правил из своих данных, без ИИ.

План — docs/d1-ai-photo-promo-today-plan-2026-10-17.md §7 (замки 15–19, 23, 25)."""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.ai.providers import fake
from apps.catalog.models import Product
from apps.inventory.models import Lot
from apps.promotions import today as today_mod
from apps.promotions.models import Promotion, PromotionDailyView
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _tenant(**kw):
    kw.setdefault("site_config", {"lots_enabled": True})
    return TenantFactory.build(**kw)


def _product(name="Joghurt"):
    return Product.objects.create(name={"de": name}, base_price=Decimal("1.99"))


def _lot(product, days, qty=12):
    return Lot.objects.create(
        product=product, mhd=TODAY + timedelta(days=days), qty_received=qty, qty_remaining=qty
    )


def _rules(found, rule):
    return [s for s in found if s.rule == rule]


# --- R1 MHD -----------------------------------------------------------------------------


def test_mhd_lot_gives_rescue_deal_with_real_quantity_and_date():
    product = _product()
    _lot(product, 1, qty=12)
    [s] = _rules(today_mod.compute(_tenant()), "mhd")
    assert s.target == ("product", product.pk)
    assert s.initial["quantity"] == 12 and s.initial["until"] == TODAY + timedelta(days=1)
    assert s.initial["percent"] == today_mod.MHD_PERCENT_SOON and s.initial["perishable"]
    assert "12" in s.text


def test_mhd_rule_off_without_lots_or_with_running_promo():
    product = _product()
    _lot(product, 2)
    assert _rules(today_mod.compute(_tenant(site_config={})), "mhd") == []
    PromotionFactory(status="active", product=product)
    assert _rules(today_mod.compute(_tenant()), "mhd") == []


def test_far_mhd_and_expired_lots_ignored():
    product = _product()
    _lot(product, 10)
    _lot(product, -1)
    assert _rules(today_mod.compute(_tenant()), "mhd") == []


# --- R2 Termine morgen ------------------------------------------------------------------


def _service():
    from apps.booking.models import Service

    return Service.objects.create(name=f"Schnitt {uuid.uuid4().hex[:4]}", duration_minutes=30)


def _starts(*hours_minutes):
    tomorrow = TODAY + timedelta(days=1)
    return [timezone.make_aware(datetime.combine(tomorrow, time(h, m))) for h, m in hours_minutes]


def test_free_morning_slots_give_happy_hour_rules():
    service = _service()
    starts = _starts((10, 0), (10, 30), (11, 0), (11, 30), (15, 0))
    with mock.patch("apps.booking.availability.service_slots", return_value=starts):
        [s] = _rules(today_mod.compute(_tenant()), "slots")
    tomorrow = TODAY + timedelta(days=1)
    assert s.target == ("service", service.pk)
    assert s.target_rules == {"weekdays": [tomorrow.weekday()], "hour_from": 10, "hour_to": 12}
    assert s.initial["until"] == tomorrow


def test_scattered_slots_give_nothing():
    _service()
    with mock.patch(
        "apps.booking.availability.service_slots", return_value=_starts((9, 0), (13, 0))
    ):
        assert _rules(today_mod.compute(_tenant()), "slots") == []


def test_booking_module_off_no_slot_rule():
    _service()
    starts = _starts((10, 0), (10, 30), (11, 0))
    with mock.patch("apps.booking.availability.service_slots", return_value=starts):
        tenant = _tenant(disabled_modules=["booking"])
        assert _rules(today_mod.compute(tenant), "slots") == []


# --- R3 Lücken --------------------------------------------------------------------------


def test_short_gap_gives_last_minute_with_stay_window():
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name="Seeblick", price_cents=10000, max_guests=2)
    services.book_stay(
        unit, arrival=TODAY + timedelta(days=1), departure=TODAY + timedelta(days=3), name="A"
    )
    services.book_stay(
        unit, arrival=TODAY + timedelta(days=5), departure=TODAY + timedelta(days=7), name="B"
    )
    [s] = _rules(today_mod.compute(_tenant()), "gap")
    gap_start = (TODAY + timedelta(days=3)).isoformat()
    assert s.target == ("stay_unit", unit.pk)
    assert s.target_rules == {"stay_from": gap_start, "stay_to": gap_start}


# --- R4 Wiederholen ---------------------------------------------------------------------


def test_best_past_promotion_and_its_weekday():
    weak = PromotionFactory(status="ended", ends_at=timezone.now() - timedelta(days=3))
    strong = PromotionFactory(
        status="ended",
        title={"de": "Feierabend-Tüte"},
        ends_at=timezone.now() - timedelta(days=2),
    )
    friday = TODAY - timedelta(days=(TODAY.weekday() - 4) % 7 or 7)
    PromotionDailyView.objects.create(promotion=strong, day=friday, views=30)
    PromotionDailyView.objects.create(promotion=weak, day=friday, views=2)
    [s] = _rules(today_mod.compute(_tenant()), "repeat")
    assert s.action == "repeat" and f"von={strong.pk}" in s.url
    assert "Feierabend-Tüte" in s.text and "Freitag" in s.text


# --- общее -------------------------------------------------------------------------------


def test_failing_rule_does_not_break_the_others():
    product = _product()
    _lot(product, 1)
    with mock.patch.object(today_mod, "_rule_slots", side_effect=RuntimeError("boom")):
        with mock.patch.object(today_mod, "RULES", (today_mod._rule_mhd, today_mod._rule_slots)):
            found = today_mod.compute(_tenant())
    assert [s.rule for s in found] == ["mhd"]


def test_dismiss_hides_and_key_is_schema_scoped():
    product = _product()
    lot = _lot(product, 1)
    tenant = _tenant()
    assert today_mod.suggestions(tenant)
    today_mod.dismiss(f"mhd:{lot.pk}")
    assert today_mod.suggestions(tenant) == []
    assert today_mod._dismiss_key("x").startswith("today-dismiss:public:")


def test_resolve_recomputes_from_db_and_rejects_forged_keys():
    product = _product()
    lot = _lot(product, 1)
    tenant = _tenant()
    assert today_mod.resolve(tenant, f"mhd:{lot.pk}").target == ("product", product.pk)
    assert today_mod.resolve(tenant, "mhd:999999") is None
    assert today_mod.resolve(tenant, "x" * 500) is None
    lot.qty_remaining = 0
    lot.save()
    assert today_mod.resolve(tenant, f"mhd:{lot.pk}") is None  # партия продана


def test_no_ai_involved(ai_on):
    product = _product()
    _lot(product, 1)
    today_mod.compute(_tenant())
    assert fake.CALLS == []


def test_titles_stay_in_base_language(settings):
    from django.utils import translation

    _service()
    starts = _starts((10, 0), (10, 30), (11, 0))
    with mock.patch("apps.booking.availability.service_slots", return_value=starts):
        with translation.override("ru"):
            [s] = _rules(today_mod.compute(_tenant()), "slots")
    assert "Happy Hour" in s.initial["title"]


def test_no_repeat_for_ended_without_any_result():
    PromotionFactory(status="ended", ends_at=timezone.now() - timedelta(days=1))
    assert _rules(today_mod.compute(_tenant()), "repeat") == []
    assert not Promotion.objects.filter(status="active").exists()
