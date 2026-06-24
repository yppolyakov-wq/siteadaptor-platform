"""Покупка билета на событие с анти-овердрафтом мест (A6).

Внутри транзакции блокируем строку Event (select_for_update — конкурентные
покупки сериализуются), считаем проданные места и пускаем, только если
capacity безлимитна или хватает мест. Customer переиспользуется по email.
"""

import secrets
import string
from decimal import Decimal

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


class PromoInvalid(Exception):
    """Подарочный/промо-код указан, но не применим (нет/просрочен/исчерпан/мин)."""


class WaiverRequired(Exception):
    """Событие требует подписанный отказ (R8), но подпись не предоставлена."""


def quote_voucher(code, base_cents) -> int:
    """Оценка скидки кода для суммы (read-only, без гашения); 0 — не применим."""
    code = (code or "").strip().upper()
    if not code:
        return 0
    from apps.loyalty.models import Voucher

    voucher = Voucher.objects.filter(code=code).first()
    return voucher.discount_for(base_cents) if voucher else 0


def _apply_voucher(code, base_cents):
    """(discount_cents, code_snapshot) для кода (R4), атомарно гасит. Пусто → (0, "").
    Код задан, но не применим → PromoInvalid. Зеркало stays._apply_voucher."""
    code = (code or "").strip().upper()
    if not code:
        return 0, ""
    from apps.loyalty.models import Voucher
    from apps.promotions.services import VoucherError, redeem_voucher

    voucher = Voucher.objects.filter(code=code).first()
    discount = voucher.discount_for(base_cents) if voucher else 0
    if not voucher or discount <= 0:
        raise PromoInvalid()
    try:
        redeem_voucher(code)
    except VoucherError as exc:
        raise PromoInvalid() from exc
    return discount, code


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
    stay_unit_id=None,
    voucher_code="",
    waiver_signed_name="",
    health_confirmed=False,
    signed_ip="",
):
    """Создать билет, атомарно проверив наличие мест. Бросает ValueError,
    EventNotBookable, SoldOut, PromoInvalid. tier_label (A6) — выбранный ценовой
    тир: цена билета берётся из него (иначе event.price_cents). extras (#7) — доп-услуги.
    stay_unit_id (R5) — выбранный тип номера: создаётся привязанная StayBooking на
    даты ретрита (анти-овербукинг stays), цена входит в total_cents (одна оплата);
    номер недоступен → stays.StayUnavailable (вся бронь откатывается).
    voucher_code (R4) — подарочный/промо-код (Voucher): скидка на сумму билета,
    атомарно гасится; задан, но не применим → PromoInvalid. deposit_percent события
    (R4) → снимок онлайн-депозита (Ticket.deposit_cents)."""
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
    # R11: анти-овердрафт на уровне тира (под той же блокировкой строки Event —
    # конкурентные покупки этого тира сериализуются). capacity тира 0 = без лимита.
    tier_cap = (matched_tier or {}).get("capacity") or 0
    if tier_cap:
        tier_sold = (
            event.tickets.filter(
                status__in=Ticket.ACTIVE_STATUSES, tier_label=matched_tier["label"]
            ).aggregate(n=models.Sum("quantity"))["n"]
            or 0
        )
        tier_available = tier_cap - tier_sold
        if quantity > tier_available:
            raise SoldOut(available=max(tier_available, 0))
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
    # R5: привязать проживание (выбранный тип номера) — внутри той же транзакции.
    if stay_unit_id:
        _attach_accommodation(event, ticket, customer, stay_unit_id, quantity)
    # R4: применить подарочный/промо-код к итогу билета (после проживания/Extras).
    fields = []
    if voucher_code:
        discount, code_snap = _apply_voucher(voucher_code, ticket.total_cents)
        ticket.discount_cents = discount
        ticket.voucher_code = code_snap
        fields += ["discount_cents", "voucher_code"]
    # R4: депозит (онлайн-предоплата %) — снимок от суммы к оплате (после скидки).
    pct = event.deposit_percent
    if 0 < pct < 100 and ticket.payable_cents > 0:
        ticket.deposit_cents = ticket.payable_cents * pct // 100
        fields.append("deposit_cents")
    if fields:
        fields.append("updated_at")
        ticket.save(update_fields=fields)
    # R8: подписанный отказ от ответственности — если событие требует.
    if event.waiver_required:
        _attach_waiver(event, ticket, waiver_signed_name, health_confirmed, signed_ip)
    # письмо «Anmeldung erhalten» — Notification в этой же транзакции (A6c)
    from .notifications import enqueue_ticket_email

    enqueue_ticket_email(ticket, "created")
    # auto_confirm (ручная запись/оплата) → переводим FSM-ом, чтобы сработал
    # finance-хук (выручка пишется на pending→confirmed, идемпотентно).
    if auto_confirm:
        from .state_machine import TicketSM

        TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
    return ticket


def _attach_waiver(event, ticket, signed_name, health_confirmed, signed_ip):
    """R8: создать подписанный TicketWaiver; без подписи → WaiverRequired (откат)."""
    from django.utils import timezone

    from .models import TicketWaiver

    signed_name = (signed_name or "").strip()
    if not signed_name:
        raise WaiverRequired()
    TicketWaiver.objects.create(
        ticket=ticket,
        waiver_text_snapshot=event.effective_waiver_text,
        health_confirmed=bool(health_confirmed),
        signed_name=signed_name[:200],
        signed_at=timezone.now(),
        signed_ip=signed_ip or None,
    )


def _retreat_dates(event):
    """(arrival, departure) дат ретрита для проживания, либо None при невалидных."""
    if not event.offers_accommodation or not event.ends_at:
        return None
    arrival, departure = event.starts_at.date(), event.ends_at.date()
    return (arrival, departure) if departure > arrival else None


def _attach_accommodation(event, ticket, customer, stay_unit_id, quantity):
    """Создать привязанную StayBooking на даты ретрита (анти-овербукинг stays).

    Оплата — вместе с билетом (payment_state=none); цена номера → ticket.
    Недоступно → StayUnavailable (вся транзакция book_ticket откатывается).
    Невалидный выбор (не из набора / нет дат) — тихо игнорируем (без номера).
    """
    dates = _retreat_dates(event)
    if not dates or not event.accommodation_units.filter(id=stay_unit_id, is_active=True).exists():
        return
    from apps.stays import availability, pricing
    from apps.stays.models import StayBooking, StayUnit
    from apps.stays.services import StayUnavailable, _unique_stay_code

    arrival, departure = dates
    unit = StayUnit.objects.select_for_update().get(id=stay_unit_id, is_active=True)
    if not availability.range_available(unit, arrival, departure, needed=1):
        raise StayUnavailable()
    room_cents = pricing.quote_total_cents(unit, arrival, departure)
    guests = min(max(1, quantity), unit.max_guests) or 1
    booking = StayBooking.objects.create(
        unit=unit,
        customer=customer,
        reference_code=_unique_stay_code(),
        arrival=arrival,
        departure=departure,
        guests=guests,
        adults=guests,
        children=0,
        rooms=1,
        price_cents=unit.price_cents,
        total_cents=room_cents,
        status=StayBooking.STATUS_PENDING,
        payment_state=StayBooking.PAYMENT_NONE,  # оплата через билет ретрита
        note=f"Retreat: {event.title} ({ticket.reference_code})",
        source_channel="retreat",
    )
    ticket.stay_booking = booking
    ticket.accommodation_cents = room_cents
    ticket.save(update_fields=["stay_booking", "accommodation_cents", "updated_at"])


def accommodation_quote(event, stay_unit_id) -> int:
    """Цена проживания выбранного типа на даты ретрита (центы, read-only); 0 — нет."""
    dates = _retreat_dates(event)
    if not (stay_unit_id and dates):
        return 0
    unit = event.accommodation_units.filter(id=stay_unit_id, is_active=True).first()
    if not unit:
        return 0
    from apps.stays import pricing

    return pricing.quote_total_cents(unit, *dates)


def accommodation_options(event) -> list:
    """Типы номеров на даты ретрита для витрины: [{unit, price_cents, price_eur,
    nights, available}] (порядок — по цене). Пусто, если проживание не предлагается."""
    dates = _retreat_dates(event)
    if not dates:
        return []
    from apps.stays import availability, pricing

    arrival, departure = dates
    nights = (departure - arrival).days
    out = []
    for unit in event.accommodation_units.filter(is_active=True).order_by("price_cents"):
        price = pricing.quote_total_cents(unit, arrival, departure)
        out.append(
            {
                "unit": unit,
                "price_cents": price,
                "price_eur": Decimal(price) / 100,
                "nights": nights,
                "available": availability.range_available(unit, arrival, departure, needed=1),
            }
        )
    return out


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
