"""Личные каналы связи с клиентом (фидбэк владельца 2026-08-25).

«На странице каналов нужно добавить соцсети, телеграм и т.д. — всё, где можем
коммуницировать персонально с клиентом или потенциальными клиентами.»

Каналы ПУБЛИКАЦИИ (`apps.publishing.Channel`) отвечают на «куда уходит акция»;
здесь — вторая половина: где клиент пишет НАМ и где мы отвечаем ему лично.
Слой только читает состояние и говорит, куда идти настраивать: собственных
таблиц и настроек не заводит.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — карточка канала не должна ронять страницу
        return default


def personal_channels(tenant) -> list[dict]:
    """[{key, icon, label, hint, ready, url}] — состояние личных каналов."""
    if tenant is None:
        return []
    rows: list[dict] = []

    wa = (getattr(tenant, "whatsapp_number", "") or "").strip()
    rows.append(
        {
            "key": "whatsapp",
            "icon": "🟢",
            "label": _("WhatsApp"),
            "hint": wa or _("Nummer in den Einstellungen hinterlegen"),
            "ready": bool(wa),
            "url": _safe(lambda: reverse("settings"), "/dashboard/settings/"),
        }
    )

    telegram_ready = _safe(
        lambda: bool((tenant.site_config or {}).get("owner_chat_id")) or _has_bot(tenant), False
    )
    rows.append(
        {
            "key": "telegram",
            "icon": "✈️",
            "label": _("Telegram"),
            "hint": _("Bot für Kundenchats und Benachrichtigungen")
            if telegram_ready
            else _("Bot verbinden"),
            "ready": bool(telegram_ready),
            "url": _safe(lambda: reverse("telegram-settings"), "/dashboard/telegram/"),
        }
    )

    email = (
        getattr(tenant, "contact_email", "") or getattr(tenant, "owner_email", "") or ""
    ).strip()
    rows.append(
        {
            "key": "email",
            "icon": "✉️",
            "label": _("E-Mail"),
            "hint": email or _("Absenderadresse in den Benachrichtigungen setzen"),
            "ready": bool(email),
            "url": _safe(lambda: reverse("notifications-settings"), "/dashboard/settings/"),
        }
    )

    inbox_on = _safe(lambda: tenant.is_module_active("inbox"), False)
    rows.append(
        {
            "key": "inbox",
            "icon": "💬",
            "label": _("Chat auf der Website"),
            "hint": _("Nachrichten landen im Posteingang")
            if inbox_on
            else _("Modul „Nachrichten“ aktivieren"),
            "ready": bool(inbox_on),
            "url": _safe(lambda: reverse("inbox:list"), "/dashboard/inbox/"),
        }
    )

    for key, label, url in _safe(lambda: tenant.social_links(), []) or []:
        rows.append(
            {
                "key": key,
                "icon": "🔗",
                "label": label,
                "hint": url,
                "ready": True,
                "url": _safe(lambda: reverse("settings"), "/dashboard/settings/"),
            }
        )
    if not (_safe(lambda: tenant.social_links(), []) or []):
        rows.append(
            {
                "key": "social",
                "icon": "🔗",
                "label": _("Social-Profile"),
                "hint": _("Instagram, Facebook, TikTok … im Profil hinterlegen"),
                "ready": False,
                "url": _safe(lambda: reverse("settings"), "/dashboard/settings/"),
            }
        )
    return rows


def _has_bot(tenant) -> bool:
    from apps.integrations.telegram.models import TelegramLink  # локально: SHARED-модель

    return TelegramLink.objects.exists()
