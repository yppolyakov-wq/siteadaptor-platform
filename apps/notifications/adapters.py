"""Адаптеры каналов доставки: channel → send(notification).

Email — базовый (тело и заголовки письма лежат в Notification.payload, рендер
произошёл при создании). WhatsApp — S6.5 (опц.). Адаптер бросает исключение при
ошибке — задача переведёт уведомление в failed с last_error.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def _send_email(notification) -> None:
    message = EmailMultiAlternatives(
        notification.subject,
        notification.payload.get("body", ""),
        settings.DEFAULT_FROM_EMAIL,
        [notification.recipient],
        headers=notification.payload.get("headers") or None,
    )
    html = notification.payload.get("html")
    if html:
        message.attach_alternative(html, "text/html")
    message.send()


_SENDERS = {
    "email": _send_email,
}


def send(notification) -> None:
    """Доставить уведомление по его каналу. Бросает при ошибке."""
    _SENDERS[notification.channel](notification)
