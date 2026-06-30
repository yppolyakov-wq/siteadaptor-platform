"""Письма по заявкам/сметам Handwerker (G6 / F3) — через apps.notifications.

Владельцу: новая Anfrage, принятие/отклонение сметы. Клиенту: готовое Angebot со
ссылкой на публичную страницу принятия. Рендер в схеме арендатора, БД-дедуп
`job:{id}:{event}:{role}`. Хелперы — из apps.promotions.notifications.
"""

from django.db import connection

from apps.notifications.services import notify
from apps.promotions.notifications import _owner_email, _render, _tenant


def enqueue_job_email(job, event, *, angebot_url="", status_url=""):
    """event: new/accepted/declined → владельцу; quoted/done → клиенту (со ссылкой).

    A9: `done` уведомляет клиента, что работа выполнена (Repair-Status), со ссылкой
    на публичную страницу статуса (`status_url`)."""
    schema = connection.schema_name
    customer = job.customer
    ctx = {
        "job": job,
        "customer": customer,
        "angebot_url": angebot_url,
        "status_url": status_url,
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
