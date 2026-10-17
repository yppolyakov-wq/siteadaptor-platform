"""Мягкие дневные лимиты (A-3: ИИ бесплатно в пилоте с мягким лимитом).

Сумма по `AIUsage` за сегодня, без блокировок: параллельные вызовы могут перерасходовать
на один-два запроса — деньги дополнительно держит бюджет у провайдера. Бизнесу — число
успешных вызовов и евро; платформе — общий бюджет в евро. Платформенные вызовы
(`tenant_schema=""`, ai_smoke) упираются только в бюджет платформы."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .errors import AIQuotaExceeded


def today_totals(tenant_schema: str | None = None) -> dict:
    from .models import AIUsage

    qs = AIUsage.objects.filter(day=timezone.localdate())
    if tenant_schema is not None:
        qs = qs.filter(tenant_schema=tenant_schema)
    agg = qs.aggregate(calls=Count("pk", filter=Q(ok=True)), cost=Sum("cost_cents"))
    return {"calls": agg["calls"] or 0, "cost_cents": agg["cost"] or Decimal(0)}


def check(tenant_schema: str) -> None:
    platform = today_totals()
    if platform["cost_cents"] >= Decimal(str(settings.AI_DAILY_BUDGET_EUR)) * 100:
        raise AIQuotaExceeded("platform daily budget")
    if not tenant_schema:
        return
    mine = today_totals(tenant_schema)
    if mine["calls"] >= settings.AI_TENANT_DAILY_CALLS:
        raise AIQuotaExceeded("tenant daily calls")
    if mine["cost_cents"] >= Decimal(str(settings.AI_TENANT_DAILY_EUR)) * 100:
        raise AIQuotaExceeded("tenant daily budget")
