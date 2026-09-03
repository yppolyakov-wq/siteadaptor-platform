"""Постановка уведомлений: get_or_create по dedupe_key + отправка после коммита.

notify() — единственная точка создания Notification. Повтор того же dedupe_key —
no-op (вернёт None): unique в БД даёт гарантию «одно событие = одно уведомление»
независимо от Redis. Создание строки идёт в текущей транзакции (атомарно с
доменным событием), enqueue отправки — после коммита.
"""

from django.db import connection, transaction

from .models import Notification
from .tasks import send_notification


def tenant_locale() -> str:
    """Язык БИЗНЕСА = `Tenant.default_locale` текущей схемы (фолбэк «de»).

    I18N-13: письма, чьё тело собирается в Python (а не шаблоном через
    `_render`), обязаны рендериться в локали ПОЛУЧАТЕЛЯ, а не в языке кабинета
    владельца — иначе владелец с русским интерфейсом отправит клиенту русское
    письмо. Использовать как `with translation.override(email_locale()):`.
    """
    try:
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(schema_name=connection.schema_name).first()
        loc = getattr(tenant, "default_locale", "") if tenant else ""
        return loc if isinstance(loc, str) and loc else "de"
    except Exception:  # noqa: BLE001
        return "de"


# Письмо собирается в языке бизнеса — исторический псевдоним для читаемости
# на почтовых колл-сайтах.
email_locale = tenant_locale


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
    attachments: list | None = None,
) -> Notification | None:
    """Создать уведомление (если ещё нет) и поставить доставку. None = дубль.

    SH-23b: `attachments` — список (имя, содержимое-bytes, mime) для писем с
    документом (счёт юрлицу приходит PDF-файлом). Хранится в payload base64,
    потому что доставка идёт отдельной задачей и должна пережить перезапуск.
    """
    payload = {"body": body}
    if html:
        payload["html"] = html
    if headers:
        payload["headers"] = headers
    if attachments:
        import base64

        payload["attachments"] = [
            {
                "name": name,
                "mime": mime,
                "b64": base64.b64encode(content).decode("ascii"),
            }
            for name, content, mime in attachments
        ]

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
