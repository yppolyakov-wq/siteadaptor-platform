"""ERP-1: снимок себестоимости (EK) в позиции заказа + Wareneinsatz/Rohertrag.

План docs/erp-wave-plan-2026-08-21.md. До снимка маржа считалась по ТЕКУЩЕМУ
cost_price и дрейфовала после смены закупочной цены.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.orders import services
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_item_snapshots_cost_and_survives_price_change():
    p = ProductFactory(base_price=Decimal("10.00"), name={"de": "Brot"})
    p.cost_price = Decimal("4.00")
    p.save(update_fields=["cost_price"])
    order = services.create_order(items=[(p, 2)], name="K", email="k@t.de")
    item = order.items.get()
    assert item.cost_price == Decimal("4.00")

    # Закупочная цена выросла ПОСЛЕ продажи — снимок не дрейфует.
    p.cost_price = Decimal("9.00")
    p.save(update_fields=["cost_price"])
    item.refresh_from_db()
    assert item.cost_price == Decimal("4.00")


def test_variant_cost_fallback_and_free_line_without_cost():
    p = ProductFactory(base_price=Decimal("10.00"), name={"de": "Tee"})
    p.cost_price = Decimal("3.00")
    p.save(update_fields=["cost_price"])
    v = ProductVariant.objects.create(product=p, label="250 g")  # свой EK пуст → фолбэк
    order = services.create_order(
        items=[(p, v, 1)],
        name="K",
        email="k2@t.de",
        custom_lines=[("Beratung", Decimal("50.00"), 1, None, None, [])],
    )
    by_title = {i.title_snapshot: i for i in order.items.all()}
    assert by_title["Tee · 250 g"].cost_price == Decimal("3.00")
    assert by_title["Beratung"].cost_price is None  # свободная строка — без EK


def test_ergebnis_shows_wareneinsatz_and_rohertrag():
    from apps.finance import views as finance_views

    p = ProductFactory(base_price=Decimal("10.00"), name={"de": "Käse"})
    p.cost_price = Decimal("6.00")
    p.save(update_fields=["cost_price"])
    order = services.create_order(items=[(p, 3)], name="K", email="k3@t.de")
    OrderSM().apply(order, "confirmed")
    OrderSM().apply(order, "ready")
    OrderSM().apply(order, "picked_up")  # выручка 30 € записана сегодня

    request = RequestFactory().get("/dashboard/finance/ergebnis/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username="own", email="o@t.de", password="pw12345678"
    )
    body = finance_views.ergebnis(request).content.decode()
    assert "18,00" in body or "18.00" in body  # Wareneinsatz 3 × 6 €
    assert "12,00" in body or "12.00" in body  # Rohertrag 30 − 18
