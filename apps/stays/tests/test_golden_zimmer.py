"""KA-12 Z-0: серверный золотой путь направления «Zimmer».

Витрина показывает цену → гость бронирует → бронь списывает ТУ ЖЕ сумму
(сезон + выходные + тариф с питанием + авто-скидка + 2 номера + Kurtaxe);
исполнение → выручка в журнале = итог брони; счёт из брони (Bruttomethode) =
итог брони точно, строки 7 % / 19 % / 0 % на месте; тот же e-mail — тот же клиент.
Браузерный двойник — GP-4 в `scripts/golden_paths.py`."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core.tests.dates import future_month_start
from apps.finance.models import RevenueEntry
from apps.finance.services import invoice_from_stay
from apps.stays import public_views
from apps.stays.models import RatePlan, SeasonRate, StayBooking, StaySettings, StayUnit
from apps.stays.state_machine import StayBookingSM
from apps.stays.tests.test_public import _req, _tenant

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def hotel():
    unit = StayUnit.objects.create(
        name=f"Doppelzimmer {uuid.uuid4().hex[:6]}",
        price_cents=9000,
        weekend_price_cents=11000,
        quantity=3,
        max_guests=2,
    )
    # Сезон на первые 3 ночи: часть ночей сезонная, часть — база/выходные.
    SeasonRate.objects.create(
        unit=unit,
        label="Hochsaison",
        start_date=D0,
        end_date=D0 + timedelta(days=2),
        price_cents=12500,
    )
    plan = RatePlan.objects.create(
        name="Halbpension", meal_plan="half_board", surcharge_cents=2400, percent_adjust=0
    )
    s = StaySettings.load()
    s.kurtaxe_cents = 250
    s.auto_discount_rules = [{"kind": "los", "threshold": 5, "percent": 10}]
    s.save()
    return unit, plan


def _shown(unit, von, bis, rooms, plan):
    """Сумма, которую витрина показывает для тарифа (контекст unit-страницы)."""
    captured = {}

    def fake_render(request, template, ctx, embed):
        captured.update(ctx)
        from django.http import HttpResponse

        return HttpResponse("")

    req = _req(
        path=f"/unterkunft/{unit.pk}/",
        data={"von": von.isoformat(), "bis": bis.isoformat(), "erw": "2", "rooms": str(rooms)},
        tenant=_tenant(),
    )
    orig = public_views._render_embed
    public_views._render_embed = fake_render
    try:
        public_views.unterkunft_unit(req, pk=unit.pk)
    finally:
        public_views._render_embed = orig
    assert captured["quote"]["available"], captured["quote"]
    option = next(o for o in captured["rate_options"] if o["rate"].pk == plan.pk)
    return round(option["total_eur"] * 100)


def _book(unit, von, bis, rooms, plan, email="gast@zimmer.de"):
    req = _req(
        "post",
        f"/unterkunft/{unit.pk}/buchen/",
        {
            "von": von.isoformat(),
            "bis": bis.isoformat(),
            "erw": "2",
            "rooms": str(rooms),
            "rate_plan": str(plan.pk),
            "name": "Gast",
            "email": email,
        },
        tenant=_tenant(),
    )
    req.META["REMOTE_ADDR"] = f"10.4.{uuid.uuid4().int % 250}.1"
    response = public_views.unterkunft_book(req, pk=unit.pk)
    assert response.status_code == 302
    return StayBooking.objects.filter(customer__email=email).latest("created_at")


def test_shown_equals_charged(hotel):
    unit, plan = hotel
    von, bis = D0, D0 + timedelta(days=6)  # 6 ночей: сезон + база + выходные, LOS −10 %
    shown = _shown(unit, von, bis, 2, plan)
    booking = _book(unit, von, bis, 2, plan)
    assert booking.rooms == 2
    assert booking.total_cents == shown


def test_fulfil_revenue_and_invoice_match_total(hotel):
    unit, plan = hotel
    booking = _book(unit, D0, D0 + timedelta(days=6), 2, plan)
    sm = StayBookingSM()
    if booking.status == StayBooking.STATUS_PENDING:
        sm.apply(booking, StayBooking.STATUS_CONFIRMED, actor=None)
    sm.apply(booking, StayBooking.STATUS_FULFILLED, actor=None)
    booking.refresh_from_db()
    total = Decimal(booking.total_cents) / 100
    revenue = sum(
        e.amount
        for e in RevenueEntry.objects.filter(source="stay", source_ref__startswith=str(booking.id))
    )
    assert revenue == total
    invoice = invoice_from_stay(booking, SimpleNamespace(small_business=False))
    assert invoice.gross == total
    rates = {line["vat_rate"] for line in invoice.lines}
    assert {"7.00", "19.00"} <= rates  # проживание 7 %, питание 19 %
    assert "0" in rates or "0.00" in rates  # Kurtaxe вне налога


def test_same_email_same_customer(hotel):
    unit, plan = hotel
    a = _book(unit, D0, D0 + timedelta(days=2), 1, plan)
    b = _book(unit, D0 + timedelta(days=10), D0 + timedelta(days=12), 1, plan)
    assert a.customer_id == b.customer_id
