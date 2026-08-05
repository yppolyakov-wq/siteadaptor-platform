"""W7c (аудит кабинета 2026-08-05): продажные предохранители — паритет поведения
доски (FSM-путь) и карточек (сервис-путь).

1. Действия заказа на канбане фильтруются по способу получения (is_delivery).
2. «Versendet» с доски пишет shipped_at (раньше NULL — ставила только вьюха карточки).
3. Резерв с доски получает confirmed_at/fulfilled_at/cancelled_at (раньше — только сервисы).
4. Primary-вкладка Verkäufe гейтится модулем своего kind (catalog→order кросс-модульный).
5. Generic-Liste сортируется по дате события (не created_at).
6. kanban_action non-fetch возвращает на исходную поверхность (next=).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.core import sales_page, transactions, views

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    pk = 1
    username = "owner"


def _make_order(**kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"))
    kw.setdefault("name", "Max")
    kw.setdefault("email", "max@test.de")
    return create_order(items=[(product, 1)], **kw)


# --- 1. is_delivery-фильтр действий -------------------------------------------
def _targets(obj):
    return {a["target"] for a in transactions.allowed_actions_for("order", "ready", obj=obj)}


def test_ready_delivery_order_offers_shipped_not_picked_up():
    t = _targets(SimpleNamespace(is_delivery=True))
    assert "shipped" in t and "picked_up" not in t


def test_ready_pickup_order_offers_picked_up_not_shipped():
    t = _targets(SimpleNamespace(is_delivery=False))
    assert "picked_up" in t and "shipped" not in t


def test_without_obj_both_targets_remain():  # fail-open для вызовов без объекта
    t = {a["target"] for a in transactions.allowed_actions_for("order", "ready")}
    assert {"picked_up", "shipped"} <= t


# --- 2. shipped_at с доски -----------------------------------------------------
def test_board_shipped_sets_shipped_at():
    from apps.orders.state_machine import OrderSM

    order = _make_order()
    sm = OrderSM()
    sm.apply(order, "confirmed")
    sm.apply(order, "ready")
    sm.apply(order, "shipped")  # FSM-путь доски, мимо вьюхи карточки
    order.refresh_from_db()
    assert order.shipped_at is not None


# --- 3. таймстемпы резерва с доски --------------------------------------------
def _make_reservation():
    from apps.promotions import services as promo_services
    from apps.promotions.tests.factories import PromotionFactory

    return promo_services.reserve(PromotionFactory(), name="Gast", email="g@test.de")


def test_board_reservation_transitions_set_timestamps():
    from apps.promotions import services as promo_services
    from apps.promotions.state_machine import ReservationSM

    res = _make_reservation()
    ReservationSM().apply(res, "confirmed")  # FSM-путь доски (kanban_action)
    res.refresh_from_db()
    assert res.confirmed_at is not None
    ReservationSM().apply(res, "cancelled")
    res.refresh_from_db()
    assert res.cancelled_at is not None
    # сервис-путь по-прежнему ставит свои таймстемпы сам (no-op в FSM)
    res2 = _make_reservation()
    promo_services.confirm(res2)
    res2.refresh_from_db()
    assert res2.confirmed_at is not None


# --- 4. primary-kind гейтится модулем -----------------------------------------
def test_visible_kinds_hides_order_tab_without_orders_module():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        business_type="other",
        disabled_modules=["orders", "events", "stays", "booking", "jobs"],
    )
    assert "order" not in sales_page.visible_kinds(tenant)


def test_visible_kinds_keeps_order_tab_with_orders_module():
    from apps.tenants.tests.factories import TenantFactory

    # S6-пресет пекарни: primary=catalog (→kind order), модуль orders активен.
    tenant = TenantFactory(
        business_type="bakery", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    assert "order" in sales_page.visible_kinds(tenant)


# --- 5. Liste по дате события --------------------------------------------------
def test_managed_queryset_event_order():
    assert transactions._managed_queryset("stay", event_order=True).query.order_by == ("-arrival",)
    assert transactions._managed_queryset("booking", event_order=True).query.order_by == ("-start",)
    # прочие kind'ы и дефолт — по created_at (доска не меняется)
    assert transactions._managed_queryset("order", event_order=True).query.order_by == (
        "-created_at",
    )
    assert transactions._managed_queryset("stay").query.order_by == ("-created_at",)


# --- 6. kanban non-fetch → next -------------------------------------------------
def test_kanban_non_fetch_redirects_to_next():
    order = _make_order()
    req = RequestFactory().post(
        f"/dashboard/board/order/{order.pk}/action/",
        {"action": "confirmed", "next": "/dashboard/verkaeufe/?tab=order&view=board"},
    )
    req.user = _User()
    resp = views.kanban_action(req, "order", order.pk)
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/verkaeufe/?tab=order&view=board"


def test_kanban_non_fetch_rejects_external_next():
    order = _make_order()
    req = RequestFactory().post(
        f"/dashboard/board/order/{order.pk}/action/",
        {"action": "confirmed", "next": "https://evil.example/x"},
    )
    req.user = _User()
    resp = views.kanban_action(req, "order", order.pk)
    assert resp.status_code == 302
    assert resp["Location"].startswith("/dashboard/board/")


# --- W10-5: единый apply_action + трек-номер с доски ---------------------------
def test_apply_action_writes_tracking_before_shipped_email():
    """W10-5: «Versendet» через единую точку → письмо уходит С Sendungsnummer
    (раньше доска слала без номера — audit-sales HIGH)."""
    from apps.core import transactions
    from apps.notifications.models import Notification

    order = _make_delivery_order()
    transactions.apply_action("order", order, "confirmed", extra={})
    transactions.apply_action("order", order, "ready", extra={})
    transactions.apply_action("order", order, "shipped", extra={"tracking_code": "  DHL-W105  "})
    order.refresh_from_db()
    assert order.tracking_code == "DHL-W105"
    assert order.shipped_at is not None  # FSM (W7c)
    shipped = Notification.objects.get(dedupe_key=f"order:{order.id}:shipped:customer")
    assert "DHL-W105" in shipped.payload["body"]


def test_kanban_card_shows_tracking_input_only_for_delivery_ready():
    """Поле трек-номера — только у заказа-доставки с доступным shipped."""
    from apps.core import transactions

    order = _make_delivery_order()
    transactions.apply_action("order", order, "confirmed", extra={})
    transactions.apply_action("order", order, "ready", extra={})
    order.refresh_from_db()
    tx = transactions.transaction_for("order", order)
    assert tx.needs_tracking is True
    # заказ-самовывоз в том же статусе — поля нет (shipped недоступен)
    pickup = _make_pickup_order()
    transactions.apply_action("order", pickup, "confirmed", extra={})
    transactions.apply_action("order", pickup, "ready", extra={})
    pickup.refresh_from_db()
    tx2 = transactions.transaction_for("order", pickup)
    assert tx2.needs_tracking is False


def _make_delivery_order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services

    return services.create_order(
        items=[(ProductFactory(name={"de": "Paketware"}), 1)],
        name="Empfänger",
        email="emp@t.de",
        fulfillment="delivery",
        shipping_address="Weg 1, Hilden",
    )


def _make_pickup_order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services

    return services.create_order(
        items=[(ProductFactory(name={"de": "Abholware"}), 1)],
        name="Abholer2",
        email="ab2@t.de",
    )
