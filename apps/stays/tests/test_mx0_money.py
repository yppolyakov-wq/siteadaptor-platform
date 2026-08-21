"""MX-0: денежные фиксы пересчёта брони при переносе/продлении.

Три доказанных дефекта (docs/mx-execution-plan-2026-08-21.md §MX-0.3):
(а) per-night доп-услуга не пересчитывалась при продлении (530 € вместо 575 €);
(б) auto_discount звался без unit/departure/extra — правка теряла скидку акции;
(в) неоплаченная процентная предоплата не следовала за новым итогом.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import extras as extras_engine
from apps.core.models import Extra
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.stays import services
from apps.stays.models import RatePlan, StayBooking, StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(price_cents=10000, **kw):
    return StayUnit.objects.create(
        name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=price_cents, quantity=1, **kw
    )


def _dates(nights=2, days_ahead=30):
    arrival = timezone.localdate() + timedelta(days=days_ahead)
    return arrival, arrival + timedelta(days=nights)


def test_per_night_extra_recomputed_on_extend():
    """Продление 2→5 ночей: завтрак ×ночь следует за ночами (было 530 €, стало 575 €)."""
    unit = _unit(max_guests=4)
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    arrival, departure = _dates(nights=2)
    snap = extras_engine.snapshot([breakfast.pk], "stays", nights=2)
    b = services.book_stay(
        unit, arrival=arrival, departure=departure, name="Gast", extras=snap, adults=1
    )
    assert b.total_cents == 20000 + 3000

    services.move_stay(b, arrival=arrival, departure=arrival + timedelta(days=5), reprice=True)
    b.refresh_from_db()
    assert b.total_cents == 50000 + 1500 * 5
    assert extras_engine.total_cents(b.extras) == 7500


def test_legacy_snapshot_without_unit_cents_kept_as_is():
    """Легаси-снимок (до MX-0, без unit_cents) при пересчёте не трогается — цену
    задним числом не угадываем."""
    unit = _unit()
    arrival, departure = _dates(nights=2)
    legacy = [{"label": "Frühstück", "price_cents": 3000}]
    b = services.book_stay(
        unit, arrival=arrival, departure=departure, name="Gast", extras=legacy, adults=1
    )
    services.move_stay(b, arrival=arrival, departure=arrival + timedelta(days=5), reprice=True)
    b.refresh_from_db()
    assert b.total_cents == 50000 + 3000  # допы остались как были


def test_snapshot_rows_carry_option_id():
    """MX-0: снимок несёт id/unit_cents/per_night — фундамент Zusatzverkäufe."""
    e = Extra.objects.create(label="Parkplatz", price_cents=800, scope=Extra.SCOPE_STAYS)
    snap = extras_engine.snapshot([e.pk], "stays", nights=3)
    assert snap == [
        {
            "id": str(e.pk),
            "label": "Parkplatz",
            "price_cents": 800,
            "unit_cents": 800,
            "per_night": False,
        }
    ]


def test_move_keeps_stay_promo_discount():
    """Правка дат внутри окна акции сохраняет скидку (раньше терялась молча)."""
    unit = _unit()
    promo = PromotionFactory(product=None, available_quantity=5)
    Promotion.objects.filter(pk=promo.pk).update(
        status="active", stay_unit=unit, discount_percent=20, target_rules={}
    )
    arrival, departure = _dates(nights=2)
    b = services.book_stay(unit, arrival=arrival, departure=departure, name="G", adults=1)
    assert b.auto_discount_cents == 4000  # 20 % от 20000
    services.move_stay(b, arrival=arrival, departure=arrival + timedelta(days=3), reprice=True)
    b.refresh_from_db()
    assert b.auto_discount_cents == 6000  # 20 % от 30000 — скидка жива
    assert b.total_cents == 30000 - 6000


def test_pending_prepayment_follows_new_total():
    """Неоплаченная процентная предоплата (G7) пересчитывается по новому итогу;
    оплаченный депозит не трогается."""
    unit = _unit()
    rate = RatePlan.objects.create(name="Standard", prepayment_percent=50)
    arrival, departure = _dates(nights=2)
    b = services.book_stay(
        unit, arrival=arrival, departure=departure, name="G", adults=1, rate_plan=rate
    )
    b.deposit_cents = 10000  # 50 % от 20000 — как выставила бы витрина
    b.payment_state = StayBooking.PAYMENT_PENDING
    b.save(update_fields=["deposit_cents", "payment_state"])
    services.move_stay(b, arrival=arrival, departure=arrival + timedelta(days=4), reprice=True)
    b.refresh_from_db()
    assert b.total_cents == 40000
    assert b.deposit_cents == 20000  # 50 % нового итога

    b.payment_state = StayBooking.PAYMENT_PAID
    b.save(update_fields=["payment_state"])
    services.move_stay(b, arrival=arrival, departure=arrival + timedelta(days=2), reprice=True)
    b.refresh_from_db()
    assert b.deposit_cents == 20000  # оплаченное не переписываем (MX-3 — доплата)
