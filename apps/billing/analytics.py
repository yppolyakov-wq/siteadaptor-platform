"""R5: платформенная BI-аналитика (MRR / churn / LTV) — SHARED, public-схема.

Считаем из SHARED-данных: подписки на `Tenant.subscription_status` (единый тариф
``BILLING_PLAN_PRICE_EUR``) + журнал usage-fee ``billing.UsageFeeRecord``. Снимок
на «сейчас» (без историй-снапшотов — churn/LTV помечены как приблизительные v1).
Читаем, не пишем. Живёт на публичном домене (суперадмин), т.к. только там виден
кросс-тенантный срез.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

_STATUSES = ("trial", "active", "trial_expired", "past_due", "suspended")


def platform_metrics() -> dict:
    """Срез ключевых метрик платформы. Все денежные — в евро (int/float)."""
    from apps.core.dashboard import _sparkline_points
    from apps.tenants.models import Tenant

    from .models import UsageFeeRecord

    price = int(getattr(settings, "BILLING_PLAN_PRICE_EUR", 39))

    counts = dict.fromkeys(_STATUSES, 0)
    for row in Tenant.objects.values("subscription_status").annotate(n=Count("id")):
        st = row["subscription_status"]
        counts[st] = counts.get(st, 0) + row["n"]
    active = counts["active"]
    total = sum(counts.values())

    # MRR = активные подписки × цена тарифа. ARPA = MRR/активные (= цена при одном
    # тарифе, но устойчиво к будущим тарифам).
    mrr = active * price
    arpa = round(mrr / active, 2) if active else 0

    # Churn (приблизительно, v1): доля ушедших (suspended) за 30 дней от базы
    # (активные + ушедшие). Без снапшотов истории — честно помечаем как оценку.
    now = timezone.now()
    since = now - timedelta(days=30)
    churned_30 = Tenant.objects.filter(
        subscription_status="suspended", subscription_ends_at__gte=since
    ).count()
    base = active + churned_30
    churn_rate = (churned_30 / base) if base else 0.0
    # LTV = ARPA / churn (стандартно). Нет оттока / нет данных → None (∞).
    ltv = round(arpa / churn_rate) if churn_rate else None

    # Usage-fee за текущий период (YYYY-MM): сумма комиссий и оборота.
    period = now.strftime("%Y-%m")
    fees = UsageFeeRecord.objects.filter(period=period).aggregate(
        fee=Sum("fee_cents"), gmv=Sum("gmv_cents")
    )
    fee_eur = round((fees["fee"] or 0) / 100, 2)
    gmv_eur = round((fees["gmv"] or 0) / 100, 2)

    # Регистрации за 30 дней (посуточно) → спарклайн роста.
    per_day = [0] * 30
    for created in Tenant.objects.filter(created_at__gte=since).values_list(
        "created_at", flat=True
    ):
        idx = (timezone.localtime(created).date() - since.date()).days
        if 0 <= idx < 30:
            per_day[idx] += 1

    return {
        "price": price,
        "mrr": mrr,
        "arpa": arpa,
        "counts": counts,
        "active": active,
        "total": total,
        "active_pct": round(100 * active / total) if total else 0,
        "churn_pct": round(churn_rate * 100, 1),
        "churned_30": churned_30,
        "ltv": ltv,
        "fee_eur": fee_eur,
        "gmv_eur": gmv_eur,
        "period": period,
        "signups_30": sum(per_day),
        "sparkline": _sparkline_points(per_day),
    }
