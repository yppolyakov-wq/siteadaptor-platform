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


def _send_telegram(notification) -> None:
    """Доставка в Telegram (TG3): recipient = chat_id, токен — бота арендатора.

    Работает в schema_context арендатора (как и задача доставки), поэтому берёт
    активного TelegramBot текущей схемы. Нет активного бота → ошибка (в failed).
    """
    from apps.telegram import services as tg_services
    from apps.telegram.notify import active_bot

    bot = active_bot()
    if bot is None:
        raise RuntimeError("kein aktiver Telegram-Bot")
    tg_services.send_message(
        bot.token, notification.recipient, notification.payload.get("body", "")
    )


_SENDERS = {
    "email": _send_email,
    "telegram": _send_telegram,
}


def send(notification) -> None:
    """Доставить уведомление по его каналу. Бросает при ошибке."""
    _SENDERS[notification.channel](notification)
