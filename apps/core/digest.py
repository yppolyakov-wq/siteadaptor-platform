"""C1: утренний дайджест владельцу — сбор метрик ТЕКУЩЕЙ схемы тенанта.

Собираем только по активным модулям (is_module_active), каждый блок fail-safe
(ошибка одного домена не валит дайджест). Пустой день (нет ни выручки, ни
сегодняшних событий, ни «требует действия») → None, письмо не шлём.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core import modules

DIGEST_HOUR = 7  # локальный час тенанта (tenant.timezone), когда слать


def _safe(fn, default=0):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — блок одного модуля не валит дайджест
        return default


def collect_digest(tenant) -> dict | None:
    """Метрики для письма или None, если сегодня нечего рассказать."""
    today = timezone.localdate()
    data = {"date": today}

    if modules.is_module_active(tenant, "finance"):

        def _rev():
            from django.db.models import Sum

            from apps.finance.models import RevenueEntry

            s = RevenueEntry.objects.filter(date=today - timedelta(days=1)).aggregate(
                s=Sum("amount")
            )["s"]
            return s or Decimal("0")

        data["revenue_yesterday"] = _safe(_rev, Decimal("0"))

    if modules.is_module_active(tenant, "booking"):
        from apps.booking.models import Booking

        data["bookings_today"] = _safe(
            lambda: Booking.objects.filter(
                start__date=today, status__in=Booking.ACTIVE_STATUSES
            ).count()
        )
        data["bookings_pending"] = _safe(
            lambda: Booking.objects.filter(
                status=Booking.STATUS_PENDING, start__gte=timezone.now()
            ).count()
        )

    if modules.is_module_active(tenant, "stays"):
        from apps.stays.models import StayBooking

        data["arrivals_today"] = _safe(
            lambda: StayBooking.objects.filter(
                arrival=today, status__in=StayBooking.ACTIVE_STATUSES
            ).count()
        )
        data["stays_pending"] = _safe(
            lambda: StayBooking.objects.filter(
                status=StayBooking.STATUS_PENDING, departure__gte=today
            ).count()
        )

    if modules.is_module_active(tenant, "events"):
        from apps.events.models import Event, Ticket

        data["events_today"] = _safe(
            lambda: Event.objects.filter(
                starts_at__date=today, status=Event.STATUS_PUBLISHED
            ).count()
        )
        data["tickets_pending"] = _safe(
            lambda: Ticket.objects.filter(status=Ticket.STATUS_PENDING).count()
        )

    if modules.is_module_active(tenant, "orders"):
        from apps.orders.models import Order

        data["orders_new"] = _safe(lambda: Order.objects.filter(status=Order.STATUS_NEW).count())

    if modules.is_module_active(tenant, "jobs"):
        from apps.jobs.models import Job

        data["jobs_new"] = _safe(lambda: Job.objects.filter(status=Job.STATUS_NEW).count())

    if modules.is_module_active(tenant, "inbox"):
        from apps.inbox.models import Conversation

        data["inbox_unread"] = _safe(
            lambda: Conversation.objects.filter(
                unread_for_staff=True, status=Conversation.STATUS_OPEN
            ).count()
        )

    interesting = [v for k, v in data.items() if k != "date"]
    if not any(interesting):
        return None
    return data
