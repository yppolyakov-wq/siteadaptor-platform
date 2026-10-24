"""Статусы подключений (read-only) — общие для «Integrationen» и «Sichtbarkeit» (T-8.31c).

Вынесено из вложенных замыканий ``integrations_home`` без изменения текстов. Каждая
функция возвращает ``(подпись, тон)`` с тоном ``ok|warn|muted``; ``safe`` гарантирует,
что сломанный блок не роняет страницу (паттерн ST-4a).
"""

from __future__ import annotations

from django.utils.translation import gettext as _


def safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — статус одного блока не валит страницу
        return ("", "muted")


def stripe(tenant):
    if getattr(tenant, "payments_enabled", False):
        return (_("Stripe verbunden"), "ok")
    if getattr(tenant, "vorkasse_enabled", False):
        return (_("Vorkasse aktiv — Stripe nicht verbunden"), "warn")
    return (_("Nicht verbunden"), "muted")


def telegram(tenant):
    from django.conf import settings as dj_settings

    from apps.telegram.notify import active_bot, owner_chat_id

    # console-бэкенд = письма НЕ уходят наружу (Stage 0 честно на виду).
    if "console" in (getattr(dj_settings, "EMAIL_BACKEND", "") or "").lower():
        return (_("E-Mail: Test-Modus (Konsole) — Mails gehen nicht raus"), "warn")
    bot = active_bot()
    notify_node = (tenant.site_config or {}).get("notify") or {}
    if isinstance(notify_node, dict) and notify_node.get("owner_bot") == "platform":
        from apps.platform_bot import links as platform_links

        if platform_links.platform_linked(tenant):
            return (_("Über Plattform-Bot verbunden"), "ok")
    if bot is None:
        return (_("Kein Telegram-Bot"), "muted")
    # I18N-7b: gettext НЕ в f-строке (xgettext их не извлекает).
    label = _("Bot aktiv")
    if bot.bot_username:
        label = f"{label} · @{bot.bot_username}"
    if owner_chat_id(tenant):
        linked = _("Inhaber verbunden")
        label = f"{label} · {linked}"
    return (label, "ok")


def domain(tenant):
    doms = list(tenant.custom_domains.all()[:5])
    active = next((d for d in doms if d.is_active), None)
    if active is not None:
        return (active.domain, "ok")
    if any(d.status == d.PENDING for d in doms):
        return (_("Prüfung ausstehend"), "warn")
    return (_("Keine eigene Domain"), "muted")


def publishing():
    from apps.publishing.models import Channel as PubChannel

    n = PubChannel.objects.filter(is_enabled=True).exclude(type=PubChannel.LOG).count()
    if n:
        lbl = _("Verbunden:")
        return (f"{lbl} {n}", "ok")
    return (_("Keine Kanäle verbunden"), "muted")


def ota():
    from apps.stays.models import Channel as OtaChannel

    n = OtaChannel.objects.count()
    if n:
        lbl = _("Verbunden:")
        return (f"{lbl} {n}", "ok")
    return (_("Keine Kanäle verbunden"), "muted")


def own_bot(tenant) -> dict:
    """T-8.29: свой бот — модуль выкл у всех по умолчанию; ``username`` у живого бота."""
    try:
        state = {"active": tenant.is_module_active("telegram"), "username": ""}
        if state["active"]:
            from apps.telegram.models import TelegramBot

            bot = TelegramBot.objects.filter(is_active=True).first()
            state["username"] = getattr(bot, "bot_username", "") if bot else ""
        return state
    except Exception:  # noqa: BLE001 — статус блока не валит страницу
        return {"active": False, "username": ""}


def google_rating(tenant):
    """GK-11: ok = кэш есть; warn = ID задан, но ещё не обновлялось; muted = выкл."""
    if not tenant.google_place_id:
        return (_("Nicht verbunden"), "muted")
    if tenant.google_rating is None:
        return (_("Wartet auf erste Aktualisierung"), "warn")
    return (f"★ {tenant.google_rating} · {tenant.google_rating_count}", "ok")


def cards(tenant) -> list[dict]:
    """KA-12 E8.6: карточки подключений (бывший экран «Integrationen») для секции
    «Verbindungen» на «Kanäle & Benachrichtigungen». Статус каждой — fail-safe."""
    rows = [
        {
            "icon": "💳",
            "label": _("Zahlung & Stripe"),
            "hint": _("Online-Zahlung, Vorkasse, Zahlarten"),
            "url_name": "payment-settings",
            "show": True,
            "status": safe(lambda: stripe(tenant)),
        },
        {
            "icon": "🌐",
            "label": _("Eigene Domain"),
            "hint": _("Custom-Domain verbinden"),
            "url_name": "domains",
            "show": True,
            "status": safe(lambda: domain(tenant)),
        },
        {
            "icon": "📣",
            "label": _("Publishing (Google/Facebook/Instagram)"),
            "hint": _("Kanäle verbinden und Beiträge planen"),
            "url_name": "channels",
            "show": tenant.is_module_active("publishing"),
            "status": safe(publishing),
        },
        {
            "icon": "⭐",
            "label": _("Google Bewertungen"),
            "hint": _("Bewertung und Anzahl von Google auf der Website anzeigen"),
            "url_name": "google-reviews-settings",
            "show": True,
            "status": safe(lambda: google_rating(tenant)),
        },
        {
            "icon": "🏨",
            "label": _("Channel Manager (OTA)"),
            "hint": _("Buchungen aus Portalen importieren"),
            "url_name": "stays:channels",
            "show": tenant.is_module_active("stays"),
            "status": safe(ota),
        },
    ]
    return [c for c in rows if c["show"]]
