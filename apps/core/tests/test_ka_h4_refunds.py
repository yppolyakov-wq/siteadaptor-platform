"""KA-H4 (2026-10-23): возврат оплаты при отмене не зависит от экрана.

Раньше Stripe-возврат делали только старые экраны заказа/брони/номера; отмена
с доски, из списка, Lieferungen или общей карточки сделки (`board-action`)
меняла статус, а деньги оставались у бизнеса. Билеты и заявки из кабинета не
возвращались вообще.
"""

import re
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import stripe
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import refunds, transactions
from apps.core import views as core_views
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: calls.append(kw))
    return calls


def _user():
    from django.contrib.auth import get_user_model

    o = uuid.uuid4().hex[:8]
    return get_user_model().objects.create_user(f"h4-{o}", f"h4-{o}@t.de", "pw12345678")


def _tenant(**kw):
    kw.setdefault("stripe_connect_id", "acct_1")
    kw.setdefault("owner_email", "inhaber@t.de")
    return TenantFactory.build(**kw)


def _paid(obj, intent="pi_1", state=None):
    obj.payment_state = state or type(obj).PAYMENT_PAID
    obj.stripe_payment_intent = intent
    obj.save(update_fields=["payment_state", "stripe_payment_intent"])
    return obj


def _order(**kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    kw.setdefault("name", "Max")
    kw.setdefault("email", "max@test.de")
    return create_order(items=[(ProductFactory(base_price=Decimal("8.00")), 1)], **kw)


def _booking():
    from apps.booking import services
    from apps.booking.models import Resource

    start = timezone.now().replace(microsecond=0) + timedelta(days=7)
    res = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    return services.book(res, start=start, end=start + timedelta(hours=1), name="Gast")


def _stay():
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=8000)
    day = timezone.localdate() + timedelta(days=20)
    return services.book_stay(unit, arrival=day, departure=day + timedelta(days=2), name="Gast")


def _ticket():
    from apps.events import services
    from apps.events.models import Event

    start = timezone.now() + timedelta(days=15)
    event = Event.objects.create(
        title="Tour",
        starts_at=start,
        ends_at=start + timedelta(hours=3),
        status=Event.STATUS_PUBLISHED,
        capacity=20,
        price_cents=5000,
    )
    return services.book_ticket(event, name="Gast", email="g@t.de")


def _job():
    from apps.jobs import services

    return services.create_job(title="Bad", name="Kunde")


def _board_post(kind, pk, action, tenant, *, fetch=False, data=None):
    payload = {"action": action, **(data or {})}
    req = RequestFactory().post(f"/dashboard/board/{kind}/{pk}/action/", payload)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _user()
    req.tenant = tenant
    if fetch:
        req.META["HTTP_X_REQUESTED_WITH"] = "fetch"
    return core_views.kanban_action(req, kind, pk), req


# --- все кабинетные поверхности возвращают оплату --------------------------------------


def test_board_action_cancel_paid_order_refunds(stripe_calls):
    order = _paid(_order())
    _board_post("order", order.pk, "cancelled", _tenant())
    order.refresh_from_db()
    assert order.status == "cancelled" and order.payment_state == "refunded"
    assert len(stripe_calls) == 1
    call = stripe_calls[0]
    assert call["payment_intent"] == "pi_1" and call["connect_id"] == "acct_1"
    assert call["idempotency_key"] == refunds._idempotency_key("order", order.pk, "pi_1")


def test_board_action_fetch_also_refunds(stripe_calls):
    order = _paid(_order())
    resp, _req = _board_post("order", order.pk, "cancelled", _tenant(), fetch=True)
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.payment_state == "refunded" and len(stripe_calls) == 1


def test_deal_card_status_form_cancel_refunds_booking_and_stay(stripe_calls):
    from apps.booking.state_machine import BookingSM
    from apps.stays.state_machine import StayBookingSM

    booking = _booking()
    BookingSM().apply(booking, "confirmed")
    _paid(booking)
    stay = _stay()
    StayBookingSM().apply(stay, "confirmed")
    _paid(stay, intent="pi_2")
    form = {"notify_form": "1"}  # общая карточка: чекбоксы сняты
    _board_post("booking", booking.pk, "cancelled", _tenant(), data=form)
    # KA-D3: у брони номера владелец выбирает явно (здесь — «erstatten»)
    _board_post("stay", stay.pk, "cancelled", _tenant(), data={**form, "refund": "1"})
    booking.refresh_from_db()
    stay.refresh_from_db()
    assert booking.payment_state == "refunded" and stay.payment_state == "refunded"
    assert {c["payment_intent"] for c in stripe_calls} == {"pi_1", "pi_2"}


def test_returned_order_refunds_via_apply_action(stripe_calls):
    from apps.orders.state_machine import OrderSM

    order = _order()
    for dst in ("confirmed", "ready", "picked_up"):
        OrderSM().apply(order, dst)
    _paid(order)
    result = transactions.apply_action("order", order, "returned", tenant=_tenant())
    assert result == refunds.RefundResult.REFUNDED
    assert len(stripe_calls) == 1


@pytest.mark.parametrize("state", ["paid", "deposit"])
def test_cabinet_ticket_cancel_refunds(stripe_calls, state):
    ticket = _paid(_ticket(), state=state)
    result = transactions.apply_action("ticket", ticket, "cancelled", tenant=_tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.REFUNDED
    assert ticket.payment_state == "refunded" and len(stripe_calls) == 1


def test_job_cancel_with_paid_deposit_refunds(stripe_calls):
    job = _paid(_job())
    result = transactions.apply_action("job", job, "cancelled", tenant=_tenant())
    assert result == refunds.RefundResult.REFUNDED and len(stripe_calls) == 1


def test_custom_cancelled_role_status_refunds(stripe_calls, monkeypatch):
    from apps.core import status_registry

    tenant = TenantFactory(
        stripe_connect_id="acct_1",
        site_config={
            "status_defs": {"order": [{"code": "kulanz_storno", "role": "cancelled"}]},
            "status_edges": {"order": [{"src": "new", "dst": "kulanz_storno"}]},
        },
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)
    order = _paid(_order())
    result = transactions.apply_action("order", order, "kulanz_storno", tenant=tenant)
    order.refresh_from_db()
    assert order.status == "kulanz_storno"
    assert result == refunds.RefundResult.REFUNDED and len(stripe_calls) == 1


# --- когда НЕ возвращаем -----------------------------------------------------------


def test_no_show_does_not_refund(stripe_calls):
    from apps.booking.state_machine import BookingSM

    booking = _booking()
    BookingSM().apply(booking, "confirmed")
    _paid(booking)
    result = transactions.apply_action("booking", booking, "no_show", tenant=_tenant())
    booking.refresh_from_db()
    assert result == refunds.RefundResult.NONE
    assert booking.payment_state == "paid" and not stripe_calls


def test_non_card_or_no_connect_does_not_call_stripe(stripe_calls):
    unpaid = _order()  # Vorkasse/на месте: unpaid
    assert (
        transactions.apply_action("order", unpaid, "cancelled", tenant=_tenant())
        == refunds.RefundResult.NONE
    )
    no_intent = _paid(_order(), intent="")
    transactions.apply_action("order", no_intent, "cancelled", tenant=_tenant())
    no_connect = _paid(_order())
    transactions.apply_action(
        "order", no_connect, "cancelled", tenant=_tenant(stripe_connect_id="")
    )
    no_connect.refresh_from_db()
    assert no_connect.payment_state == "paid"
    assert not stripe_calls


def test_non_cancel_transition_does_not_refund(stripe_calls):
    order = _paid(_order())
    transactions.apply_action("order", order, "confirmed", tenant=_tenant())
    assert not stripe_calls


# --- повтор, гонка, ошибка Stripe --------------------------------------------------


def test_double_refund_is_impossible(stripe_calls):
    order = _paid(_order())
    transactions.apply_action("order", order, "cancelled", tenant=_tenant())
    stale = type(order).objects.get(pk=order.pk)
    stale.payment_state = "paid"  # устаревшая копия в памяти (вторая вкладка)
    assert refunds.refund_payment("order", stale, _tenant()) == refunds.RefundResult.ALREADY
    assert len(stripe_calls) == 1


def test_stripe_error_keeps_paid_and_notifies_owner(monkeypatch):
    def _boom(**kw):
        raise stripe.error.APIConnectionError("down")

    monkeypatch.setattr("apps.billing.connect.refund", _boom)
    order = _paid(_order())
    result = transactions.apply_action("order", order, "cancelled", tenant=_tenant())
    order.refresh_from_db()
    assert result == refunds.RefundResult.FAILED
    assert order.status == "cancelled" and order.payment_state == "paid"
    note = Notification.objects.get(type="refund_failed_owner")
    assert note.recipient == "inhaber@t.de" and order.reference_code in note.subject


def test_charge_already_refunded_counts_as_success(monkeypatch):
    def _already(**kw):
        raise stripe.error.InvalidRequestError("x", None, code="charge_already_refunded")

    monkeypatch.setattr("apps.billing.connect.refund", _already)
    order = _paid(_order())
    result = transactions.apply_action("order", order, "cancelled", tenant=_tenant())
    order.refresh_from_db()
    assert result == refunds.RefundResult.REFUNDED and order.payment_state == "refunded"
    assert not Notification.objects.filter(type="refund_failed_owner").exists()


# --- паритет старых экранов: одно сообщение, один возврат ---------------------------


def test_order_screen_refunds_once_with_message(stripe_calls):
    from apps.orders import views as order_views

    order = _paid(_order())
    req = RequestFactory().post(f"/dashboard/orders/{order.pk}/action/", {"action": "cancelled"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _user()
    req.tenant = _tenant()
    order_views.order_action(req, pk=order.pk)
    assert len(stripe_calls) == 1
    assert _("Payment refunded.") in [str(m) for m in get_messages(req)]


def test_board_non_fetch_shows_refund_message(stripe_calls):
    order = _paid(_order())
    _resp, req = _board_post("order", order.pk, "cancelled", _tenant())
    assert _("Payment refunded.") in [str(m) for m in get_messages(req)]


# --- одна точка вызова Stripe -------------------------------------------------------


def test_no_direct_connect_refund_outside_refunds_module():
    root = Path(refunds.__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or path.name == "connect.py":
            continue
        if path.name == "refunds.py" and path.parent.name == "core":
            continue
        if re.search(r"connect\.refund\(", path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


# --- ревью KA-H4 -----------------------------------------------------------------------


def test_installment_ticket_is_not_auto_refunded(stripe_calls):
    """R10: в intent лежит только первая доля — «возвращено целиком» было бы ложью."""
    from apps.events.models import InstallmentPlan

    ticket = _paid(_ticket())
    InstallmentPlan.objects.create(ticket=ticket, total_cents=5000, count=3)
    result = transactions.apply_action("ticket", ticket, "cancelled", tenant=_tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.MANUAL
    assert ticket.payment_state == "paid" and not stripe_calls


def test_idempotency_key_depends_on_payment_and_hides_schema():
    a = refunds._idempotency_key("order", 1, "pi_a")
    b = refunds._idempotency_key("order", 1, "pi_b")
    assert a != b and a.startswith("refund:")
    from django.db import connection

    assert connection.schema_name not in a


def test_stale_in_memory_state_still_refunds(stripe_calls):
    """Вебхук оплаты пришёл после загрузки объекта: решение — по БД."""
    order = _order()
    type(order).objects.filter(pk=order.pk).update(
        payment_state="paid", stripe_payment_intent="pi_1"
    )
    order.stripe_payment_intent = "pi_1"  # в памяти payment_state ещё «unpaid»
    result = transactions.apply_action("order", order, "cancelled", tenant=_tenant())
    assert result == refunds.RefundResult.REFUNDED and len(stripe_calls) == 1


def test_board_fetch_reports_refund_header(stripe_calls):
    order = _paid(_order())
    resp, _req = _board_post("order", order.pk, "cancelled", _tenant(), fetch=True)
    assert resp["X-Refund"] == "refunded"


def test_cabinet_ticket_cancel_notifies_waitlist(stripe_calls, monkeypatch):
    from apps.events import views as event_views

    seen = []
    monkeypatch.setattr(event_views, "notify_event_waitlist", lambda ev: seen.append(ev.pk))
    ticket = _paid(_ticket())
    req = RequestFactory().post("/x/", {"target": "cancelled"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _user()
    req.tenant = _tenant()
    event_views.ticket_action(req, pk=ticket.event_id, tid=ticket.pk)
    ticket.refresh_from_db()
    assert ticket.status == "cancelled" and ticket.payment_state == "refunded"
    assert seen == [ticket.event_id]
