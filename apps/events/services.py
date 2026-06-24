"""Покупка билета на событие с анти-овердрафтом мест (A6).

Внутри транзакции блокируем строку Event (select_for_update — конкурентные
покупки сериализуются), считаем проданные места и пускаем, только если
capacity безлимитна или хватает мест. Customer переиспользуется по email.
"""

import secrets
import string

from django.db import models, transaction

from apps.promotions.models import Customer

from .models import Event, EventWaitlistEntry, Ticket

_ALPHABET = string.ascii_uppercase + string.digits


class SoldOut(Exception):
    """Не хватает свободных мест на запрошенное количество."""

    def __init__(self, available=0):
        self.available = available
        super().__init__(f"sold out (available {available})")


class EventNotBookable(Exception):
    """Событие не опубликовано / отменено."""


def _unique_ticket_code() -> str:
    for _ in range(10):
        code = "E-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Ticket.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique ticket code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


@transaction.atomic
def book_ticket(
    event,
    *,
    name,
    email="",
    phone="",
    quantity=1,
    answers=None,
    note="",
    source_channel="",
    auto_confirm=False,
    tier_label="",
    extras=None,
):
    """Создать билет, атомарно проверив наличие мест. Бросает ValueError,
    EventNotBookable, SoldOut. tier_label (A6) — выбранный ценовой тир: цена
    билета берётся из него (иначе event.price_cents). extras (#7) — доп-услуги."""
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    event_id = getattr(event, "id", event)
    event = Event.objects.select_for_update().get(id=event_id)
    if not event.is_published:
        raise EventNotBookable()

    if event.capacity:
        sold = (
            event.tickets.filter(status__in=Ticket.ACTIVE_STATUSES).aggregate(
                n=models.Sum("quantity")
            )["n"]
            or 0
        )
        available = event.capacity - sold
        if quantity > available:
            raise SoldOut(available=max(available, 0))

    # Цена из выбранного тира (Frühbucher/Standard…), иначе единая цена события.
    matched_tier = next((t for t in event.tier_list if t["label"] == tier_label), None)
    price_cents = matched_tier["price_cents"] if matched_tier else event.price_cents
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    ticket = Ticket.objects.create(
        event=event,
        customer=customer,
        reference_code=_unique_ticket_code(),
        quantity=quantity,
        price_cents=price_cents,
        tier_label=matched_tier["label"] if matched_tier else "",
        status=Ticket.STATUS_PENDING,
        answers=answers or {},
        extras=list(extras or []),
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо «Anmeldung erhalten» — Notification в этой же транзакции (A6c)
    from .notifications import enqueue_ticket_email

    enqueue_ticket_email(ticket, "created")
    # auto_confirm (ручная запись/оплата) → переводим FSM-ом, чтобы сработал
    # finance-хук (выручка пишется на pending→confirmed, идемпотентно).
    if auto_confirm:
        from .state_machine import TicketSM

        TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    return ticket


def join_waitlist(event, *, name="", email="", phone="", party_size=1) -> EventWaitlistEntry:
    """Записать e-mail в лист ожидания события (идемпотентно по event+email)."""
    entry, _created = EventWaitlistEntry.objects.get_or_create(
        event=event,
        email=email.lower(),
        defaults={
            "name": (name or "")[:200],
            "phone": (phone or "")[:40],
            "party_size": max(1, min(int(party_size or 1), 50)),
        },
    )
    return entry


def notify_event_waitlist(event) -> int:
    """Уведомить ещё не оповещённых из листа ожидания, если есть свободные места.

    Шлёт одно письмо на запись (R1), помечает notified=True. Возвращает число
    отправленных. Безлимитное событие (capacity=0) — тоже шлёт (мест всегда хватает.)
    """
    left = event.seats_left  # None = безлимит
    if left is not None and left <= 0:
        return 0
    from .notifications import enqueue_event_waitlist_available

    pending = event.waitlist.filter(notified=False).order_by("created_at")
    sent = 0
    for entry in pending:
        enqueue_event_waitlist_available(entry)
        entry.notified = True
        entry.save(update_fields=["notified", "updated_at"])
        sent += 1
    return sent
