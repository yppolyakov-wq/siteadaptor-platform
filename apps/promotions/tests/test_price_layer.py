"""P2 «акция = ценовой слой»: чекаут стандартным заказом (2026-08-03).

План promo-price-layer-plan-2026-08-03 §3. Главный риск волны — двойное
списание (лимит кампании + склад) в одной транзакции — закрыт замками ниже.
"""

from decimal import Decimal

import pytest

from apps.orders.services import OutOfStock as OrderOutOfStock
from apps.orders.state_machine import OrderSM
from apps.promotions import services
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _promo(product=None, quantity=10, price="5.00"):
    promo = PromotionFactory(
        product=product,
        available_quantity=quantity,
        price_override=Decimal(price),
    )
    Promotion.objects.filter(pk=promo.pk).update(status="active")
    promo.refresh_from_db()
    return promo


def _product(stock=30, price="10.00"):
    from apps.catalog.tests.factories import ProductFactory

    return ProductFactory(base_price=Decimal(price), stock_quantity=stock)


def test_purchase_decrements_both_counters_in_one_transaction():
    """Продажа по акции списывает И лимит кампании, И склад товара."""
    product = _product(stock=30)
    promo = _promo(product=product, quantity=10)
    order = services.purchase(promo, quantity=2, name="Anna", email="a@t.de")
    promo.refresh_from_db()
    product.refresh_from_db()
    assert promo.available_quantity == 8
    assert product.stock_quantity == 28
    item = order.items.get()
    assert item.unit_price == Decimal("5.00")  # замороженная промо-цена
    assert item.product_id == product.pk  # склад/леджер — штатные
    assert {"promo": str(promo.pk), "label": "Aktion"} in item.modifiers
    assert order.total == Decimal("10.00")


def test_sold_out_stock_rolls_back_campaign_limit():
    """Склад пуст → OutOfStock заказа откатывает И списание лимита кампании
    (одна транзакция; фантомного списания нет)."""
    product = _product(stock=1)
    promo = _promo(product=product, quantity=10)
    with pytest.raises(OrderOutOfStock):
        services.purchase(promo, quantity=2, name="Anna", email="a@t.de")
    promo.refresh_from_db()
    product.refresh_from_db()
    assert promo.available_quantity == 10  # лимит НЕ потерян
    assert product.stock_quantity == 1


def test_exhausted_campaign_limit_raises_and_keeps_stock():
    product = _product(stock=30)
    promo = _promo(product=product, quantity=1)
    services.purchase(promo, quantity=1, name="A", email="a@t.de")
    with pytest.raises(services.OutOfStock):
        services.purchase(promo, quantity=1, name="B", email="b@t.de")
    product.refresh_from_db()
    assert product.stock_quantity == 29  # второй чекаут склад не тронул


def test_cancel_returns_both_stock_and_campaign_limit_once():
    """Отмена заказа возвращает склад (штатно) И лимит кампании — один раз."""
    product = _product(stock=30)
    promo = _promo(product=product, quantity=10)
    order = services.purchase(promo, quantity=3, name="Anna", email="a@t.de")
    OrderSM().apply(order, "cancelled")
    promo.refresh_from_db()
    product.refresh_from_db()
    assert promo.available_quantity == 10
    assert product.stock_quantity == 30


def test_free_promotion_without_target_sells_as_standard_order():
    """«Свободная» акция (без цели): стандартный заказ со свободной строкой —
    склад не тронут, клиент в CRM, канбан/письма штатные."""
    promo = _promo(product=None, quantity=5)
    order = services.purchase(promo, quantity=1, name="Bernd", email="b@t.de")
    promo.refresh_from_db()
    assert promo.available_quantity == 4
    assert order.items.get().product_id is None
    assert order.customer.email == "b@t.de"


def test_inactive_promotion_refuses_purchase():
    promo = _promo(product=None, quantity=None)  # без лимита
    Promotion.objects.filter(pk=promo.pk).update(status="paused")
    promo.refresh_from_db()
    with pytest.raises(services.OutOfStock):
        services.purchase(promo, quantity=1, name="A", email="a@t.de")


def test_reserve_flow_untouched():
    """Паритет: старый резерв-флоу жив, пока витрина не переехала (P5)."""
    promo = _promo(product=None, quantity=5)
    reservation = services.reserve(promo, name="Alt", email="alt@t.de", quantity=1)
    promo.refresh_from_db()
    assert promo.available_quantity == 4
    assert reservation.reference_code.startswith("R-")


# --- P5: витрина акций на новых рельсах -------------------------------------


def test_promotion_purchase_endpoint_creates_standard_order():
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    from apps.orders.models import Order
    from apps.promotions import public_views

    promo = _promo(product=None, quantity=5, price="7.50")
    request = RequestFactory().post(
        f"/p/{promo.pk}/kaufen/",
        {"name": "Anna", "email": "a@t.de", "quantity": "2", "form_token": f"kauf-{promo.pk}"},
    )
    request.session = {}
    request._messages = FallbackStorage(request)
    resp = public_views.promotion_purchase(request, pk=promo.pk)
    assert resp.status_code == 302
    order = Order.objects.get()
    assert (
        resp.url.endswith(f"/bestellung/{order.reference_code}/")
        or order.reference_code in resp.url
    )
    promo.refresh_from_db()
    assert promo.available_quantity == 3


def test_detail_service_target_links_to_slot_funnel():
    """Акция на услугу: CTA ведёт в штатную воронку записи (промо-цена там
    применяется автоматически) — формы покупки на детали нет."""
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory

    from apps.booking.models import Service
    from apps.promotions import public_views
    from apps.promotions.models import Promotion

    service = Service.objects.create(name="Haarschnitt", price_cents=3500)
    promo = _promo(product=None, quantity=5)
    Promotion.objects.filter(pk=promo.pk).update(service=service)
    request = RequestFactory().get(f"/p/{promo.pk}/")
    request.session = {}
    request._messages = FallbackStorage(request)
    body = public_views.promotion_detail(request, pk=promo.pk).content.decode()
    assert f"/termin/leistung/{service.pk}/" in body
    assert "/kaufen/" not in body
