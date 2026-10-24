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


def _installment(ticket, *paid_intents, scheduled=1):
    from apps.events.models import InstallmentCharge, InstallmentPlan

    plan = InstallmentPlan.objects.create(ticket=ticket, total_cents=6000, count=3)
    day = timezone.localdate()
    for i, intent in enumerate(paid_intents, start=1):
        InstallmentCharge.objects.create(
            plan=plan,
            sequence=i,
            due_date=day,
            amount_cents=2000,
            status=InstallmentCharge.STATUS_PAID,
            stripe_payment_intent=intent,
        )
    for j in range(scheduled):
        InstallmentCharge.objects.create(
            plan=plan, sequence=len(paid_intents) + j + 1, due_date=day, amount_cents=2000
        )
    return plan


def test_installment_ticket_refunds_every_paid_share(stripe_calls):
    """KA-12 E1.12 (осознанная переписка KA-H4 «MANUAL»): у каждой доли рассрочки свой
    платёж — при отмене возвращаются ВСЕ оплаченные доли, а не одна первая."""
    ticket = _paid(_ticket(), intent="pi_r1", state="installment")
    plan = _installment(ticket, "pi_r1", "pi_r2")
    result = transactions.apply_action("ticket", ticket, "cancelled", tenant=_tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.REFUNDED
    assert sorted(c["payment_intent"] for c in stripe_calls) == ["pi_r1", "pi_r2"]
    assert ticket.payment_state == "refunded"
    assert not plan.charges.filter(status="paid").exists()
    # повтор — второй возврат не уходит
    assert refunds.refund_payment("ticket", ticket, _tenant()) == refunds.RefundResult.ALREADY
    assert len(stripe_calls) == 2


def test_installment_share_failure_keeps_rest_paid(monkeypatch):
    calls = []

    def _refund(**kw):
        calls.append(kw["payment_intent"])
        if kw["payment_intent"] == "pi_r2":
            raise RuntimeError("stripe down")

    monkeypatch.setattr("apps.billing.connect.refund", _refund)
    ticket = _paid(_ticket(), intent="pi_r1", state="installment")
    plan = _installment(ticket, "pi_r1", "pi_r2")
    result = refunds.refund_payment("ticket", ticket, _tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.FAILED
    statuses = dict(plan.charges.values_list("stripe_payment_intent", "status"))
    assert statuses == {"pi_r1": "refunded", "pi_r2": "paid", "": "scheduled"}
    assert ticket.payment_state == "installment"  # не «возвращено целиком»


def test_custom_cancel_without_refund_keeps_payment(stripe_calls):
    """KA-12 E1.12: свой статус отмены с флагом «ohne Erstattung»."""
    tenant = _tenant(
        site_config={
            "status_defs": {
                "order": [
                    {
                        "code": "storno_nr",
                        "label": "Storno ohne Erstattung",
                        "role": "cancelled",
                        "stage": "terminal",
                        "no_refund": True,
                    }
                ]
            }
        }
    )
    from apps.tenants import siteconfig

    tenant.site_config = siteconfig.normalize(tenant.site_config)
    assert refunds.wants_refund("order", "storno_nr", "new", tenant) is False
    assert refunds.wants_refund("order", "cancelled", "new", tenant) is True


def test_no_refund_flag_survives_normalize_only_for_cancel_role():
    from apps.tenants import siteconfig

    defs = siteconfig.normalize_status_defs(
        {
            "order": [
                {
                    "code": "a_x",
                    "label": "A",
                    "role": "cancelled",
                    "stage": "terminal",
                    "no_refund": True,
                },
                {
                    "code": "b_x",
                    "label": "B",
                    "role": "active",
                    "stage": "in_progress",
                    "no_refund": True,
                },
                {"code": "c_x", "label": "C", "role": "cancelled", "stage": "terminal"},
            ]
        }
    )["order"]
    by = {d["code"]: d for d in defs}
    assert by["a_x"]["no_refund"] is True
    assert "no_refund" not in by["b_x"] and "no_refund" not in by["c_x"]  # presence-minimal


def test_deposit_by_card_and_rest_in_cash_tells_owner_the_rest(stripe_calls):
    """KA-12 E1.6: депозит вернула карта, а наличный остаток — владельцу вернуть самому."""
    from apps.core.money_contract import settle_payment

    stay = _stay()
    stay.deposit_cents = 3000
    stay.save(update_fields=["deposit_cents"])
    _paid(stay, intent="pi_dep", state="deposit")
    settle_payment("stay", stay)
    stay.refresh_from_db()
    assert stay.payment_state == "paid"
    result = refunds.refund_payment("stay", stay, _tenant())
    assert result == refunds.RefundResult.REFUNDED and len(stripe_calls) == 1
    rest = refunds._OFFLINE_REST.get()
    assert rest == Decimal(stay.total_cents - 3000) / 100
    assert Notification.objects.filter(type="refund_rest_owner").count() == 1

    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    refunds.flash(req, result, "stay")
    texts = [str(m) for m in get_messages(req)]
    assert any("Restbetrag" in t for t in texts)


def test_full_card_payment_has_no_rest_hint(stripe_calls):
    order = _paid(_order())
    assert refunds.refund_payment("order", order, _tenant()) == refunds.RefundResult.REFUNDED
    assert refunds._OFFLINE_REST.get() == 0
    assert not Notification.objects.filter(type="refund_rest_owner").exists()


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


# --- ревью KA-12 W3 батч 1 -------------------------------------------------------------


def test_installment_without_paid_shares_is_not_marked_refunded(stripe_calls):
    """Ничего не оплачено — ничего не «возвращено» (раньше состояние ставилось ложно)."""
    ticket = _paid(_ticket(), intent="", state="installment")
    _installment(ticket, scheduled=2)
    result = refunds.refund_payment("ticket", ticket, _tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.NONE
    assert ticket.payment_state == "installment"
    assert stripe_calls == []


def test_installment_share_paid_outside_stripe_is_manual(stripe_calls):
    """Доля, оплаченная без платежа Stripe, — не молчаливое NONE, а MANUAL + письмо."""
    ticket = _paid(_ticket(), intent="pi_r1", state="installment")
    plan = _installment(ticket, "pi_r1", "", scheduled=0)
    result = refunds.refund_payment("ticket", ticket, _tenant())
    ticket.refresh_from_db()
    assert result == refunds.RefundResult.MANUAL
    assert [c["payment_intent"] for c in stripe_calls] == ["pi_r1"]
    assert plan.charges.filter(status="paid", stripe_payment_intent="").exists()
    assert ticket.payment_state == "installment"


def test_custom_no_refund_cancel_keeps_revenue(monkeypatch):
    """«ohne Erstattung»: деньги остаются у бизнеса — сторно выручки не делается."""
    from apps.core import status_effects
    from apps.core.status_registry import StatusDescriptor

    calls = []
    monkeypatch.setattr(status_effects, "record_reversal_for", lambda k, i: calls.append(k))
    for name in ("restore_stock_for", "unredeem_for"):
        monkeypatch.setattr(status_effects, name, lambda *a, **kw: None)
    src = StatusDescriptor(code="done_x", role="done", stage="done", revenue_recognized=True)
    keep = StatusDescriptor(
        code="storno_nr", role="cancelled", stage="terminal", builtin=False, no_refund=True
    )
    plain = StatusDescriptor(code="storno", role="cancelled", stage="terminal", builtin=False)
    status_effects.apply_custom_effects("order", object(), src, keep)
    assert calls == []
    status_effects.apply_custom_effects("order", object(), src, plain)
    assert calls == ["order"]


def test_staff_cannot_set_no_refund(monkeypatch):
    """Флаг «ohne Erstattung» — политика денег: сотрудник его не включает и не снимает."""
    from apps.core import roles
    from apps.tenants import siteconfig

    defs = {
        "order": [
            {"code": "st_a", "label": "A", "role": "cancelled", "stage": "terminal"},
            {
                "code": "st_b",
                "label": "B",
                "role": "cancelled",
                "stage": "terminal",
                "no_refund": True,
            },
        ]
    }
    tenant = TenantFactory(site_config={"status_defs": defs})
    data = {
        "custom_code": ["st_a", "st_b"],
        "label_st_a": "A",
        "role_st_a": "cancelled",
        "norefund_st_a": "on",
        "label_st_b": "B",
        "role_st_b": "cancelled",
        "new_label": "Neu Storno",
        "new_role": "cancelled",
        "new_no_refund": "on",
    }
    monkeypatch.setattr(roles, "is_owner", lambda user: False)
    request = RequestFactory().post("/dashboard/status-manager/order/save/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = tenant
    core_views.status_manager_save(request, kind="order")
    tenant.refresh_from_db()
    saved = {
        d["code"]: d
        for d in siteconfig.normalize_status_defs(tenant.site_config["status_defs"])["order"]
    }
    assert "no_refund" not in saved["st_a"]  # не включил
    assert saved["st_b"]["no_refund"] is True  # не снял
    assert "no_refund" not in saved["neu_storno"]


def test_discount_change_on_certificate_paid_deal_is_refused():
    """Сумма сертификата читается из discount_cents — правка скидки сдвинула бы оплату."""
    from apps.core import deal_discount
    from apps.loyalty.models import Voucher
    from apps.orders import editing

    Voucher.objects.create(code="WERT05", label="Gutschein", balance_cents=500)
    order = _order()
    order.voucher_code = "WERT05"
    order.discount_cents = 500
    order.save(update_fields=["voucher_code", "discount_cents"])
    with pytest.raises(editing.OrderLocked):
        editing.set_discount(order, cents=1500)
    with pytest.raises(deal_discount.CertificateLocked):
        deal_discount.set_discount("stay", _cert_stay("WERT05"), cents=0)
    order.refresh_from_db()
    assert order.discount_cents == 500
    # та же сумма — не правка (повторное сохранение формы не ломается)
    editing.set_discount(order, cents=500)


def _cert_stay(code):
    stay = _stay()
    stay.voucher_code = code
    stay.discount_cents = 500
    stay.save(update_fields=["voucher_code", "discount_cents"])
    return stay
