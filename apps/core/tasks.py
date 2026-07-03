"""C1: beat-задача утреннего дайджеста владельцу.

Задача бежит раз в час по всем схемам; шлёт только когда локальный час
тенанта (tenant.timezone) == digest.DIGEST_HOUR. Дедуп — unique dedupe_key
`digest:{schema}:{date}` в Notification: повторные прогоны безвредны.
MVP — email на owner_email; Telegram владельцу — отдельный трек (нет
chat_id владельца, см. roadmap §Отложено).
"""

from zoneinfo import ZoneInfo

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.core import digest


def _iter_tenants():
    with schema_context("public"):
        return list(get_tenant_model().objects.exclude(schema_name="public"))


def send_digest_for_tenant(tenant, force_hour=False) -> bool:
    """Собрать и отправить дайджест ТЕКУЩЕЙ схемы. True = письмо создано."""
    if not tenant.owner_digest_enabled or not tenant.owner_email:
        return False
    try:
        local_now = timezone.now().astimezone(ZoneInfo(tenant.timezone or "Europe/Berlin"))
    except Exception:  # noqa: BLE001 — битая таймзона не валит рассылку
        local_now = timezone.localtime()
    if not force_hour and local_now.hour != digest.DIGEST_HOUR:
        return False
    data = digest.collect_digest(tenant)
    if data is None:
        return False  # пустой день — не шумим

    from django.template.loader import render_to_string

    from apps.notifications.services import notify

    ctx = {"tenant": tenant, "d": data}
    subject = render_to_string("emails/owner_digest_subject.txt", ctx).strip()
    body = render_to_string("emails/owner_digest.txt", ctx)
    return (
        notify(
            dedupe_key=f"digest:{tenant.schema_name}:{data['date'].isoformat()}",
            type="owner_digest",
            recipient=tenant.owner_email,
            subject=subject,
            body=body,
        )
        is not None
    )


@shared_task
def send_owner_digests() -> int:
    """Beat (раз в час): дайджест всем тенантам, у кого сейчас утро."""
    sent = 0
    for tenant in _iter_tenants():
        with schema_context(tenant.schema_name):
            try:
                if send_digest_for_tenant(tenant):
                    sent += 1
            except Exception:  # noqa: BLE001 — один тенант не валит обход
                continue
    return sent
