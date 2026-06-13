"""Создание записи с анти-двойным-бронированием (Track D / D3a).

Аналог anti-oversell, но по интервалам: внутри транзакции блокируем строку
ресурса (select_for_update — все брони одного ресурса сериализуются), считаем
активные пересечения [start, end) и пускаем только если их меньше capacity.
Customer переиспользуется по email (как в promotions/orders).
"""

import secrets
import string

from django.db import transaction
from django.db.models import Q

from apps.promotions.models import Customer

from .models import Booking, ClosedDate, Resource

_ALPHABET = string.ascii_uppercase + string.digits


class SlotTaken(Exception):
    """Интервал на ресурсе уже занят (по capacity)."""


class ResourceClosed(Exception):
    """На эту дату ресурс/бизнес закрыт (ClosedDate)."""


def _unique_booking_code() -> str:
    for _ in range(10):
        code = "T-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Booking.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique booking reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


def overlapping(resource, start, end):
    """Активные записи ресурса, пересекающие интервал [start, end)."""
    return Booking.objects.filter(
        resource=resource,
        status__in=Booking.ACTIVE_STATUSES,
        start__lt=end,
        end__gt=start,
    )


@transaction.atomic
def book(
    resource,
    *,
    start,
    end,
    name,
    email="",
    phone="",
    party_size=1,
    note="",
    source_channel="",
    auto_confirm=False,
    service=None,
    price_cents=0,
):
    """Создать запись, атомарно проверив пересечения. Бросает SlotTaken /
    ResourceClosed / ValueError (кривой интервал). service/price_cents — G10."""
    if end <= start:
        raise ValueError("end must be after start")

    resource_id = getattr(resource, "id", resource)
    # Блокировка строки ресурса сериализует конкурентные брони этого ресурса.
    resource = Resource.objects.select_for_update().get(id=resource_id, is_active=True)

    # Точечные исключения: выходной ресурса или всего бизнеса (resource=None).
    closed = ClosedDate.objects.filter(date=start.date()).filter(
        Q(resource=resource) | Q(resource__isnull=True)
    )
    if closed.exists():
        raise ResourceClosed()

    if overlapping(resource, start, end).count() >= resource.capacity:
        raise SlotTaken()

    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    booking = Booking.objects.create(
        resource=resource,
        service=service,
        price_cents=int(price_cents or 0),
        customer=customer,
        reference_code=_unique_booking_code(),
        start=start,
        end=end,
        party_size=party_size,
        status=Booking.STATUS_CONFIRMED if auto_confirm else Booking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо «заявка принята» — Notification в этой же транзакции (D3c)
    from .notifications import enqueue_booking_email

    enqueue_booking_email(booking, "created")
    return booking


@transaction.atomic
def move(booking, *, start, end):
    """Перенос записи на новый интервал с той же anti-double-book проверкой."""
    if end <= start:
        raise ValueError("end must be after start")
    resource = Resource.objects.select_for_update().get(id=booking.resource_id)
    overlaps = overlapping(resource, start, end).exclude(pk=booking.pk)
    if overlaps.count() >= resource.capacity:
        raise SlotTaken()
    booking.start = start
    booking.end = end
    booking.save(update_fields=["start", "end", "updated_at"])
    return booking
