"""KA-W1 (пилот, батч C): время самовывоза — окна из часов работы, ёмкость, гонка.

План — `docs/ka-w1-pickup-slots-plan-2026-10-23.md`."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.orders import pickup_slots, public_views
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL_DAY = {str(d): ["00:00", "23:59"] for d in range(7)}
WEEKDAYS = {str(d): ["09:00", "12:00"] for d in range(5)}  # Mo–Fr 9–12, Sa/So zu
CFG = {"step": 30, "capacity": 0, "lead": 60, "days": 7}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(hours=None, cfg=CFG, **extra):
    site_config = {"pickup_slots": cfg} if cfg else {}
    return TenantFactory.build(
        business_type="bakery",
        opening_hours_structured=hours if hours is not None else WEEKDAYS,
        site_config=site_config,
        **extra,
    )


def _local(*args):
    return timezone.make_aware(datetime(*args))


# --- настройки ------------------------------------------------------------------------------


def test_normalize_clamps_and_drops_junk():
    assert siteconfig.normalize_pickup_slots(None) is None
    assert siteconfig.normalize_pickup_slots("x") is None
    assert siteconfig.normalize_pickup_slots({"on": False}) is None
    got = siteconfig.normalize_pickup_slots(
        {"step": "45", "capacity": "-3", "lead": "99999", "days": "abc"}
    )
    assert got == {"step": 30, "capacity": 0, "lead": 2880, "days": 7}
    assert siteconfig.normalize_pickup_slots({"step": 15, "days": 30})["days"] == 14


def test_key_is_presence_minimal_in_normalize():
    assert "pickup_slots" not in siteconfig.normalize({})
    assert siteconfig.normalize({"pickup_slots": CFG})["pickup_slots"] == CFG
    assert "pickup_slots" not in siteconfig.normalize({"pickup_slots": "junk"})


# --- сетка окон ------------------------------------------------------------------------------


def test_slots_respect_lead_close_and_closed_days():
    # Пт 10:10 → с учётом 60 мин первое окно 11:30 (11:00 < 11:10), последнее 11:30
    # (12:00 — закрытие, окно 12:00–12:30 вне часов); Sa/So пропущены → дальше Пн.
    now = _local(2026, 10, 23, 10, 10)
    grid = pickup_slots.slots_for(_tenant(), now=now)
    first_day, first_row = grid[0]
    assert first_day.isoformat() == "2026-10-23"
    assert [timezone.localtime(s).strftime("%H:%M") for s, _ in first_row] == ["11:30"]
    assert grid[1][0].isoformat() == "2026-10-26"  # Montag
    assert [timezone.localtime(s).strftime("%H:%M") for s, _ in grid[1][1]] == [
        "09:00",
        "09:30",
        "10:00",
        "10:30",
        "11:00",
        "11:30",
    ]
    assert all(d.weekday() < 5 for d, _ in grid)
    assert [d.isoformat() for d, _ in grid][-1] == "2026-10-29"  # 7 Kalendertage
    assert len(grid) == 5


def test_no_hours_or_disabled_means_no_slots():
    assert pickup_slots.slots_for(_tenant(hours={})) == []
    assert pickup_slots.slots_for(_tenant(cfg=None)) == []


def test_slots_survive_dst_change():
    # 25.10.2026 — переход на зимнее время: шаги в UTC, ни одно окно не теряется.
    now = _local(2026, 10, 24, 20, 0)
    grid = pickup_slots.slots_for(_tenant(hours=ALL_DAY, cfg={**CFG, "days": 2}), now=now)
    sunday = next(row for day, row in grid if day.isoformat() == "2026-10-25")
    labels = [timezone.localtime(s).strftime("%H:%M") for s, _ in sunday]
    # 25-часовой день: окна — разные моменты, 02:00/02:30 по настенным часам дважды
    assert len({s for s, _ in sunday}) == len(sunday) == 49
    assert labels.count("02:00") == 2
    assert labels[0] == "00:00" and "12:00" in labels


def test_validate_accepts_only_grid_values():
    t = _tenant()
    now = _local(2026, 10, 23, 8, 0)
    ok = _local(2026, 10, 23, 10, 0)
    assert pickup_slots.validate(t, ok.isoformat(), now=now) == ok
    for bad in (
        "",
        "junk",
        _local(2026, 10, 23, 10, 15).isoformat(),  # не на сетке
        _local(2026, 10, 23, 8, 30).isoformat(),  # раньше открытия
        _local(2026, 10, 24, 10, 0).isoformat(),  # суббота — закрыто
        _local(2026, 10, 22, 10, 0).isoformat(),  # прошлое
        "9" * 100,
    ):
        assert pickup_slots.validate(t, bad, now=now) is None, bad


# --- ёмкость и гонка -------------------------------------------------------------------------


def _order(slot, **kw):
    return create_order(
        items=[(ProductFactory(base_price=Decimal("3.00")), 1)],
        name="K",
        pickup_slot=slot,
        **kw,
    )


def test_full_slot_disappears_and_cancel_frees_it():
    from apps.orders.state_machine import OrderSM

    t = _tenant(cfg={**CFG, "capacity": 2})
    now = _local(2026, 10, 23, 8, 0)
    slot = _local(2026, 10, 23, 10, 0)
    a = _order(slot)
    _order(slot)
    offered = {s for _d, row in pickup_slots.slots_for(t, now=now) for s, _ in row}
    assert slot not in offered
    OrderSM().apply(a, "cancelled")
    offered = {s for _d, row in pickup_slots.slots_for(t, now=now) for s, _ in row}
    assert slot in offered


def test_claim_rejects_a_full_slot_and_rolls_back_stock():
    slot = _local(2026, 10, 23, 10, 0)
    _order(slot)
    product = ProductFactory(base_price=Decimal("3.00"), stock_quantity=5)
    with pytest.raises(pickup_slots.SlotFull):
        create_order(items=[(product, 2)], name="K", pickup_slot=slot, pickup_capacity=1)
    product.refresh_from_db()
    assert product.stock_quantity == 5
    assert Order.objects.count() == 1


def test_delivery_never_gets_a_slot():
    slot = _local(2026, 10, 23, 10, 0)
    order = _order(slot, fulfillment=Order.FULFILLMENT_DELIVERY, shipping_address="Weg 1")
    assert order.pickup_slot is None


# --- витрина ---------------------------------------------------------------------------------


def _req(method="post", data=None, session=None, tenant=None, path="/warenkorb/bestellen/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant or _tenant(hours=ALL_DAY, cfg={**CFG, "lead": 0, "days": 2})
    return request


def _cart(tenant):
    product = ProductFactory(base_price=Decimal("8.00"))
    add = _req(data={"product": str(product.pk), "qty": "1"}, tenant=tenant)
    public_views.cart_add(add)
    return add.session[public_views.CART_SESSION_KEY]


def _first_slot(tenant):
    return pickup_slots.slots_for(tenant)[0][1][0][0]


def test_without_setting_cart_and_order_are_unchanged():
    t = _tenant(hours=ALL_DAY, cfg=None)
    cart = _cart(t)
    body = public_views.cart_view(
        _req("get", session={"cart": cart}, tenant=t, path="/warenkorb/")
    ).content.decode()
    assert 'name="pickup_slot"' not in body
    public_views.checkout(_req(data={"name": "K"}, session={"cart": cart}, tenant=t))
    assert Order.objects.get().pickup_slot is None


def test_cart_offers_slots_and_checkout_stores_the_choice():
    t = _req().tenant
    cart = _cart(t)
    body = public_views.cart_view(
        _req("get", session={"cart": cart}, tenant=t, path="/warenkorb/")
    ).content.decode()
    assert 'name="pickup_slot"' in body and "<optgroup" in body
    select = body.split('name="pickup_slot"', 1)[0].rsplit("<select", 1)[1]
    assert "required" not in select  # скрытое обязательное поле отменило бы отправку
    slot = _first_slot(t)
    public_views.checkout(
        _req(data={"name": "K", "pickup_slot": slot.isoformat()}, session={"cart": cart}, tenant=t)
    )
    assert Order.objects.get().pickup_slot == slot


def test_checkout_requires_a_valid_slot():
    t = _req().tenant
    cart = _cart(t)
    for data in ({"name": "K"}, {"name": "K", "pickup_slot": "2001-01-01T10:00:00+01:00"}):
        resp = public_views.checkout(_req(data=data, session={"cart": cart}, tenant=t))
        assert resp.status_code == 302 and resp.url.endswith("/warenkorb/")
    assert Order.objects.count() == 0


def test_checkout_without_any_slot_is_refused():
    t = _tenant(hours={}, cfg=CFG)
    cart = _cart(t)
    public_views.checkout(_req(data={"name": "K"}, session={"cart": cart}, tenant=t))
    assert Order.objects.count() == 0


def test_delivery_checkout_ignores_posted_slot():
    t = _tenant(
        hours=ALL_DAY,
        cfg={**CFG, "lead": 0, "days": 2},
        delivery_enabled=True,
    )
    cart = _cart(t)
    public_views.checkout(
        _req(
            data={
                "name": "K",
                "fulfillment": "delivery",
                "street": "Weg 1",
                "plz": "42651",
                "city": "Solingen",
                "pickup_slot": _first_slot(t).isoformat(),
            },
            session={"cart": cart},
            tenant=t,
        )
    )
    order = Order.objects.get()
    assert order.is_delivery and order.pickup_slot is None


def test_full_slot_at_checkout_returns_to_cart():
    t = _tenant(hours=ALL_DAY, cfg={**CFG, "lead": 0, "days": 2, "capacity": 1})
    cart = _cart(t)
    slot = _first_slot(t)
    # кто-то занял окно между показом корзины и отправкой: validate ещё видит окно
    # (снимок сетки), а claim под блокировкой — уже нет
    real_validate = pickup_slots.validate
    _order(slot)
    try:
        pickup_slots.validate = lambda *a, **k: slot
        resp = public_views.checkout(
            _req(
                data={"name": "K", "pickup_slot": slot.isoformat()},
                session={"cart": cart},
                tenant=t,
            )
        )
    finally:
        pickup_slots.validate = real_validate
    assert resp.status_code == 302 and resp.url.endswith("/warenkorb/")
    assert Order.objects.count() == 1


def test_slot_is_shown_on_confirmation_emails_and_cabinet_card():
    from django.template.loader import render_to_string

    slot = _local(2026, 10, 23, 10, 30)
    order = _order(slot)
    ctx = {"order": order, "customer": order.customer, "items": list(order.items.all())}
    for tpl in ("order_created.txt", "order_owner.txt", "order_confirmed.txt", "order_ready.txt"):
        assert "23.10., 10:30" in render_to_string(f"emails/{tpl}", ctx), tpl
    src = open("templates/storefront/order_confirmation.html").read()
    assert "data-pickup-slot" in src and "order.pickup_slot" in src
    assert "data-pickup-slot" in open("templates/orders/order_detail.html").read()


# --- настройка в кабинете --------------------------------------------------------------------


def test_save_is_targeted_and_switch_off_removes_the_key():
    from apps.orders.views import save_pickup_slots

    t = TenantFactory(site_config={"notify": {"x": 1}, "board": {"order": ["a"]}})
    req = RequestFactory().post(
        "/",
        {
            "pickup_slots_on": "on",
            "pickup_slots_step": "15",
            "pickup_slots_capacity": "4",
            "pickup_slots_lead": "30",
            "pickup_slots_days": "3",
        },
    )
    save_pickup_slots(t, req)
    t.refresh_from_db()
    assert t.site_config["pickup_slots"] == {"step": 15, "capacity": 4, "lead": 30, "days": 3}
    assert t.site_config["notify"] == {"x": 1} and t.site_config["board"] == {"order": ["a"]}
    save_pickup_slots(t, RequestFactory().post("/", {}))
    t.refresh_from_db()
    assert "pickup_slots" not in t.site_config and t.site_config["notify"] == {"x": 1}


def test_settings_form_has_own_sentinel_and_warns_without_hours():
    src = open("templates/tenant/_payment_fields.html").read()
    block = src.split("data-pickup-slots-settings", 1)[1]
    assert 'name="sec_pickup_slots"' in block[:200]
    assert "Ohne strukturierte Öffnungszeiten" in block
    views_src = open("apps/core/views.py").read()
    assert 'request.POST.get("sec_pickup_slots")' in views_src


def test_one_contact_cannot_hoard_limited_slots():
    t = _tenant(hours=ALL_DAY, cfg={**CFG, "lead": 0, "days": 2, "capacity": 5})
    cart = _cart(t)
    grid = [s for _d, row in pickup_slots.slots_for(t) for s, _ in row]
    for slot in grid[: pickup_slots.MAX_OPEN_PER_CONTACT]:
        _order(slot, email="hoard@example.com")
    resp = public_views.checkout(
        _req(
            data={"name": "K", "email": "Hoard@example.com", "pickup_slot": grid[5].isoformat()},
            session={"cart": cart},
            tenant=t,
        )
    )
    assert resp.status_code == 302 and resp.url.endswith("/warenkorb/")
    assert Order.objects.count() == pickup_slots.MAX_OPEN_PER_CONTACT
    # без лимита ёмкости окна не ограничены — и правило не мешает
    unlimited = _tenant(hours=ALL_DAY, cfg={**CFG, "lead": 0, "days": 2})
    public_views.checkout(
        _req(
            data={"name": "K", "email": "hoard@example.com", "pickup_slot": grid[5].isoformat()},
            session={"cart": _cart(unlimited)},
            tenant=unlimited,
        )
    )
    assert Order.objects.count() == pickup_slots.MAX_OPEN_PER_CONTACT + 1


def test_spring_forward_gap_slots_stay_choosable():
    # 29.03.2026: 02:00 → 03:00. Каждое предложенное окно проходит validate.
    t = _tenant(hours=ALL_DAY, cfg={**CFG, "days": 1, "lead": 0})
    now = _local(2026, 3, 29, 0, 0)
    row = pickup_slots.slots_for(t, now=now)[0][1]
    assert all(pickup_slots.validate(t, s.isoformat(), now=now) == s for s, _ in row)
    assert len({s for s, _ in row}) == len(row)


def test_abandoned_online_payment_frees_the_slot():
    t = _tenant(cfg={**CFG, "capacity": 1})
    now = _local(2026, 10, 23, 8, 0)
    slot = _local(2026, 10, 23, 10, 0)
    order = _order(slot, payment_method=Order.METHOD_STRIPE)
    offered = lambda: {s for _d, row in pickup_slots.slots_for(t, now=now) for s, _ in row}  # noqa: E731
    assert slot not in offered()
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=1))
    assert slot in offered()
