"""Доставка уведомлений клиенту в Telegram + привязка по deep-link (TG3).

Поток: на странице подтверждения клиенту показываем кнопку «Updates per Telegram»
(deep_link) → t.me/<bot>?start=<link_token> → /start <token> в боте находит
TelegramLink по токену и проставляет chat_id (link_from_start). Дальше события
заказа/брони уходят в Telegram через apps.notifications (channel=telegram).
"""

import secrets

from .models import TelegramBot, TelegramLink


def active_bot() -> TelegramBot | None:
    return TelegramBot.objects.filter(is_active=True).exclude(token="").first()


def _link_for(customer) -> TelegramLink:
    link, _ = TelegramLink.objects.get_or_create(
        customer=customer, defaults={"link_token": secrets.token_urlsafe(16)}
    )
    if not link.link_token:  # на всякий случай (старые/битые записи)
        link.link_token = secrets.token_urlsafe(16)
        link.save(update_fields=["link_token", "updated_at"])
    return link


def deep_link(customer) -> str:
    """t.me-ссылка для привязки клиента к боту. '' если бота нет."""
    bot = active_bot()
    if bot is None or not bot.bot_username:
        return ""
    token = _link_for(customer).link_token
    return f"https://t.me/{bot.bot_username}?start={token}"


def link_from_start(payload: str, chat_id) -> bool:
    """Привязать chat_id по токену из /start <payload>. True при успехе."""
    link = TelegramLink.objects.filter(link_token=payload).first()
    if link is None:
        return False
    link.chat_id = str(chat_id)
    link.save(update_fields=["chat_id", "updated_at"])
    return True


def send_to_customer(customer, *, type: str, dedupe_key: str, text: str) -> None:
    """Поставить Telegram-уведомление клиенту, если он привязан и бот активен.

    Тихо ничего не делает, если нет привязки/бота — Telegram дополняет email,
    не заменяет его (email уходит своим путём).
    """
    if active_bot() is None:
        return
    link = TelegramLink.objects.filter(customer=customer, chat_id__gt="").first()
    if link is None:
        return
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    notify(
        dedupe_key=dedupe_key,
        type=type,
        recipient=link.chat_id,
        body=text,
        channel=Notification.TELEGRAM,
    )


# --- UD4c: привязка Telegram ВЛАДЕЛЬЦА к боту бизнеса + пуш владельцу -----------
# Хранение — Tenant.site_config["notify"] (без миграции): owner_link_token (для
# deep-link) + owner_chat_id (проставляется на /start owner-<token>).


def _notify_node(tenant) -> dict:
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    node = cfg.get("notify")
    return node if isinstance(node, dict) else {}


def _save_notify_node(tenant, node: dict) -> None:
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    cfg["notify"] = node
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])


def owner_chat_id(tenant) -> str:
    return _notify_node(tenant).get("owner_chat_id", "") or ""


def owner_deep_link(tenant) -> str:
    """t.me-ссылка для привязки Telegram ВЛАДЕЛЬЦА к боту бизнеса. '' если бота нет.

    Токен генерится один раз и хранится в site_config (в отличие от клиента —
    у владельца нет отдельной модели, привязка живёт на тенанте)."""
    bot = active_bot()
    if bot is None or not bot.bot_username:
        return ""
    node = _notify_node(tenant)
    token = node.get("owner_link_token")
    if not token:
        token = secrets.token_urlsafe(16)
        node = {**node, "owner_link_token": token}
        _save_notify_node(tenant, node)
    return f"https://t.me/{bot.bot_username}?start=owner-{token}"


def link_owner_from_start(payload: str, chat_id, tenant) -> bool:
    """Привязать chat_id владельца по /start owner-<token>. True при успехе."""
    if not payload.startswith("owner-"):
        return False
    token = payload[len("owner-") :]
    node = _notify_node(tenant)
    if not token or node.get("owner_link_token") != token:
        return False
    _save_notify_node(tenant, {**node, "owner_chat_id": str(chat_id)})
    return True


def send_to_owner(tenant, *, type: str, dedupe_key: str, text: str) -> None:
    """Telegram-уведомление ВЛАДЕЛЬЦУ, если привязан owner_chat_id и бот активен.

    Тихо no-op без привязки/бота — Telegram дополняет owner-email, не заменяет."""
    if active_bot() is None:
        return
    chat = owner_chat_id(tenant)
    if not chat:
        return
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    notify(
        dedupe_key=dedupe_key, type=type, recipient=chat, body=text, channel=Notification.TELEGRAM
    )
