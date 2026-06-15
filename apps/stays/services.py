"""Создание брони по датам с анти-овербукингом (Track E / E1).

Зеркало apps.booking.services / anti-oversell, но по ночам: внутри транзакции
блокируем строку StayUnit (select_for_update — все брони юнита сериализуются),
пер-ночно считаем занятость (availability.range_available) и пускаем, только если
на КАЖДУЮ ночь есть свободный из quantity юнитов. Customer переиспользуется по
email (как promotions/orders/booking).
"""

import secrets
import string

from django.db import transaction

from apps.promotions.models import Customer

from . import availability, pricing
from .models import StayBooking, StayUnit

_ALPHABET = string.ascii_uppercase + string.digits


class StayUnavailable(Exception):
    """На запрошенный диапазон нет свободного юнита (занятость/блок)."""


class MinStay(Exception):
    """Диапазон короче минимального числа ночей юнита (min_nights)."""


class MaxGuests(Exception):
    """Гостей больше вместимости юнита (max_guests)."""


def _unique_stay_code() -> str:
    for _ in range(10):
        code = "S-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not StayBooking.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique stay reference code")


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
def book_stay(
    unit,
    *,
    arrival,
    departure,
    name,
    email="",
    phone="",
    guests=1,
    note="",
    source_channel="",
    auto_confirm=False,
):
    """Создать бронь по датам, атомарно проверив занятость по ночам. Бросает
    ValueError (кривой диапазон), MinStay, MaxGuests, StayUnavailable."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    if guests < 1:
        raise ValueError("guests must be >= 1")

    unit_id = getattr(unit, "id", unit)
    # Блокировка строки юнита сериализует конкурентные брони этого юнита.
    unit = StayUnit.objects.select_for_update().get(id=unit_id, is_active=True)

    if (departure - arrival).days < unit.min_nights:
        raise MinStay()
    if guests > unit.max_guests:
        raise MaxGuests()
    if not availability.range_available(unit, arrival, departure):
        raise StayUnavailable()

    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    booking = StayBooking.objects.create(
        unit=unit,
        customer=customer,
        reference_code=_unique_stay_code(),
        arrival=arrival,
        departure=departure,
        guests=guests,
        price_cents=unit.price_cents,
        total_cents=pricing.quote_total_cents(unit, arrival, departure),  # A5a: сезон/выходные
        status=StayBooking.STATUS_CONFIRMED if auto_confirm else StayBooking.STATUS_PENDING,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо «Anfrage erhalten» — Notification в этой же транзакции (E3)
    from .notifications import enqueue_stay_email

    enqueue_stay_email(booking, "created")
    return booking


@transaction.atomic
def move_stay(booking, *, arrival, departure):
    """Перенос брони на новый диапазон с той же anti-overbook-проверкой."""
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    unit = StayUnit.objects.select_for_update().get(id=booking.unit_id)
    if (departure - arrival).days < unit.min_nights:
        raise MinStay()
    if not availability.range_available(unit, arrival, departure, exclude_pk=booking.pk):
        raise StayUnavailable()
    booking.arrival = arrival
    booking.departure = departure
    booking.total_cents = pricing.quote_total_cents(unit, arrival, departure)  # A5a: пересчёт
    booking.save(update_fields=["arrival", "departure", "total_cents", "updated_at"])
    return booking
