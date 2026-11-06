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
def conn_tenant():
    """Тенант соединения через set_tenant (не monkeypatch: откат raising=False удаляет атрибут
    у общего соединения и роняет соседние тесты процесса)."""
    prev = getattr(connection, "tenant", None)
    tenant = TenantFactory.build(schema_name=connection.schema_name)
    connection.set_tenant(tenant)
    yield tenant
    if prev is not None:
        connection.set_tenant(prev)
    else:
        connection.set_schema_to_public()


@pytest.fixture
def not_ready(monkeypatch, settings, conn_tenant):
    """Флаг включён, тенант соединения — обычный и НЕ готов к продаже."""
    settings.READINESS_SELL_GATE = True
    monkeypatch.setattr(readiness, "sell_ready", lambda t, d: False)
    return conn_tenant


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


def test_checkout_flag_off_still_creates_order(settings, monkeypatch, conn_tenant):
    from apps.orders import public_views
    from apps.orders.models import Order

    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.READINESS_SELL_GATE = False
    monkeypatch.setattr(readiness, "sell_ready", lambda t, d: pytest.fail("gate consulted"))
    p = ProductFactory(base_price=Decimal("3"))
    public_views.checkout(_checkout_request({str(p.pk): 1}, conn_tenant))
    assert Order.objects.count() == 1


# --- срез 2: записи, столы, номера, билеты, абонемент, сертификат --------------------------


@pytest.fixture
def blocked_directions(monkeypatch):
    """Гейт закрыт для всех направлений; копит, с каким направлением его спросили."""
    seen = []

    def deny(tenant, direction):
        seen.append(direction)
        raise readiness.SellBlocked(direction)

    monkeypatch.setattr(readiness, "require_sell", deny)
    return seen


def test_booking_services_ask_the_gate_with_their_direction(blocked_directions):
    from datetime import date, datetime
    from types import SimpleNamespace

    from apps.booking import services as booking
    from apps.events import services as events
    from apps.stays import services as stays

    now = datetime(2030, 1, 1, 10)
    cases = (
        (SimpleNamespace(type="table"), None, "tisch"),
        (SimpleNamespace(type="table"), object(), "termine"),  # услуга на ресурсе-«столе»
        (None, None, "termine"),
    )
    for resource, service, expected in cases:
        with pytest.raises(readiness.SellBlocked):
            booking.book(
                resource, start=now, end=now, name="G", service=service, channel="storefront"
            )
        assert blocked_directions[-1] == expected
    with pytest.raises(readiness.SellBlocked):
        booking.book_many([], service=object(), name="G", channel="storefront")
    assert blocked_directions[-1] == "termine"
    with pytest.raises(readiness.SellBlocked):
        stays.book_stay(
            None,
            arrival=date(2030, 1, 1),
            departure=date(2030, 1, 2),
            name="G",
            channel="storefront",
        )
    with pytest.raises(readiness.SellBlocked):
        events.book_ticket(None, name="G", channel="storefront")
    assert blocked_directions[-2:] == ["zimmer", "tickets"]


def test_booking_services_without_channel_skip_the_gate(blocked_directions):
    """Кабинет channel не передаёт: до гейта дело не доходит (ошибка — уже своя, по данным)."""
    from datetime import datetime

    from apps.booking import services as booking

    now = datetime(2030, 1, 1, 10)
    with pytest.raises(ValueError):  # end <= start — своя проверка сервиса, не гейт
        booking.book(None, start=now, end=now, name="G")
    assert blocked_directions == []


def test_gift_voucher_checks_only_the_base(monkeypatch):
    seen = []
    monkeypatch.setattr(readiness, "missing", lambda t, **kw: seen.append(kw) or [])
    assert readiness.sell_ready(TenantFactory.build(), "") is True
    assert {kw.get("direction") for kw in seen} == {""}


def test_every_storefront_sale_call_passes_the_channel():
    """Замок класса: вьюха витрины, зовущая сервис продажи, передаёт channel="storefront"
    (или внесена сюда с причиной)."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    calls = re.compile(
        r"(?<![\w.])(?:\w*services\.)?(book|book_many|book_stay|book_ticket|create_order|purchase)\("
    )
    allow = {
        # пробрасывает channel вызывающего (публичного вызова нет; витрина передаст storefront)
        "apps/promotions/price_layer.py:book",
    }
    missing_channel = []
    paths = [*root.glob("apps/*/public_views.py"), root / "apps/promotions/price_layer.py"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for m in calls.finditer(text):
            if text[max(0, m.start() - 4) : m.start()] == "def ":
                continue
            window = text[m.end() : m.end() + 2500]
            depth, end = 1, 0
            for i, ch in enumerate(window):
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0:
                    end = i
                    break
            args = window[:end]
            key = f"{path.relative_to(root)}:{m.group(1)}"
            gated = "channel=" in args and ('"storefront"' in args or "channel=channel" in args)
            if not gated and not any(key.startswith(a) for a in allow):
                missing_channel.append(key)
    assert not missing_channel, missing_channel


def test_gate_without_tenant_is_allowed_not_500(settings):
    settings.READINESS_SELL_GATE = True
    readiness.require_sell(None, "waren")  # не бросает


# --- GET: фраза вместо формы (не вводить данные зря) -------------------------------------


@pytest.mark.parametrize("kind", ["stay", "service", "event", "goods"])
def test_sell_closed_tag_follows_the_gate(kind, not_ready, settings):
    from types import SimpleNamespace

    from apps.tenants.templatetags.siteui import sell_closed

    ctx = {"request": SimpleNamespace(tenant=not_ready)}
    assert sell_closed(ctx, kind) is True
    settings.READINESS_SELL_GATE = False
    assert sell_closed(ctx, kind) is False


def test_stay_page_shows_notice_instead_of_form(not_ready, settings):
    from django.template.loader import render_to_string

    html = render_to_string(
        "storefront/_buybox.html",
        {
            "sellable": {"kind": "stay", "buybox_ready": True, "purchase_mode": "booking"},
            "buybox_form": "storefront/_price_request.html",
            "buybox_mode": "booking",
            "request": __import__("types").SimpleNamespace(tenant=not_ready),
        },
    )
    assert "data-sell-closed" in html


def test_stay_page_shows_form_when_gate_is_off(settings, conn_tenant):
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    settings.READINESS_SELL_GATE = False
    html = render_to_string(
        "storefront/_buybox.html",
        {
            "sellable": {"kind": "stay", "buybox_ready": True, "purchase_mode": "booking"},
            "buybox_form": "storefront/_price_request.html",
            "buybox_mode": "booking",
            "request": SimpleNamespace(tenant=conn_tenant),
        },
    )
    assert "data-sell-closed" not in html and "data-price-on-request" in html
