"""«Verkauft N diese Woche» — честный social-proof (LS-4 v2, одобрен 2026-07-19).

Принцип честности (как у бейджа времени ответа): бейдж рендерится ТОЛЬКО при
n >= SOLD_BADGE_MIN реальных продаж за 7 дней в committed-статусах (отменённые
исключены). Меньше/ошибка → None → бейджа нет. Одна агрегация на детальную.
"""

from datetime import timedelta

from django.utils import timezone

SOLD_BADGE_MIN = 5
_WINDOW_DAYS = 7


def _since():
    return timezone.now() - timedelta(days=_WINDOW_DAYS)


def sold_last_week(kind, obj):
    """Число продаж сущности за 7 дней или None (мало/нет данных/ошибка).

    product → Σ qty позиций не-отменённых заказов · service → брони
    confirmed/fulfilled · stay → брони confirmed/fulfilled · event — билеты
    confirmed/attended. Возвращает int ТОЛЬКО при n >= SOLD_BADGE_MIN."""
    try:
        n = _count(kind, obj)
    except Exception:  # fail-safe: витрина не падает из-за бейджа
        return None
    if n is None or n < SOLD_BADGE_MIN:
        return None
    return n


def _count(kind, obj):
    if kind == "product":
        from django.db.models import Sum

        from apps.orders.models import Order, OrderItem

        return (
            OrderItem.objects.filter(
                product=obj,
                order__created_at__gte=_since(),
            )
            .exclude(order__status=Order.STATUS_CANCELLED)
            .aggregate(n=Sum("qty"))["n"]
            or 0
        )
    if kind == "service":
        from apps.booking.models import Booking

        return Booking.objects.filter(
            service=obj,
            created_at__gte=_since(),
            status__in=(Booking.STATUS_CONFIRMED, Booking.STATUS_FULFILLED),
        ).count()
    if kind == "stay":
        from apps.stays.models import StayBooking

        return StayBooking.objects.filter(
            unit=obj,
            created_at__gte=_since(),
            status__in=(StayBooking.STATUS_CONFIRMED, StayBooking.STATUS_FULFILLED),
        ).count()
    if kind == "event":
        from apps.events.models import Ticket

        return Ticket.objects.filter(
            event=obj,
            created_at__gte=_since(),
            status__in=(Ticket.STATUS_CONFIRMED, Ticket.STATUS_ATTENDED),
        ).count()
    return None
