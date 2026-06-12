"""Track D / D2b: кабинет заказов — список/карточка/действия, письма по
статусам (Notification + БД-дедуп), оплата вручную, 360° в CRM."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import services, views
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/orders/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _order(email=None):
    return services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 2)],
        name="Kunde K",
        email=email or f"k-{uuid.uuid4().hex[:8]}@test.de",
    )


# --- письма ----------------------------------------------------------------------


def test_create_order_enqueues_customer_email():
    order = _order()
    notification = Notification.objects.get(dedupe_key=f"order:{order.id}:created:customer")
    assert notification.type == "order_created"
    assert order.reference_code in notification.payload["body"]


def test_transitions_enqueue_emails_with_dedupe():
    order = _order()
    sm = OrderSM()
    order = sm.apply(order, "confirmed")
    order = sm.apply(order, "ready")
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:confirmed:customer").exists()
    ready = Notification.objects.get(dedupe_key=f"order:{order.id}:ready:customer")
    assert "abholbereit" in ready.payload["body"].lower()
    # повтор того же статуса — no-op, дубль письма не создаётся (БД-дедуп)
    sm.apply(order, "ready")
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").count() == 1


# --- кабинет ---------------------------------------------------------------------


def test_order_list_renders_and_filters():
    order = _order()
    body = views.order_list(_req()).content.decode()
    assert order.reference_code in body and "Brot" in body
    body = views.order_list(_req(data={"status": "cancelled"})).content.decode()
    assert order.reference_code not in body


def test_order_detail_shows_items_and_actions():
    order = _order()
    body = views.order_detail(_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    body = body.content.decode()
    assert order.reference_code in body
    assert "2× Brot" in body
    assert 'value="confirmed"' in body and 'value="cancelled"' in body
    assert 'value="ready"' not in body  # из new сразу в ready нельзя


def test_order_action_transitions_and_payment():
    order = _order()
    response = views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "confirmed"}), pk=order.pk
    )
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == "confirmed"

    views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "mark_paid"}), pk=order.pk
    )
    order.refresh_from_db()
    assert order.payment_state == "paid"

    # запрещённый переход не меняет статус
    views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "picked_up"}), pk=order.pk
    )
    order.refresh_from_db()
    assert order.status == "confirmed"


def test_crm_card_shows_orders():
    from apps.crm.views import customer_detail

    order = _order(email="kunde360@test.de")
    body = customer_detail(
        _req(path=f"/crm/{order.customer.pk}/"), pk=order.customer.pk
    ).content.decode()
    assert order.reference_code in body


def test_nav_includes_orders_when_active():
    from apps.core import modules
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build()
    keys = [s.key for s in modules.active_modules(tenant)]
    assert "orders" in keys
    spec = modules.get_module("orders")
    assert spec.nav_items and spec.nav_items[0].url_name == "orders:order-list"
