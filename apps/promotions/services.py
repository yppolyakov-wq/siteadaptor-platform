"""Сервисы резервирования (anti-oversell).

Списание остатка — одним атомарным conditional UPDATE с F() (см.
docs/references/patterns/anti-oversell.md). Смена статусов — через
ReservationSM. Возврат остатка при отмене/истечении — в on_transition.
"""

import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import Customer, Promotion, Reservation
from .state_machine import ReservationSM

# алфавит без похожих символов (0/O, 1/I) — код диктуется голосом на выдаче
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class OutOfStock(Exception):
    """Недостаточно доступного количества (или акция не active)."""


class ReservationLimitReached(Exception):
    """Превышен Promotion.max_per_customer для этого клиента."""


def _unique_reference_code() -> str:
    for _ in range(10):
        code = "R-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Reservation.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique reservation reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            # дозаполняем пустые контакты, имя не перетираем
            updates = []
            if not customer.phone and phone:
                customer.phone = phone
                updates.append("phone")
            if updates:
                customer.save(update_fields=[*updates, "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


@transaction.atomic
def reserve(promotion, *, name, email="", phone="", quantity=1, note=""):
    """Создать бронь, атомарно списав остаток акции.

    Бросает OutOfStock, если остатка не хватило/акция не active, и
    ReservationLimitReached при превышении max_per_customer.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1")

    promo_id = getattr(promotion, "id", promotion)
    promotion = Promotion.objects.get(id=promo_id)

    customer = _get_or_create_customer(name=name, email=email, phone=phone)

    # лимит на клиента по этой акции (по сумме активных броней)
    if promotion.max_per_customer:
        active_qty = (
            Reservation.objects.filter(
                promotion=promotion,
                customer=customer,
                status__in=["pending", "confirmed"],
            ).aggregate(n=Sum("quantity"))["n"]
            or 0
        )
        if active_qty + quantity > promotion.max_per_customer:
            raise ReservationLimitReached()

    # атомарное условное списание остатка
    if promotion.available_quantity is not None:
        rows = Promotion.objects.filter(
            id=promotion.id,
            status="active",
            available_quantity__gte=quantity,
        ).update(available_quantity=F("available_quantity") - quantity)
        if rows == 0:
            raise OutOfStock()
    elif promotion.status != "active":
        # без лимита остатка, но акция должна быть активной
        raise OutOfStock()

    initial_status = "confirmed" if promotion.auto_confirm else "pending"
    now = timezone.now()
    return Reservation.objects.create(
        promotion=promotion,
        customer=customer,
        reference_code=_unique_reference_code(),
        quantity=quantity,
        status=initial_status,
        expires_at=now + timedelta(hours=promotion.reservation_ttl_hours),
        confirmed_at=now if initial_status == "confirmed" else None,
        note=note,
    )


def confirm(reservation, *, actor=None):
    """pending → confirmed (ручное подтверждение владельцем)."""
    with transaction.atomic():
        if reservation.status == "pending":
            reservation.confirmed_at = timezone.now()
            reservation.save(update_fields=["confirmed_at", "updated_at"])
        return ReservationSM().apply(reservation, "confirmed", actor=actor)


def fulfill(reservation, *, actor=None):
    """confirmed → fulfilled (бронь выдана клиенту)."""
    with transaction.atomic():
        if reservation.status != "fulfilled":
            reservation.fulfilled_at = timezone.now()
            reservation.save(update_fields=["fulfilled_at", "updated_at"])
        return ReservationSM().apply(reservation, "fulfilled", actor=actor)


def cancel(reservation, *, actor=None):
    """Отмена брони с возвратом остатка. Идемпотентно (защита от double-refund)."""
    with transaction.atomic():
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status not in ("pending", "confirmed"):
            return res  # уже терминальная — no-op
        res.cancelled_at = timezone.now()
        res.save(update_fields=["cancelled_at", "updated_at"])
        return ReservationSM().apply(res, "cancelled", actor=actor)


def expire(reservation, *, actor=None):
    """Просрочка брони (по TTL) с возвратом остатка. Идемпотентно."""
    with transaction.atomic():
        res = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if res.status not in ("pending", "confirmed"):
            return res
        return ReservationSM().apply(res, "expired", actor=actor)
