"""Nutzungsgebühr — помесячная плата за пользование системой (вариант B, P2.5-fee).

Считаем «vermittelter Umsatz» (оборот через платформу = выручка по заказам и
броням из apps.finance.RevenueEntry, без ручных записей) за период и выставляем
строкой в Stripe-счёт подписки бизнеса (services.create_usage_invoice_item).
Процент — по типу бизнеса (connect.application_fee_percent, сейчас 0 → ничего не
начисляем). Идемпотентность — UsageFeeRecord по (tenant, период).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from django_tenants.utils import schema_context


def period_bounds(period: str) -> tuple[date, date]:
    """«YYYY-MM» → (первый день, последний день месяца) включительно."""
    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return start, nxt - timedelta(days=1)


def previous_period(today: date | None = None) -> str:
    """Завершённый прошлый месяц относительно today (по умолчанию — сегодня)."""
    today = today or timezone.localdate()
    last_prev = today.replace(day=1) - timedelta(days=1)
    return last_prev.strftime("%Y-%m")


def tenant_gmv_cents(tenant, period: str) -> int:
    """Оборот тенанта за период (центы): выручка заказов+броней, кросс-схемно."""
    from apps.finance.models import RevenueEntry

    start, end = period_bounds(period)
    with schema_context(tenant.schema_name):
        total = RevenueEntry.objects.filter(
            source__in=[RevenueEntry.SOURCE_ORDER, RevenueEntry.SOURCE_RESERVATION],
            date__gte=start,
            date__lte=end,
        ).aggregate(s=Sum("amount"))["s"] or Decimal(0)
    return int(round(total * 100))


def fee_cents_for(tenant, period: str) -> tuple[int, int, Decimal]:
    """(gmv_cents, fee_cents, percent) для тенанта за период."""
    from .connect import application_fee_percent

    pct = application_fee_percent(tenant.business_type)
    gmv = tenant_gmv_cents(tenant, period)
    fee = int(gmv * pct / 100) if pct > 0 else 0
    return gmv, fee, pct


def bill_tenant(tenant, period: str) -> str:
    """Выставить Nutzungsgebühr тенанту за период (идемпотентно).

    Возвращает статус: already / zero (нет процента или оборота) / no_customer /
    billed. Запись UsageFeeRecord создаём только при реальном начислении (>0).
    """
    from . import services
    from .models import UsageFeeRecord

    if UsageFeeRecord.objects.filter(tenant=tenant, period=period).exists():
        return "already"
    gmv, fee, pct = fee_cents_for(tenant, period)
    if fee <= 0:
        return "zero"
    if not tenant.stripe_customer_id:
        return "no_customer"
    item_id = services.create_usage_invoice_item(
        tenant,
        amount_cents=fee,
        description=f"Nutzungsgebühr {pct}% vom Umsatz ({period})",
    )
    UsageFeeRecord.objects.create(
        tenant=tenant,
        period=period,
        gmv_cents=gmv,
        fee_percent=pct,
        fee_cents=fee,
        stripe_invoice_item_id=item_id or "",
    )
    return "billed"
