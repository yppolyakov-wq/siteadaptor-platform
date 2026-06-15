"""KPI-дашборд платформенной админки (unfold DASHBOARD_CALLBACK).

Все данные — SHARED-модели на public-схеме (где и живёт админка), поэтому
кросс-схемные обходы не нужны. Карточки и списки рендерит
``templates/admin/index.html``. Любая ошибка БД (например, до миграций) не должна
ронять админку — отдаём пустые значения.
"""

from django.urls import reverse


def _safe(fn, default=0):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — админка не должна падать из-за дашборда
        return default


def dashboard_callback(request, context):
    from apps.billing.state_machine import ACTIVE, PAST_DUE, SUSPENDED, TRIAL, TRIAL_EXPIRED
    from apps.support.models import SupportThread
    from apps.tenants.models import Tenant

    # Реальные бизнесы — без служебной строки public.
    tenants = Tenant.objects.exclude(schema_name="public")
    tenant_url = reverse("admin:tenants_tenant_changelist")
    support_url = reverse("admin:support_supportthread_changelist")
    open_statuses = [SupportThread.STATUS_OPEN, SupportThread.STATUS_PENDING]

    context["kpi_cards"] = [
        {
            "title": "Betriebe",
            "value": _safe(tenants.count),
            "hint": "Registrierte Geschäfte",
            "icon": "storefront",
            "link": tenant_url,
        },
        {
            "title": "Aktive Abos",
            "value": _safe(lambda: tenants.filter(subscription_status=ACTIVE).count()),
            "hint": "Zahlende Kunden",
            "icon": "verified",
            "link": f"{tenant_url}?subscription_status={ACTIVE}",
        },
        {
            "title": "Im Test",
            "value": _safe(lambda: tenants.filter(subscription_status=TRIAL).count()),
            "hint": "Trial-Phase",
            "icon": "schedule",
            "link": f"{tenant_url}?subscription_status={TRIAL}",
        },
        {
            "title": "Offene Tickets",
            "value": _safe(lambda: SupportThread.objects.filter(status__in=open_statuses).count()),
            "hint": "Support wartet",
            "icon": "support_agent",
            "link": support_url,
        },
    ]

    # Карточка-предупреждение появляется только при наличии проблемных абонементов.
    overdue = _safe(
        lambda: tenants.filter(subscription_status__in=[PAST_DUE, TRIAL_EXPIRED, SUSPENDED]).count()
    )
    context["kpi_alert"] = (
        {
            "title": "Zahlung überfällig",
            "value": overdue,
            "hint": "past_due / trial_expired / suspended",
            "link": tenant_url,
        }
        if overdue
        else None
    )

    context["recent_tenants"] = _safe(
        lambda: [
            {
                "name": t.name,
                "meta": f"{t.get_business_type_display()} · {t.subscription_status}",
                "link": reverse("admin:tenants_tenant_change", args=[t.pk]),
            }
            for t in tenants.order_by("-created_at")[:8]
        ],
        default=[],
    )

    context["open_tickets"] = _safe(
        lambda: [
            {
                "subject": th.subject,
                "meta": f"{th.tenant.name} · {th.status}",
                "link": reverse("admin:support_supportthread_change", args=[th.pk]),
            }
            for th in SupportThread.objects.filter(status__in=open_statuses).select_related(
                "tenant"
            )[:8]
        ],
        default=[],
    )

    return context
