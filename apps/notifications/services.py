"""Постановка уведомлений: get_or_create по dedupe_key + отправка после коммита.

notify() — единственная точка создания Notification. Повтор того же dedupe_key —
no-op (вернёт None): unique в БД даёт гарантию «одно событие = одно уведомление»
независимо от Redis. Создание строки идёт в текущей транзакции (атомарно с
доменным событием), enqueue отправки — после коммита.
"""

from django.db import connection, transaction

from .models import Notification
from .tasks import send_notification


def notify(
    *,
    dedupe_key: str,
    type: str,
    recipient: str,
    subject: str = "",
    body: str = "",
    html: str = "",
    headers: dict | None = None,
    channel: str = Notification.EMAIL,
) -> Notification | None:
    """Создать уведомление (если ещё нет) и поставить доставку. None = дубль."""
    payload = {"body": body}
    if html:
        payload["html"] = html
    if headers:
        payload["headers"] = headers

    notification, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "type": type,
            "channel": channel,
            "recipient": recipient,
            "subject": subject,
            "payload": payload,
        },
    )
    if not created:
        return None

    schema = connection.schema_name
    nid = str(notification.id)
    transaction.on_commit(
        lambda: send_notification.delay(
            dedupe_key=f"send:{nid}", tenant_schema=schema, notification_id=nid
        )
    )
    return notification
