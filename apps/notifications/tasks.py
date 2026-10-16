"""Celery: доставка уведомлений (per-tenant, идемпотентно).

Гарантия от повторной отправки — проверка status == pending перед доставкой
(unique dedupe_key уже отсёк дубль строки; Redis-lock задачи — оптимизация).
Чистая логика — deliver() в текущей схеме, её и тестируем.
"""

from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.jobs import idempotent_task

from . import adapters
from .state_machine import FAILED, PENDING, SENT, NotificationSM


def deliver(notification_id) -> str:
    """Доставить pending-уведомление (в текущей схеме). Повтор — skip."""
    from .models import Notification

    notification = Notification.objects.filter(id=notification_id).first()
    if notification is None:
        return "missing"
    if notification.status != PENDING:
        return "skip"

    sm = NotificationSM()
    notification.attempts += 1
    from apps.core import demo_mode

    if demo_mode.current_is_demo():
        # В1: из демо-бизнеса ничего не уходит (ни покупателю, ни владельцу, ни в
        # Telegram). Строка остаётся следом в журнале.
        notification.last_error = "demo tenant: not sent"
        notification.save(update_fields=["attempts", "last_error", "updated_at"])
        sm.apply(notification, FAILED)
        return "demo"
    try:
        adapters.send(notification)
    except Exception as exc:  # noqa: BLE001 — ошибку доставки фиксируем в last_error
        notification.last_error = str(exc)[:500]
        notification.save(update_fields=["attempts", "last_error", "updated_at"])
        sm.apply(notification, FAILED)
        return "failed"

    notification.sent_at = timezone.now()
    notification.last_error = ""
    notification.save(update_fields=["attempts", "sent_at", "last_error", "updated_at"])
    sm.apply(notification, SENT)
    return "sent"


@idempotent_task()
def send_notification(*, tenant_schema, notification_id):
    with schema_context(tenant_schema):
        return {"result": deliver(notification_id)}
