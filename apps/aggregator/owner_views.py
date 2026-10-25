"""В5 V5-3: экран владельца «Besuche aus dem Stadtportal» (`/dashboard/stadtportal/`).

Доступ: `@login_required` + членство — его держит CabinetOwnerAccessMiddleware для
всего `/dashboard/`. Цифры — `owner_stats.summary` (только своя схема)."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST


@login_required
@require_GET
def portal_stats(request):
    from apps.core import owner_login
    from apps.core.permissions import has_perm

    # Решение владельца: только владельцу (право «stadtportal.view»). Middleware держит
    # то же правило для HTTP; проверка здесь — защита в глубину.
    if not has_perm(request.user, "stadtportal.view"):
        return HttpResponseForbidden(_("Nur für Inhaber."))

    from apps.core import freshness

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
            "freshness": freshness.banner(request.tenant),
            **owner_login.pending_context(request),
        },
    )


@login_required
@require_POST
def freshness_confirm(request):
    """Г3: «Alles noch aktuell» — подтвердить все товары и услуги для каталога города.

    Подтверждать могут и сотрудники (это не настройка бизнеса); членство держит
    middleware кабинета. `next` — только относительный путь своего кабинета."""
    from django.contrib import messages
    from django.db import connection
    from django.shortcuts import redirect

    from apps.core import freshness

    n = freshness.confirm_all(connection.schema_name)
    messages.success(request, _("%(n)s Positionen bestätigt.") % {"n": n})
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = (request.POST.get("next") or "").strip()
    # Ревью: стандартная проверка (сама режет TAB/CR/LF, «\», «///», схемы) +
    # только свой кабинет — `next` здесь всегда путь экрана кабинета.
    if not (
        nxt.startswith("/dashboard/")
        and url_has_allowed_host_and_scheme(
            nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
    ):
        nxt = "/dashboard/"
    return redirect(nxt)
