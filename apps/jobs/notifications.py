"""Письма по заявкам/сметам Handwerker (G6 / F3) — через apps.notifications.

Владельцу: новая Anfrage, принятие/отклонение сметы. Клиенту: готовое Angebot со
ссылкой на публичную страницу принятия. Рендер в схеме арендатора, БД-дедуп
`job:{id}:{event}:{role}`. Хелперы — из apps.promotions.notifications.
"""

from django.db import connection

from apps.notifications.services import notify
from apps.promotions.notifications import _owner_email, _render, _tenant


def enqueue_job_email(job, event, *, angebot_url=""):
    """event: new/accepted/declined → владельцу; quoted → клиенту (со ссылкой)."""
    schema = connection.schema_name
    customer = job.customer
    ctx = {"job": job, "customer": customer, "angebot_url": angebot_url}

    if event == "quoted":
        if customer.email and not customer.unsubscribed:
            subject, body, html = _render("job_quoted", ctx)
            notify(
                dedupe_key=f"job:{job.id}:quoted:customer",
                type="job_quoted",
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
