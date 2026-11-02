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
    try:
        adapters.send(notification)
    except Exception as exc:  # noqa: BLE001 — ошибку доставки фиксируем в last_error
        # SEC-A1: текст ошибки Telegram/почты может нести токен бота в URL — маскируем.
        from apps.telegram.services import scrub

        notification.last_error = scrub(str(exc))[:500]
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


#: SEC (ревью аудита, SM8): сколько раз пробуем доставить уведомление всего.
MAX_ATTEMPTS = 3
#: Повторяем только сбои последних суток.
RETRY_WINDOW = __import__("datetime").timedelta(hours=24)
#: Ошибки, которые повтором не лечатся (чат заблокировал бота, адрес не существует).
_PERMANENT_MARKERS = ("(403)", "(400)", "blocked", "Invalid email")


def retry_failed(*, now=None, limit=200) -> int:
    """Вернуть в очередь упавшие уведомления текущей схемы (экспоненциальная пауза:
    10 мин, 20 мин). Раньше FAILED было окончательным — сбой Resend или Telegram на
    минуту терял письмо клиенту навсегда. Постоянные ошибки не повторяем."""
    from datetime import timedelta

    from django.db import connection, transaction
    from django.db.models import Q

    from apps.core.fsm import IllegalTransition

    from .models import Notification

    now = now or timezone.now()
    sm = NotificationSM()
    requeued = 0
    # Ревью волны 2: только свежие сбои (сутки) — после деплоя не рассылаем старые
    # напоминания/подтверждения; постоянные ошибки и пауза — в запросе, чтобы они не
    # занимали лимит выборки.
    permanent = Q()
    for marker in _PERMANENT_MARKERS:
        permanent |= Q(last_error__contains=marker)
    rows = (
        Notification.objects.filter(
            status=FAILED,
            attempts__lt=MAX_ATTEMPTS,
            updated_at__gte=now - RETRY_WINDOW,
            updated_at__lte=now - timedelta(minutes=10),
        )
        .exclude(permanent)
        .order_by("updated_at")[:limit]
    )
    for n in rows:
        if n.updated_at > now - timedelta(minutes=10 * (2 ** max(n.attempts - 1, 0))):
            continue
        try:
            sm.apply(n, PENDING)
        except IllegalTransition:
            continue  # параллельный проход уже вернул в очередь
        nid, attempt, schema = str(n.id), n.attempts, connection.schema_name
        transaction.on_commit(
            lambda nid=nid, attempt=attempt, schema=schema: send_notification.delay(
                dedupe_key=f"send:{nid}:retry{attempt}",
                tenant_schema=schema,
                notification_id=nid,
            )
        )
        requeued += 1
    return requeued


@idempotent_task()
def retry_failed_notifications():
    """Beat: повтор упавших уведомлений во всех схемах (каждая — своя попытка: сбой
    одной схемы не останавливает остальные)."""
    import logging

    from django_tenants.utils import get_tenant_model

    log = logging.getLogger(__name__)
    total = 0
    for schema in (
        get_tenant_model()
        .objects.exclude(schema_name="public")
        .values_list("schema_name", flat=True)
    ):
        try:
            with schema_context(schema):
                total += retry_failed()
        except Exception:  # noqa: BLE001
            log.exception("notification retry failed for schema %s", schema)
    return {"requeued": total}
