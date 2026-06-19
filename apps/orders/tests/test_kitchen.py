"""A4 KDS: Küchen-Display — доска активных заказов + действия Annehmen/Fertig."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.orders import services, views
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/orders/kitchen/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _order():
    return services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 2)],
        name="Kunde K",
        email=f"k-{uuid.uuid4().hex[:8]}@test.de",
    )


def test_kitchen_lists_active_orders_only():
    new = _order()
    done = _order()
    done.status = Order.STATUS_PICKED_UP
    done.save(update_fields=["status"])

    body = views.kitchen(_req()).content.decode()
    assert new.reference_code in body
    assert done.reference_code not in body  # завершённый не на доске


def test_kitchen_action_accept_then_ready():
    order = _order()
    # Annehmen: new → confirmed
    views.kitchen_action(_req("post", data={"action": "confirmed"}), pk=order.pk)
    order.refresh_from_db()
    assert order.status == Order.STATUS_CONFIRMED

    # Fertig: confirmed → ready (покидает доску)
    resp = views.kitchen_action(_req("post", data={"action": "ready"}), pk=order.pk)
    order.refresh_from_db()
    assert order.status == Order.STATUS_READY
    assert order.reference_code not in resp.content.decode()


def test_kitchen_board_shows_order_note():
    """T1: комментарий к заказу (повару) виден на KDS-доске."""
    services.create_order(
        items=[(ProductFactory(name={"de": "Pizza"}), 1)],
        name="Kunde K",
        email=f"k-{uuid.uuid4().hex[:8]}@test.de",
        note="Bitte ohne Zwiebeln",
    )
    body = views.kitchen(_req()).content.decode()
    assert "Bitte ohne Zwiebeln" in body


def test_table_qr_page_renders_codes():
    """T2a: лист QR-кодов столов рендерит N кодов."""
    req = _req(path="/dashboard/orders/tisch-qr/", data={"count": "3"})
    body = views.table_qr(req).content.decode()
    assert body.count("data:image/svg+xml") >= 3


def test_kitchen_action_illegal_is_noop():
    order = _order()
    order.status = Order.STATUS_PICKED_UP
    order.save(update_fields=["status"])
    # «ready» из picked_up недопустим — не падаем, статус не меняется
    views.kitchen_action(_req("post", data={"action": "ready"}), pk=order.pk)
    order.refresh_from_db()
    assert order.status == Order.STATUS_PICKED_UP
