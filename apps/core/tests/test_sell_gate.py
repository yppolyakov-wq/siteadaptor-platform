"""AIS W4-5d: гейт продажи в кассах витрины (план docs/ais-w4-5d-sell-gate-plan-2026-11-06.md).

Срез 1 — касса товаров: `create_order(channel="storefront")` и покупка акции. Флаг выключен —
поведение прежнее; включён и магазин не готов — отказ ДО записей и списаний; демо, служебный и
exempt-тенант не гейтятся; кабинет (без channel) не гейтится никогда.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection

from apps.catalog.tests.factories import ProductFactory
from apps.core import readiness
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def not_ready(monkeypatch, settings):
    """Флаг включён, тенант соединения — обычный и НЕ готов к продаже."""
    settings.READINESS_SELL_GATE = True
    tenant = TenantFactory.build(schema_name=connection.schema_name)
    monkeypatch.setattr(connection, "tenant", tenant, raising=False)
    monkeypatch.setattr(readiness, "sell_ready", lambda t, d: False)
    return tenant


def _order(**kw):
    from apps.orders import services

    p = ProductFactory(base_price=Decimal("3"), stock_quantity=5)
    return p, services.create_order(items=[(p, None, 1, [])], name="G", email="g@example.com", **kw)


def test_flag_off_is_a_noop_without_queries(settings, django_assert_num_queries):
    settings.READINESS_SELL_GATE = False
    with django_assert_num_queries(0):
        readiness.require_sell(TenantFactory.build(), "waren")


def test_storefront_order_is_refused_before_any_write(not_ready):
    from apps.orders import services
    from apps.orders.models import Order

    p = ProductFactory(base_price=Decimal("3"), stock_quantity=5)
    with pytest.raises(readiness.SellBlocked):
        services.create_order(
            items=[(p, None, 1, [])], name="G", email="g@example.com", channel="storefront"
        )
    p.refresh_from_db()
    assert not Order.objects.exists() and p.stock_quantity == 5


def test_cabinet_order_is_never_gated(not_ready):
    _p, order = _order()
    assert order.pk


@pytest.mark.parametrize("attr", ["is_demo", "is_internal"])
def test_demo_and_internal_tenants_sell(not_ready, attr):
    setattr(not_ready, attr, True)
    _p, order = _order(channel="storefront")
    assert order.pk


def test_exempt_tenant_sells(not_ready):
    not_ready.site_config = {"readiness": {"exempt": True}}
    _p, order = _order(channel="storefront")
    assert order.pk


def test_ready_tenant_sells(not_ready, monkeypatch):
    monkeypatch.setattr(readiness, "sell_ready", lambda t, d: True)
    _p, order = _order(channel="storefront")
    assert order.pk


def test_promo_purchase_refused_before_campaign_limit(not_ready):
    from apps.orders.models import Order
    from apps.promotions import services as promo_services
    from apps.promotions.tests.factories import PromotionFactory

    promo = PromotionFactory(
        product=ProductFactory(base_price=Decimal("10")),
        status="active",
        discount_percent=10,
        available_quantity=3,
    )
    with pytest.raises(readiness.SellBlocked):
        promo_services.purchase(
            promo, quantity=1, name="G", email="g@example.com", channel="storefront"
        )
    promo.refresh_from_db()
    assert promo.available_quantity == 3 and not Order.objects.exists()


def test_goods_direction_prefers_menu_only_for_pure_gastro(monkeypatch):
    from types import SimpleNamespace

    from apps.core import directions

    t = TenantFactory.build()
    monkeypatch.setattr(directions, "active", lambda t: [SimpleNamespace(key="speisekarte")])
    assert readiness.goods_direction(t) == "speisekarte"
    monkeypatch.setattr(
        directions,
        "active",
        lambda t: [SimpleNamespace(key="speisekarte"), SimpleNamespace(key="waren")],
    )
    assert readiness.goods_direction(t) == "waren"


def _checkout_request(cart, tenant):
    import uuid

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    request = RequestFactory().post("/warenkorb/bestellen/", {"name": "K"})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.update({"cart": cart})
    request.tenant = tenant
    return request


def test_checkout_shows_neutral_message_and_keeps_cart(not_ready, settings):
    from django.contrib.messages import get_messages

    from apps.orders import public_views
    from apps.orders.models import Order

    settings.ROOT_URLCONF = "config.urls_tenant"
    p = ProductFactory(base_price=Decimal("3"))
    request = _checkout_request({str(p.pk): 2}, not_ready)
    resp = public_views.checkout(request)
    assert resp.status_code == 302 and not Order.objects.exists()
    assert request.session["cart"] == {str(p.pk): 2}
    texts = [str(m) for m in get_messages(request)]
    assert texts == [str(readiness.NEUTRAL_MESSAGE)]


def test_checkout_flag_off_still_creates_order(settings, monkeypatch):
    from apps.orders import public_views
    from apps.orders.models import Order

    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.READINESS_SELL_GATE = False
    monkeypatch.setattr(readiness, "sell_ready", lambda t, d: pytest.fail("gate consulted"))
    tenant = TenantFactory.build(schema_name=connection.schema_name)
    monkeypatch.setattr(connection, "tenant", tenant, raising=False)
    p = ProductFactory(base_price=Decimal("3"))
    public_views.checkout(_checkout_request({str(p.pk): 1}, tenant))
    assert Order.objects.count() == 1
