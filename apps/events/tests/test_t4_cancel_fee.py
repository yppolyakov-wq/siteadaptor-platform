"""KA-12 T-4 (EV-3): шкала Stornogebühr «ab N Tagen vor Beginn: P %».

Было: только «бесплатно до N дней» или «невозвратно» — частично вернуть нельзя,
владелец считал штраф вручную и возвращал мимо системы. Стало: шкала у события,
самоотмена гостем удерживает процент и возвращает остаток картой (по нескольким
платежам), пусто = прежнее правило (решение О-2)."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

from apps.billing import connect
from apps.core import folio, refunds
from apps.core.models import DealPayment
from apps.events import details, public_views, services
from apps.events.forms import EventForm
from apps.events.models import Event, Ticket
from apps.events.services import book_ticket

pytestmark = pytest.mark.django_db

STEPS = [{"days": 30, "percent": 0}, {"days": 14, "percent": 50}, {"days": 0, "percent": 100}]
TENANT = SimpleNamespace(
    stripe_connect_id="acct_test",
    owner_email="o@t.de",
    schema_name="x",
    is_module_active=lambda name: True,
)


@pytest.fixture
def stripe_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(connect, "refund", lambda **kw: calls.append(kw))
    return calls


def _event(days=10, **kw):
    data = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=days, hours=1),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 10000,
        "capacity": 10,
        "cancel_fee_steps": STEPS,
    }
    data.update(kw)
    return Event.objects.create(**data)


def _paid(event, state=Ticket.PAYMENT_PAID, **kw):
    ticket = book_ticket(event, name="A", email="a@test.de", auto_confirm=True)
    ticket.payment_state = state
    ticket.stripe_payment_intent = "pi_t"
    for k, v in kw.items():
        setattr(ticket, k, v)
    ticket.save()
    return ticket


def _post(token):
    req = RequestFactory().post("/")
    req.tenant = TENANT
    req.session = {}
    req._messages = FallbackStorage(req)
    return public_views.veranstaltung_cancel(req, token)


# --- шкала ---------------------------------------------------------------------


def test_steps_parse_sort_and_drop_garbage():
    raw = "14 | 50\n30=0\nfoo\n0:100 %\n400 | 10\n14 | 70\n7 | 150"
    assert details.normalize_fee_steps(raw) == STEPS
    assert details.fee_steps_to_text(STEPS) == "30 | 0\n14 | 50\n0 | 100"


@pytest.mark.parametrize(
    ("days_left", "percent"), [(40, 0), (30, 0), (20, 0), (14, 50), (5, 50), (0, 100), (-1, 100)]
)
def test_fee_percent_by_days_left(days_left, percent):
    assert details.fee_percent(STEPS, days_left) == percent


def test_state_uses_steps_over_free_cancel_days():
    ticket = book_ticket(_event(days=10, free_cancel_days=0), name="A", email="a@t.de")
    state = services.cancellation_state(ticket)
    assert state["fee_percent"] == 50 and state["free"] is False


def test_state_without_steps_unchanged():
    event = _event(days=10, cancel_fee_steps=[], free_cancel_days=7)
    state = services.cancellation_state(book_ticket(event, name="A", email="a@t.de"))
    assert state["free"] is True and state["fee_percent"] == 0
    nonref = _event(cancellation=Event.CANCEL_NONREF)
    assert (
        services.cancellation_state(book_ticket(nonref, name="B", email="b@t.de"))["fee_percent"]
        == 100
    )


# --- расчёт удержания ------------------------------------------------------------


def test_split_paid_deposit_unpaid_installment():
    event = _event(days=10)
    paid = _paid(event)
    state = services.cancellation_state(paid)
    assert services.cancel_fee_split(paid, state) == {
        "mode": "partial",
        "percent": 50,
        "retained_cents": 5000,
        "refund_cents": 5000,
        "refund_eur": Decimal("50.00"),
    }
    deposit = _paid(event, state=Ticket.PAYMENT_DEPOSIT, deposit_cents=3001)
    split = services.cancel_fee_split(deposit, state)
    assert (split["retained_cents"], split["refund_cents"]) == (1501, 1500)
    unpaid = book_ticket(event, name="C", email="c@t.de")
    assert services.cancel_fee_split(unpaid, state)["mode"] == "keep"
    inst = _paid(event, state=Ticket.PAYMENT_INSTALLMENT)
    assert services.cancel_fee_split(inst, state)["mode"] == "free"  # в пользу клиента


# --- самоотмена ------------------------------------------------------------------


def test_self_cancel_keeps_fee_and_refunds_rest(stripe_calls):
    ticket = _paid(_event(days=10))
    _post(public_views.cancel_token(ticket))
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_CANCELLED
    assert [c["amount_cents"] for c in stripe_calls] == [5000]
    rows = DealPayment.objects.filter(deal_kind="ticket", deal_id=ticket.pk)
    assert sum(r.refunded_cents for r in rows) == 5000
    assert ticket.payment_state == Ticket.PAYMENT_PAID  # вернули часть — не «возвращено»


def test_self_cancel_free_window_refunds_all(stripe_calls):
    ticket = _paid(_event(days=40))
    _post(public_views.cancel_token(ticket))
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_CANCELLED
    assert ticket.payment_state == Ticket.PAYMENT_REFUNDED


def test_self_cancel_last_step_refunds_nothing(stripe_calls):
    ticket = _paid(_event(days=0, starts_at=timezone.now() + timedelta(hours=5)))
    _post(public_views.cancel_token(ticket))
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_CANCELLED and stripe_calls == []


def test_fee_refund_spans_two_card_payments(stripe_calls):
    ticket = _paid(_event(days=10))
    for intent, cents in (("pi_dep", 3000), ("pi_rest", 7000)):
        DealPayment.objects.create(
            deal_kind="ticket",
            deal_id=ticket.pk,
            purpose="full",
            method="stripe",
            amount_cents=cents,
            stripe_payment_intent=intent,
            source="webhook",
        )
    folio.forget(ticket)
    ticket.status = Ticket.STATUS_CANCELLED
    ticket.save(update_fields=["status"])
    result = refunds.refund_cancel_fee("ticket", ticket, retained_cents=2000, tenant=TENANT)
    assert result == refunds.RefundResult.REFUNDED
    assert sorted(c["amount_cents"] for c in stripe_calls) == [1000, 7000]
    # Повтор (двойной клик/ретрай): цель уже достигнута — удержанное не уходит.
    refunds.refund_cancel_fee("ticket", ticket, retained_cents=2000, tenant=TENANT)
    assert len(stripe_calls) == 2


def test_second_post_does_not_refund_retained_fee(stripe_calls, monkeypatch):
    ticket = _paid(_event(days=10))
    token = public_views.cancel_token(ticket)
    _post(token)
    # Гонка: второй запрос прочитал билет ДО коммита первого (видит «можно отменить»);
    # под блокировкой он видит «cancelled» и до возврата не доходит.
    real = services.cancellation_state
    calls = []

    def stale(t, now=None):
        calls.append(1)
        if len(calls) == 1:
            return {"can_cancel": True, "free": False, "deadline": None, "fee_percent": 50}
        return real(t, now)

    monkeypatch.setattr(services, "cancellation_state", stale)
    _post(token)
    assert [c["amount_cents"] for c in stripe_calls] == [5000]


def test_storno_cap_inside_refund_partial(stripe_calls):
    ticket = _paid(_event(days=10))
    ticket.status = Ticket.STATUS_CANCELLED
    ticket.save(update_fields=["status"])
    folio.ensure_opening("ticket", ticket)
    over = refunds.refund_partial(
        "ticket",
        ticket,
        cents=6000,
        method="card",
        tenant=TENANT,
        reason="stornogebuehr",
        storno_target=5000,
    )
    assert over == refunds.RefundResult.REFUSED and stripe_calls == []


def test_after_start_is_full_fee_even_without_zero_step():
    event = _event(
        days=0,
        starts_at=timezone.now() - timedelta(hours=1),
        cancel_fee_steps=[{"days": 30, "percent": 0}],
    )
    ticket = book_ticket(event, name="A", email="a@t.de")
    assert services.cancellation_state(ticket)["fee_percent"] == 100


def test_storno_reason_refused_for_active_deal(stripe_calls):
    ticket = _paid(_event(days=10))
    result = refunds.refund_partial(
        "ticket",
        ticket,
        cents=1000,
        method="card",
        tenant=TENANT,
        reason="stornogebuehr",
        storno_target=5000,
    )
    assert result == refunds.RefundResult.REFUSED and stripe_calls == []


def test_no_connect_tells_owner(stripe_calls, monkeypatch):
    sent = []
    monkeypatch.setattr(refunds, "_notify_owner_failed", lambda *a, **kw: sent.append(kw))
    ticket = _paid(_event(days=10))
    ticket.status = Ticket.STATUS_CANCELLED
    ticket.save(update_fields=["status"])
    no_connect = SimpleNamespace(stripe_connect_id="", owner_email="o@t.de")
    result = refunds.refund_cancel_fee("ticket", ticket, retained_cents=5000, tenant=no_connect)
    assert result == refunds.RefundResult.FAILED and sent and sent[0]["cents"] == 5000


# --- кабинет и витрина -------------------------------------------------------------


def _form_data(event, **extra):
    data = {
        "title": event.title,
        "starts_at": event.starts_at.strftime("%Y-%m-%dT%H:%M"),
        "capacity": event.capacity,
        "price_eur": "100",
    }
    data.update(extra)
    return data


def test_form_writes_steps_only_when_field_sent():
    event = _event(days=10)
    form = EventForm(_form_data(event), instance=event)
    assert form.is_valid(), form.errors
    assert form.save().cancel_fee_steps == STEPS  # поле не пришло — шкала цела (W0)
    form = EventForm(_form_data(event, cancel_fee_text="7 | 80"), instance=event)
    assert form.is_valid(), form.errors
    assert form.save().cancel_fee_steps == [{"days": 7, "percent": 80}]
    assert EventForm(instance=event).fields["cancel_fee_text"].initial == "7 | 80"


def test_storefront_partials_show_scale():
    event = _event(days=10)
    html = render_to_string("storefront/_event_cancel_fees.html", {"event": event})
    assert "data-cancel-fees" in html and "50 %" in html
    event.cancellation = Event.CANCEL_NONREF
    assert "data-cancel-fees" not in render_to_string(
        "storefront/_event_cancel_fees.html", {"event": event}
    )
