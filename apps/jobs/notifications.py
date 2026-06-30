"""Письма по заявкам/сметам Handwerker (G6 / F3) — через apps.notifications.

Владельцу: новая Anfrage, принятие/отклонение сметы. Клиенту: готовое Angebot со
ссылкой на публичную страницу принятия. Рендер в схеме арендатора, БД-дедуп
`job:{id}:{event}:{role}`. Хелперы — из apps.promotions.notifications.
"""

from django.db import connection

from apps.notifications.services import notify
from apps.promotions.notifications import _owner_email, _render, _tenant


def _review_url(schema) -> str:
    """A7: ссылка на страницу бизнеса в портале агрегатора для отзыва (best-effort).

    Портал/тенант — SHARED (public). Берём активный портал, где бизнес присутствует:
    по business_type (вертикаль) или по городу (city-портал). Нет портала/слага → ''
    (письмо уйдёт без ссылки, как у stays/events)."""
    try:
        from django.db.models import Q
        from django_tenants.utils import schema_context

        from apps.aggregator.models import AggregatorPortal
        from apps.tenants.models import Tenant

        with schema_context("public"):
            t = (
                Tenant.objects.filter(schema_name=schema)
                .only("slug", "business_type", "city")
                .first()
            )
            if t is None or not t.slug:
                return ""
            portal = (
                AggregatorPortal.objects.filter(is_active=True)
                .filter(Q(business_type=t.business_type) | Q(city__iexact=t.city))
                .order_by("business_type")
                .first()
            )
            if portal is None:
                return ""
            host, slug = portal.host, t.slug
        return f"https://{host}/unternehmen/{slug}/"
    except Exception:  # noqa: BLE001 — письмо не должно падать из-за ссылки
        return ""


def enqueue_job_email(job, event, *, angebot_url="", status_url=""):
    """event: new/accepted/declined → владельцу; quoted/done → клиенту (со ссылкой).

    A9: `done` уведомляет клиента, что работа выполнена (Repair-Status), со ссылкой
    на публичную страницу статуса (`status_url`). A7: в `done` добавляем запрос отзыва
    (`review_url`, страница бизнеса в портале — best-effort, как post-stay/post-event)."""
    schema = connection.schema_name
    customer = job.customer
    ctx = {
        "job": job,
        "customer": customer,
        "angebot_url": angebot_url,
        "status_url": status_url,
        "review_url": _review_url(schema) if event == "done" else "",
    }

    if event in ("quoted", "done", "service_reminder"):  # → клиенту
        if customer.email and not customer.unsubscribed:
            subject, body, html = _render(f"job_{event}", ctx)
            # A9: напоминание о TÜV/Service может приходить повторно (на каждую дату),
            # поэтому дедуп включает саму дату — иначе вторая дата не отправится.
            suffix = (
                f":{job.service_due_date.isoformat()}"
                if event == "service_reminder" and job.service_due_date
                else ""
            )
            notify(
                dedupe_key=f"job:{job.id}:{event}{suffix}:customer",
                type=f"job_{event}",
                recipient=customer.email,
                subject=subject,
                body=body,
                html=html,
            )
        return

    # new / accepted / declined → владельцу
    owner = _owner_email(_tenant(schema))
    if owner:
        subject, body, html = _render(f"job_{event}", ctx)
        notify(
            dedupe_key=f"job:{job.id}:{event}:owner",
            type=f"job_{event}",
            recipient=owner,
            subject=subject,
            body=body,
            html=html,
        )
