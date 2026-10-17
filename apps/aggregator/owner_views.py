"""В5 V5-3: экран владельца «Besuche aus dem Stadtportal» (`/dashboard/stadtportal/`).

Доступ: `@login_required` + членство — его держит CabinetOwnerAccessMiddleware для
всего `/dashboard/`. Цифры — `owner_stats.summary` (только своя схема)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET


@login_required
@require_GET
def portal_stats(request):
    from apps.core import owner_login

    from . import owner_stats

    days = owner_stats.parse_period(request.GET.get("tage"))
    return render(
        request,
        "aggregator/owner_stats.html",
        {
            "nav": "portal-stats",
            "days": days,
            "periods": owner_stats.PERIODS,
            "stats": owner_stats.summary(request.tenant, days),
            **owner_login.pending_context(request),
        },
    )
