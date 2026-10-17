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


WEEK_DAYS = 7
TOP_PROMOTIONS = 3


def _promo_week(today) -> dict | None:
    """Г4-2: акции за прошлую неделю `[today−7, today)` — только агрегаты.

    Просмотры — по дневной таблице (Г4-1); «отложено» — резервы, созданные в окне
    (тот же фильтр статусов, что счётчик списка акций); «выдано» — по `fulfilled_at`;
    купоны — выданные в окне и погашенные в окне (`updated_at` ставит погашение).
    Имён, контактов и кодов клиентов здесь нет. Пустая неделя → None.
    """
    from datetime import datetime, time

    from django.db.models import Sum

    from apps.loyalty.models import Voucher
    from apps.promotions.models import Promotion, PromotionDailyView, Reservation

    first = today - timedelta(days=WEEK_DAYS)
    start = timezone.make_aware(datetime.combine(first, time.min))
    end = timezone.make_aware(datetime.combine(today, time.min))
    views = PromotionDailyView.objects.filter(day__gte=first, day__lt=today)
    week = {
        "views": views.aggregate(n=Sum("views"))["n"] or 0,
        "held": Reservation.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            status__in=["pending", "confirmed", "fulfilled"],
        ).count(),
        "handed": Reservation.objects.filter(fulfilled_at__gte=start, fulfilled_at__lt=end).count(),
        "coupons": Voucher.objects.filter(
            promotion__isnull=False, created_at__gte=start, created_at__lt=end
        ).count(),
        "coupons_redeemed": Voucher.objects.filter(
            promotion__isnull=False, used_count__gt=0, updated_at__gte=start, updated_at__lt=end
        ).count(),
    }
    if not any(week.values()):
        return None
    ranked = list(
        views.values("promotion")
        .annotate(n=Sum("views"))
        .order_by("-n", "promotion")[:TOP_PROMOTIONS]
    )
    titles = {
        p.pk: p.title_text
        for p in Promotion.objects.filter(pk__in=[r["promotion"] for r in ranked]).only(
            "pk", "title"
        )
    }
    week["top"] = [
        {"title": titles.get(r["promotion"], ""), "views": r["n"]}
        for r in ranked
        if titles.get(r["promotion"])
    ]
    return week


def collect_digest(tenant, *, weekly: bool = False) -> dict | None:
    """Метрики для письма или None, если сегодня нечего рассказать.

    `weekly` — понедельник: добавляется недельный блок акций (Г4-2)."""
    today = timezone.localdate()
    data = {"date": today}

    if weekly and modules.is_module_active(tenant, "promotions"):
        week = _safe(lambda: _promo_week(today), None)
        if week:
            data["promo_week"] = week

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
        from apps.core import status_registry

        # SM-3: «активные» через реестр — запись в кастом-статусе видна в дайджесте.
        data["bookings_today"] = _safe(
            lambda: Booking.objects.filter(
                start__date=today,
                status__in=status_registry.active_statuses_for("booking", tenant),
            ).count()
        )
        data["bookings_pending"] = _safe(
            lambda: Booking.objects.filter(
                status=Booking.STATUS_PENDING, start__gte=timezone.now()
            ).count()
        )

    if modules.is_module_active(tenant, "stays"):
        from apps.core import status_registry
        from apps.stays.models import StayBooking

        data["arrivals_today"] = _safe(
            lambda: StayBooking.objects.filter(
                arrival=today,
                status__in=status_registry.active_statuses_for("stay", tenant),
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

    # Г3 (В-5): одна строка «скоро уйдут из каталога города».
    from apps.core import freshness

    fresh = _safe(lambda: freshness.banner(tenant), None)
    if fresh and fresh["soon"]:
        data["freshness_soon"] = fresh["soon"]

    interesting = [v for k, v in data.items() if k != "date"]
    if not any(interesting):
        return None
    return data
