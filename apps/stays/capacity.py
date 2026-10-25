"""KA-12 Zimmer Z-5b (DF-Z3, решение О-8 — запрет): ёмкость категории не опускается
ниже проданного.

План — docs/ka-12-w4-z5-front-desk-heute-plan-2026-10-25.md Р-5. Считаем только
ПРОДАННОЕ (активные брони × rooms) на ночи от сегодня: блок — не продажа, лишний
блок безвреден (его покажет предупреждение «Überbuchung»). Проверки — под тем же
локом категории, что ``services.book_stay``; порядок «категория → комната», как
у ``assign_room``/``create_block``.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q

from apps.core import status_registry


class CapacityBelowSold(Exception):
    """На ночь ``day`` продано ``sold`` номеров — меньше ёмкость сделать нельзя."""

    def __init__(self, day, sold):
        super().__init__(f"{day}: {sold}")
        self.day = day
        self.sold = sold


class RoomAssigned(Exception):
    """Комната назначена текущей/будущей брони — сначала переназначить гостя."""

    def __init__(self, booking):
        super().__init__(booking.reference_code)
        self.booking = booking


def sold_by_night(unit, from_day) -> dict:
    """Продано номеров по ночам ``≥ from_day`` (активные брони × rooms)."""
    from .models import StayBooking

    rows = StayBooking.objects.filter(
        unit=unit,
        status__in=status_registry.active_statuses_for("stay"),
        departure__gt=from_day,
    ).values_list("arrival", "departure", "rooms")
    out = {}
    for arrival, departure, rooms in rows:
        night = max(arrival, from_day)
        while night < departure:
            out[night] = out.get(night, 0) + (rooms or 1)
            night += timedelta(days=1)
    return out


def _check(unit, new_qty, today) -> None:
    sold = sold_by_night(unit, today)
    over = sorted(day for day, n in sold.items() if n > new_qty)
    if over:
        raise CapacityBelowSold(over[0], sold[over[0]])


def _lock_unit(unit):
    from .models import StayUnit

    return StayUnit.objects.select_for_update().get(pk=unit.pk)


def set_quantity(unit, new_qty, today) -> None:
    """Сменить quantity категории без комнат; ниже проданного → CapacityBelowSold.

    У категории с физическими комнатами ёмкость = число активных комнат
    (``sync_room_quantity``) — её меняет только ``delete_room``/добавление комнаты."""
    with transaction.atomic():
        locked = _lock_unit(unit)
        if locked.rooms.exists() or locked.quantity == new_qty:
            return
        if new_qty < locked.quantity:
            _check(locked, new_qty, today)
        locked.quantity = new_qty
        locked.save(update_fields=["quantity", "updated_at"])
        unit.quantity = new_qty


def delete_room(room, today) -> None:
    """Удалить физическую комнату. Назначена активной брони, ещё не выехавшей, →
    RoomAssigned; ёмкость после удаления ниже проданного → CapacityBelowSold."""
    from .models import Room, StayBooking
    from .services import sync_room_quantity

    with transaction.atomic():
        unit = _lock_unit(room.unit)
        # Лок комнаты ДО проверки назначения: assign_room лочит только комнату.
        locked = Room.objects.select_for_update().filter(pk=room.pk).first()
        if locked is None:
            return
        booking = (
            StayBooking.objects.filter(
                Q(room=locked) | Q(extra_rooms=locked),
                status__in=status_registry.active_statuses_for("stay"),
                departure__gt=today,
            )
            .order_by("arrival")
            .distinct()
            .first()
        )
        if booking is not None:
            raise RoomAssigned(booking)
        if locked.is_active:
            remaining = unit.rooms.filter(is_active=True).exclude(pk=locked.pk).count()
            _check(unit, remaining, today)
        locked.blocks.all().delete()
        locked.delete()
        sync_room_quantity(unit)
