"""KA-12 B2-6 (E1.10): напоминание перед событием называет остаток билета.

Онлайн-оплата доступна — ссылка на доплату; нет — «vor Ort» (решение владельца
E-1). Полностью оплаченный или ожидающий первой оплаты билет строки не получает."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core import balance_pay, money_contract
from apps.events import notifications, services
from apps.events.models import Event, Ticket

pytestmark = pytest.mark.django_db


def _ticket(state):
    event = Event.objects.create(
        title="Retreat",
        starts_at=timezone.now() + timedelta(days=3),
        status=Event.STATUS_PUBLISHED,
        capacity=20,
        price_cents=10000,
    )
    ticket = services.book_ticket(event, name="A", email="a@test.de", auto_confirm=True)
    Ticket.objects.filter(pk=ticket.pk).update(payment_state=state, deposit_cents=3000)
    ticket.refresh_from_db()
    return ticket


def test_deposit_ticket_gets_rest_and_link(monkeypatch):
    monkeypatch.setattr(balance_pay, "rest_payable", lambda *a: True)
    ticket = _ticket(Ticket.PAYMENT_DEPOSIT)
    ctx = notifications._rest_context(ticket, SimpleNamespace(), "https://x.test")
    due = money_contract.due("ticket", ticket)
    assert due > 0
    assert ctx["rest_eur"] == f"{due:.2f}".replace(".", ",")
    assert ctx["rest_url"] == f"https://x.test/{balance_pay.pay_path('ticket', ticket).lstrip('/')}"


def test_without_online_payment_says_on_site(monkeypatch):
    monkeypatch.setattr(balance_pay, "rest_payable", lambda *a: False)
    ticket = _ticket(Ticket.PAYMENT_DEPOSIT)
    ctx = notifications._rest_context(ticket, SimpleNamespace(), "https://x.test")
    assert ctx["rest_eur"] and ctx["rest_url"] == ""
    from django.template.loader import render_to_string

    body = render_to_string(
        "emails/ticket_reminder.txt",
        {"ticket": ticket, "event": ticket.event, "customer": ticket.customer, **ctx},
    )
    assert ctx["rest_eur"] in body and "vor Ort" in body


@pytest.mark.parametrize("state", [Ticket.PAYMENT_PAID, Ticket.PAYMENT_PENDING])
def test_paid_or_pending_ticket_gets_no_rest_line(state):
    ticket = _ticket(state)
    assert notifications._rest_context(ticket, SimpleNamespace(), "https://x.test") == {}
