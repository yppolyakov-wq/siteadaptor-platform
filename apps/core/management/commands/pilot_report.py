"""KA-12 E11.5: отчёт пилота по бизнесам — только чтение, без персональных данных.

План — docs/ka-12-e11-checks-plan-2026-10-23.md, памятка — docs/pilot-protocol-solingen-2026-10-23.md.

    python manage.py pilot_report --city solingen --format csv > pilot-2026-10-30.csv

На каждый бизнес — строка счётчиков и времён «от регистрации до …» в минутах. Ни имён, ни
адресов, ни e-mail/телефонов: только схема, тип, пакет и числа. Пустая ячейка — «ещё не было»
(не ноль). Сбой одной схемы не обрывает отчёт: строка получает колонку `error`.
"""

from __future__ import annotations

import csv
import logging
import statistics
import sys
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

COLUMNS = (
    "schema",
    "business_type",
    "package",
    "registered",
    "email_confirmed",
    "min_to_first_active_promo",
    "promotions_total",
    "promotions_active",
    "min_to_first_reservation",
    "min_to_first_coupon",
    "min_to_first_order",
    "min_to_first_booking",
    "promo_views",
    "reservations",
    "coupons",
    "orders",
    "failed_notifications",
    "owner_days_since_login",
    "support_requests",
    "error",
)
# Колонки-длительности: итоговая строка показывает их медиану.
DURATIONS = tuple(c for c in COLUMNS if c.startswith("min_to_"))


def _minutes(start, end):
    if start is None or end is None:
        return ""
    return max(0, round((end - start).total_seconds() / 60))


def _first(qs, field="created_at"):
    return qs.aggregate(first=Min(field))["first"]


def _support_counts(path: str) -> dict:
    """Ручной журнал обращений: CSV с колонками date, schema, topic, minutes."""
    if not path:
        return {}
    counts: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                schema = (row.get("schema") or "").strip()
                if schema:
                    counts[schema] = counts.get(schema, 0) + 1
    except (OSError, UnicodeDecodeError) as exc:
        raise CommandError(f"support-log: {exc}") from exc
    return counts


def _in_city(tenant, city: str) -> bool:
    if not city:
        return True
    return (tenant.city or "").strip().lower() == city.strip().lower()


def tenant_row(tenant, support: dict) -> dict:
    """Строка отчёта одного бизнеса (вызывается внутри schema_context)."""
    from apps.audit.models import AuditEvent
    from apps.core import storefront_profile
    from apps.core.models import Membership
    from apps.notifications.models import Notification
    from apps.promotions.models import Promotion, PromotionChannelView, Reservation

    registered = tenant.created_at
    row = {
        "schema": tenant.schema_name,
        "business_type": tenant.business_type,
        "package": "lite" if storefront_profile.is_aktionen(tenant) else "full",
        "registered": registered.date().isoformat() if registered else "",
        "email_confirmed": "no" if tenant.email_pending else "yes",
        "support_requests": support.get(tenant.schema_name, 0),
    }
    first_active = _first(
        AuditEvent.objects.filter(tenant_schema=tenant.schema_name, action="promotion.activated")
    )
    row["min_to_first_active_promo"] = _minutes(registered, first_active)
    row["promotions_total"] = Promotion.objects.count()
    row["promotions_active"] = Promotion.objects.filter(status="active").count()
    row["min_to_first_reservation"] = _minutes(registered, _first(Reservation.objects.all()))
    row["reservations"] = Reservation.objects.count()
    row["promo_views"] = PromotionChannelView.objects.aggregate(n=Sum("views"))["n"] or 0

    from apps.loyalty.models import Voucher

    coupons = Voucher.objects.filter(promotion__isnull=False)
    row["coupons"] = coupons.count()
    row["min_to_first_coupon"] = _minutes(registered, _first(coupons))

    from apps.orders.models import Order

    row["orders"] = Order.objects.count()
    row["min_to_first_order"] = _minutes(registered, _first(Order.objects.all()))

    booking_starts = []
    from apps.booking.models import Booking
    from apps.stays.models import StayBooking

    for model in (Booking, StayBooking):
        value = _first(model.objects.all())
        if value is not None:
            booking_starts.append(value)
    row["min_to_first_booking"] = _minutes(registered, min(booking_starts, default=None))

    row["failed_notifications"] = Notification.objects.filter(status="failed").count()

    owner = (
        Membership.objects.filter(role=Membership.ROLE_OWNER, user__last_login__isnull=False)
        .select_related("user")
        .order_by("-user__last_login")
        .first()
    )
    last_login = getattr(getattr(owner, "user", None), "last_login", None)
    row["owner_days_since_login"] = (timezone.now() - last_login).days if last_login else ""
    return row


class Command(BaseCommand):
    help = "Отчёт пилота по бизнесам: времена до первых действий и счётчики (без ПДн)."

    def add_arguments(self, parser):
        parser.add_argument("--city", default="", help="только бизнесы этого города")
        parser.add_argument("--since", default="", help="зарегистрированы не раньше YYYY-MM-DD")
        parser.add_argument("--include-demo", action="store_true", help="включить демо/внутренние")
        parser.add_argument("--format", choices=("csv", "table"), default="csv")
        parser.add_argument("--support-log", default="", help="CSV журнала обращений")

    def handle(self, *args, **opts):
        from django_tenants.utils import schema_context

        from apps.tenants.models import Tenant

        since = None
        if opts["since"]:
            try:
                since = date.fromisoformat(opts["since"])
            except ValueError as exc:
                raise CommandError("--since: ожидается YYYY-MM-DD") from exc
        support = _support_counts(opts["support_log"])

        tenants = Tenant.objects.exclude(schema_name="public").order_by("created_at")
        if not opts["include_demo"]:
            tenants = tenants.filter(is_demo=False, is_internal=False)
        if since:
            tenants = tenants.filter(
                created_at__gte=timezone.make_aware(datetime.combine(since, datetime.min.time()))
            )
        rows = []
        for tenant in tenants:
            if not _in_city(tenant, opts["city"]):
                continue
            try:
                with schema_context(tenant.schema_name):
                    rows.append(tenant_row(tenant, support))
            except Exception as exc:  # noqa: BLE001 — одна схема не обрывает отчёт
                logger.exception("pilot_report: schema %s failed", tenant.schema_name)
                rows.append(
                    {
                        "schema": tenant.schema_name,
                        "business_type": tenant.business_type,
                        "error": type(exc).__name__,
                    }
                )
        rows.append(self._summary(rows))
        self._write(rows, opts["format"])

    def _summary(self, rows):
        summary = {"schema": f"MEDIAN ({sum(1 for r in rows if not r.get('error'))})"}
        for col in DURATIONS:
            values = [r[col] for r in rows if isinstance(r.get(col), int)]
            summary[col] = round(statistics.median(values)) if values else ""
        return summary

    def _write(self, rows, fmt):
        out = self.stdout if hasattr(self, "stdout") else sys.stdout
        if fmt == "csv":
            writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in COLUMNS})
            return
        for row in rows:
            out.write(" | ".join(f"{c}={row.get(c, '')}" for c in COLUMNS if row.get(c, "") != ""))
            out.write("\n")
