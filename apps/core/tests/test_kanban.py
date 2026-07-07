"""U-D2: generischer kanban_action — FSM genau einmal, 409 bei Illegal, Snap-back-
Vertrag, keine doppelte Umsatzbuchung bei Neuzeichnung."""

import uuid
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.core import views

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    pk = 1


def _make_order(**kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"))
    kw.setdefault("name", "Max")
    kw.setdefault("email", "max@test.de")
    return create_order(items=[(product, 1)], **kw)


def _post(kind, pk, action, *, fetch=True):
    req = RequestFactory().post(f"/dashboard/board/{kind}/{pk}/action/", {"action": action})
    req.user = _User()
    if fetch:
        req.META["HTTP_X_REQUESTED_WITH"] = "fetch"
    return req


def _act(kind, pk, action, **kw):
    return views.kanban_action(_post(kind, pk, action, **kw), kind, pk)


def test_apply_advances_status_and_returns_card_html():
    order = _make_order()
    resp = _act("order", order.pk, "confirmed")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == "confirmed"
    assert order.reference_code in resp.content.decode()


def test_revenue_recorded_once_and_redraw_does_not_double():
    from apps.finance.models import RevenueEntry

    order = _make_order()
    _act("order", order.pk, "confirmed")
    _act("order", order.pk, "ready")
    _act("order", order.pk, "picked_up")  # picked_up → record_revenue
    order.refresh_from_db()
    assert order.status == "picked_up"
    assert RevenueEntry.objects.filter(source="order", source_ref=str(order.id)).count() == 1
    # повторный «drop» на тот же статус — apply src==dst no-op → без второй выручки
    resp = _act("order", order.pk, "picked_up")
    assert resp.status_code == 200
    assert RevenueEntry.objects.filter(source="order").count() == 1


def test_illegal_transition_returns_409_and_leaves_status():
    order = _make_order()  # new
    resp = _act("order", order.pk, "picked_up")  # new→picked_up verboten
    assert resp.status_code == 409
    order.refresh_from_db()
    assert order.status == "new"


def test_illegal_transition_non_fetch_redirects_with_message():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    order = _make_order()
    req = _post("order", order.pk, "picked_up", fetch=False)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    resp = views.kanban_action(req, "order", order.pk)
    assert resp.status_code == 302
    assert "kind=order" in resp["Location"]


def test_unknown_kind_bad_request():
    pk = uuid.uuid4()
    resp = views.kanban_action(_post("nope", pk, "x"), "nope", pk)
    assert resp.status_code == 400
