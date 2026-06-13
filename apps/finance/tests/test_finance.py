"""Track D / D4a: журнал выручки — идемпотентные хуки (заказ выдан / бронь
выдана), ручные записи, кабинет-журнал за период."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.finance import views
from apps.finance.models import RevenueEntry
from apps.finance.services import record_revenue
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/finance/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw")
    return request


# --- сервис -----------------------------------------------------------------------


def test_record_revenue_idempotent_by_source_ref():
    first = record_revenue(source="order", source_ref="abc", amount=Decimal("10.00"))
    assert first is not None
    assert record_revenue(source="order", source_ref="abc", amount=Decimal("10.00")) is None
    assert RevenueEntry.objects.count() == 1
    # ручные — без дедупа, нулевые/отрицательные не пишем
    record_revenue(source="manual", amount=Decimal("5.00"))
    record_revenue(source="manual", amount=Decimal("5.00"))
    assert record_revenue(source="manual", amount=Decimal("0")) is None
    assert RevenueEntry.objects.count() == 3


# --- хуки FSM ----------------------------------------------------------------------


def test_order_picked_up_creates_entry_once():
    from apps.orders.services import create_order
    from apps.orders.state_machine import OrderSM

    order = create_order(
        items=[(ProductFactory(base_price=Decimal("4.00")), 3)], name="K", email="k@f.de"
    )
    sm = OrderSM()
    order = sm.apply(order, "confirmed")
    order = sm.apply(order, "ready")
    assert RevenueEntry.objects.count() == 0  # до выдачи выручки нет
    order = sm.apply(order, "picked_up")
    entry = RevenueEntry.objects.get(source="order", source_ref=str(order.id))
    assert entry.amount == Decimal("12.00")
    assert entry.customer == order.customer
    sm.apply(order, "picked_up")  # повтор статуса — no-op, дубля нет
    assert RevenueEntry.objects.count() == 1


def test_reservation_fulfilled_creates_entry_with_price():
    from apps.promotions.state_machine import ReservationSM

    promo = PromotionFactory(status="active", auto_confirm=True, price_override=Decimal("6.50"))
    reservation = reserve(promo, name="Gast", email="g@f.de", quantity=2)
    ReservationSM().apply(reservation, "fulfilled")
    entry = RevenueEntry.objects.get(source="reservation", source_ref=str(reservation.id))
    assert entry.amount == Decimal("13.00")

    # акция без цены — выручку не угадываем, записи нет
    promo2 = PromotionFactory(status="active", auto_confirm=True)
    reservation2 = reserve(promo2, name="Gast2", email="g2@f.de", quantity=1)
    ReservationSM().apply(reservation2, "fulfilled")
    assert not RevenueEntry.objects.filter(source_ref=str(reservation2.id)).exists()


# --- кабинет -----------------------------------------------------------------------


def test_journal_filters_period_and_totals():
    record_revenue(source="manual", amount=Decimal("10.00"), date=date(2026, 6, 1))
    record_revenue(
        source="manual", amount=Decimal("7.00"), vat_rate=Decimal("7.00"), date=date(2026, 6, 15)
    )
    record_revenue(source="manual", amount=Decimal("99.00"), date=date(2026, 5, 1))  # вне периода

    body = views.journal(_req(data={"von": "2026-06-01", "bis": "2026-06-30"})).content.decode()
    assert "17,00" in body or "17.00" in body  # итог периода
    # Запись вне периода (99,00) не показана. Проверяем формат с разделителем, а не
    # голую «99» — случайный CSRF-токен в HTML может содержать «99» (флака CI).
    assert "99,00" not in body and "99.00" not in body


def test_journal_manual_add():
    response = views.journal(
        _req("post", {"amount": "12,50", "vat_rate": "7.00", "date": "2026-06-10", "note": "Theke"})
    )
    assert response.status_code == 302
    entry = RevenueEntry.objects.get()
    assert entry.amount == Decimal("12.50") and entry.vat_rate == Decimal("7.00")
    assert entry.source == "manual" and entry.note == "Theke"
