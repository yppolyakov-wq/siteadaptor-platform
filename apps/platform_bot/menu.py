"""T-8.10h H-7b/c/g: меню общего бота — «/hilfe», «☰ Menü», «/kabinett», «/eigener_bot».

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.

- Кнопки меню — `pm:<код>`; бизнес берётся из ТЕКУЩЕЙ связи в момент нажатия (в
  callback_data нет pk — подменять нечего), права перепроверяет `signup.send_login_link`.
- Вход в кабинет — только письмом (решение владельца), но сразу на нужный экран:
  экран выбирается из закрытого списка `TARGETS`, произвольный путь не принимается.
- Токен своего бота в чате НЕ принимаем (секрет остался бы в облачной истории Telegram):
  `/eigener_bot` — только инструкция и вход в кабинет «Telegram-Bot».
"""

from __future__ import annotations

import re

from django.urls import reverse
from django.utils.translation import gettext as _

from . import links

PREFIX = "pm:"
HELP_RE = re.compile(r"^/(?:hilfe|help|menu|menue)(?:@\w+)?\s*$", re.IGNORECASE)
CABINET_RE = re.compile(r"^/(?:kabinett|cabinet|login)(?:@\w+)?\s*$", re.IGNORECASE)
OWN_BOT_RE = re.compile(r"^/(?:eigener_bot|own_bot)(?:@\w+)?\s*$", re.IGNORECASE)
CALLBACK_RE = re.compile(r"^pm:(h|k|b|d|a|l:[aetn])$")
TENANT_URLCONF = "config.urls_tenant"

# Экраны кабинета для входа письмом: код → url_name (подписи — `_label`).
TARGETS = {
    "a": "promotions:promotion-list",
    "e": "settings",
    "t": "telegram-settings",
    "n": "notifications-settings",
}


def _label(code: str) -> str:
    labels = {
        "a": _("Aktionen"),
        "e": _("Einstellungen"),
        "t": _("Telegram-Bot"),
        "n": _("Benachrichtigungen"),
    }
    return labels[code]


def target_path(code: str) -> str:
    return reverse(TARGETS[code], urlconf=TENANT_URLCONF)


def _send(bot, chat, text, markup=None):
    from .handler import send

    return send(bot, chat, text, markup)


def keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📋 " + _("Meine Aktionen"), "callback_data": PREFIX + "a"},
                {"text": "🏪 " + _("Profil"), "callback_data": "pp:" + "v"},
            ],
            [
                {"text": "🔑 " + _("Kabinett"), "callback_data": PREFIX + "k"},
                {"text": "🤖 " + _("Eigener Bot"), "callback_data": PREFIX + "b"},
            ],
            [
                {"text": "🔒 " + _("Datenschutz"), "callback_data": PREFIX + "d"},
                {"text": "❓ " + _("Hilfe"), "callback_data": PREFIX + "h"},
            ],
        ]
    }


def help_text() -> str:
    from apps.promotions.telegram_promo import photo_tip

    return "\n".join(
        [
            _("So arbeiten Sie mit diesem Bot:"),
            "✍️ "
            + _(
                "Aktion als Text senden, z. B. „Brötchen 2,50 € statt 3,90 €, heute bis 18 Uhr“ — "
                "ich zeige eine Vorschau, ✅ veröffentlicht."
            ),
            photo_tip(),
            "📋 /aktionen — " + _("Ihre Aktionen: pausieren, starten, beenden, wo sichtbar"),
            "🔁 /wiederholen — " + _("eine frühere Aktion erneut starten"),
            "🏪 /profil — " + _("Telefon, WhatsApp, Stadtkatalog"),
            "🏪 /geschaeft — "
            + _("Geschäft wechseln")
            + " · /neu — "
            + _("Neues Geschäft anlegen"),
            "🔑 /kabinett — " + _("Anmeldelink für das Kabinett per E-Mail"),
            "🤖 /eigener_bot — " + _("eigenen Telegram-Bot für Ihr Geschäft einrichten"),
            "🔒 /datenschutz · /meine_daten · /berichtigen · /einschraenken · /widerspruch · "
            "/daten_loeschen",
        ]
    )


def show_help(bot, chat) -> str:
    _send(bot, chat, help_text(), keyboard())
    return "help"


def cabinet(bot, uid, chat) -> str:
    """Экраны кабинета: «Login per E-Mail» (письмо со ссылкой сразу на экран) + прямые ссылки
    для уже вошедших в браузере (без входа они ведут на форму входа)."""
    from apps.core import owner_login

    current = links.active_links(uid).first()
    if current is None:
        from .handler import _private_onboarding

        return _private_onboarding(bot, chat)
    base = owner_login.tenant_url(current.tenant)
    rows = []
    for code in TARGETS:
        row = [{"text": "✉️ " + _label(code), "callback_data": f"{PREFIX}l:{code}"}]
        if base.startswith(("https://", "http://")):  # иначе Telegram отверг бы всё
            row.append({"text": "↗", "url": f"{base}{target_path(code)}"})
        rows.append(row)
    _send(
        bot,
        chat,
        _(
            "Kabinett von %(name)s. ✉️ schickt einen Anmeldelink per E-Mail direkt auf die Seite; "
            "↗ öffnet sie, wenn Sie im Browser schon angemeldet sind."
        )
        % {"name": current.tenant.name},
        {"inline_keyboard": rows},
    )
    return "cabinet"


def own_bot(bot, uid, chat) -> str:
    current = links.active_links(uid).first()
    text = "\n".join(
        [
            _("Eigener Bot für Ihr Geschäft — so geht’s:"),
            "1. " + _("In Telegram @BotFather öffnen und /newbot senden."),
            "2. " + _("Namen wählen — BotFather schickt einen Token."),
            "3. "
            + _(
                "Den Token NUR im Kabinett unter „Telegram-Bot“ eintragen — "
                "nicht hier im Chat senden."
            ),
            _(
                "Danach beantwortet Ihr eigener Bot Kundinnen und Kunden; Aktionen gehen weiter hier."
            ),
        ]
    )
    markup = None
    if current is not None:
        markup = {
            "inline_keyboard": [
                [{"text": "✉️ " + _("Kabinett „Telegram-Bot“"), "callback_data": PREFIX + "l:t"}]
            ]
        }
    _send(bot, chat, text, markup)
    return "own_bot"


def my_promotions(bot, uid, chat, language_code: str = "") -> str:
    """📋 — то же, что «/aktionen» текущего бизнеса (тот же путь прав и лимитов)."""
    from .handler import _private_onboarding, _promo_message

    current = links.active_links(uid).first()
    if current is None:
        return _private_onboarding(bot, chat)
    message = {"chat_id": chat, "from_id": uid, "text": "/aktionen", "language_code": language_code}
    return _promo_message(bot, message, current, None)


def on_message(bot, message: dict, text: str) -> str:
    """'' — не команда меню."""
    uid, chat = message["from_id"], message["chat_id"]
    if HELP_RE.match(text):
        return show_help(bot, chat)
    if CABINET_RE.match(text):
        return cabinet(bot, uid, chat)
    if OWN_BOT_RE.match(text):
        return own_bot(bot, uid, chat)
    return ""


def on_callback(bot, callback: dict) -> str:
    from apps.telegram import services

    uid, chat = callback.get("from_id"), callback.get("chat_id")
    services.answer_callback_query(bot.token, callback.get("id") or "")
    if not uid or chat != uid:
        return "skip"
    match = CALLBACK_RE.match(str(callback.get("data") or ""))
    if not match:
        return "skip"
    code = match.group(1)
    if code == "h":
        return show_help(bot, chat)
    if code == "k":
        return cabinet(bot, uid, chat)
    if code == "b":
        return own_bot(bot, uid, chat)
    if code == "d":
        from . import privacy

        return privacy.info(bot, uid, chat)
    if code == "a":
        return my_promotions(bot, uid, chat, callback.get("language_code") or "")
    current = links.active_links(uid).first()
    if current is None:
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    from . import signup

    return signup.send_login_link(
        bot, uid, chat, str(current.tenant.pk), next_path=target_path(code[2:])
    )
