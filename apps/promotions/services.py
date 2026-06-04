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

from .models import Customer, Promotion, Reservation, Voucher
from .notifications import enqueue_reservation_email
from .state_machine import ReservationSM

# алфавит без похожих символов (0/O, 1/I) — код диктуется голосом на выдаче
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class OutOfStock(Exception):
    """Недостаточно доступного количества (или акция не active)."""


class ReservationLimitReached(Exception):
    """Превышен Promotion.max_per_customer для этого клиента."""


class VoucherError(Exception):
    """Ваучер нельзя погасить. reason: not_found/inactive/expired/used_up."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


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
def reserve(promotion, *, name, email="", phone="", quantity=1, note="", source_channel=""):
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
    reservation = Reservation.objects.create(
        promotion=promotion,
        customer=customer,
        reference_code=_unique_reference_code(),
        quantity=quantity,
        status=initial_status,
        expires_at=now + timedelta(hours=promotion.reservation_ttl_hours),
        confirmed_at=now if initial_status == "confirmed" else None,
        note=note,
        source_channel=(source_channel or "")[:50],
    )
    # письмо клиенту/владельцу — после коммита транзакции
    enqueue_reservation_email(reservation, "created")
    return reservation


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


# ---------------------------------------------------------------------------
# Ваучеры / промокоды
# ---------------------------------------------------------------------------


def _unique_voucher_code() -> str:
    for _ in range(10):
        code = "V-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Voucher.objects.filter(code=code).exists():
            return code
    raise RuntimeError("could not generate unique voucher code")


def generate_vouchers(*, label, count=1, max_uses=1, expires_at=None):
    """Сгенерировать count ваучеров с уникальными кодами. Вернуть список."""
    count = max(1, min(int(count), 200))  # разумный потолок на пачку
    created = []
    for _ in range(count):
        created.append(
            Voucher.objects.create(
                code=_unique_voucher_code(),
                label=label,
                max_uses=max_uses,
                expires_at=expires_at,
            )
        )
    return created


@transaction.atomic
def redeem_voucher(code):
    """Погасить ваучер (одно использование). Бросает VoucherError с reason."""
    code = (code or "").strip().upper()
    voucher = Voucher.objects.select_for_update().filter(code=code).first()
    if voucher is None:
        raise VoucherError("not_found")
    if not voucher.is_active:
        raise VoucherError("inactive")
    if voucher.expires_at and voucher.expires_at < timezone.now():
        raise VoucherError("expired")
    if voucher.max_uses and voucher.used_count >= voucher.max_uses:
        raise VoucherError("used_up")
    Voucher.objects.filter(pk=voucher.pk).update(used_count=F("used_count") + 1)
    voucher.refresh_from_db(fields=["used_count"])
    return voucher
