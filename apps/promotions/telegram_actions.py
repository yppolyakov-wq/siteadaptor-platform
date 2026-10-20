"""T-8.10h H-7e: «/aktionen» — свои акции в чате: статус, ⏸/▶/⏹, 🔁, 📍, ✏️, 📄.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.

- Смена статуса — только через FSM (`PromotionSM`), запуск — через `limits.activate`
  (лимит бесплатной ступени Р-5). Недопустимый переход (повторное нажатие, акция уже
  закончилась) — словами, без исключения наружу.
- ⏹ необратим — второй шаг «Ja, beenden» (`ta:E`).
- Права перепроверяются на КАЖДОМ нажатии вызывающим кодом (`handle_callback` /
  `handle_platform_callback` → `owner_ok`); в общем боте кнопки заворачивает
  `routing.wrap`, поэтому pk акции наружу не уходит.
- Цену и текст живой акции в чате не правим (решение владельца): ✏️ — веб-форма, 🔁 — копия.
"""

from __future__ import annotations

import re

from django.urls import reverse
from django.utils.translation import gettext as _

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
COMMAND_RE = re.compile(r"(?i)^/(?:aktionen|angebote|offers)(?:@\w+)?\s*$")
CALLBACK_RE = re.compile(rf"^ta:(s|p|a|e|E|w):({UUID})$")
LIST_LIMIT = 10
ACTION_LIMIT = 60  # нажатий на чат в час
LIST_STATUSES = ("draft", "scheduled", "active", "paused", "ended")
TENANT_URLCONF = "config.urls_tenant"


def _status_word(status: str) -> str:
    words = {
        "draft": _("Entwurf"),
        "scheduled": _("geplant"),
        "active": _("aktiv"),
        "paused": _("pausiert"),
        "ended": _("beendet"),
        "archived": _("archiviert"),
    }
    return words.get(status, status)


STATUS_ICON = {
    "draft": "📝",
    "scheduled": "🗓",
    "active": "🟢",
    "paused": "⏸",
    "ended": "⏹",
    "archived": "🗄",
}


def _tp():
    from . import telegram_promo

    return telegram_promo


def list_menu(bot, chat) -> str:
    from .models import Promotion

    tp = _tp()
    promos = list(
        Promotion.objects.filter(status__in=LIST_STATUSES).order_by("-created_at")[:LIST_LIMIT]
    )
    if not promos:
        tp._send(bot, chat, _("Noch keine Aktionen. Schicken Sie einfach die erste als Nachricht."))
        return "actions_empty"
    rows = [
        [
            {
                "text": f"{STATUS_ICON.get(p.status, '•')} {(p.title_text or '—')[:44]}",
                "callback_data": tp._cbdata(f"ta:s:{p.pk}"),
            }
        ]
        for p in promos
    ]
    title = _("Ihre letzten Aktionen — antippen zum Verwalten:")
    business = tp._business_line()
    if business:
        title = f"{title}\n{business}"
    tp._send(bot, chat, title, {"inline_keyboard": rows})
    return "actions_menu"


def _period(promo) -> str:
    from django.utils import formats, timezone

    def fmt(value):
        return formats.date_format(timezone.localtime(value), "SHORT_DATETIME_FORMAT")

    if promo.starts_at and promo.ends_at:
        return f"{fmt(promo.starts_at)} – {fmt(promo.ends_at)}"
    if promo.ends_at:
        return _("bis %(date)s") % {"date": fmt(promo.ends_at)}
    return ""


def _expired(promo) -> bool:
    from django.utils import timezone

    return bool(promo.ends_at and promo.ends_at <= timezone.now())


def _card_markup(promo) -> dict:
    from apps.telegram.services import tenant_base_url

    from .views import REPEATABLE_STATUSES

    tp = _tp()
    row = []
    if promo.status == "active":
        row.append({"text": "⏸ " + _("Pausieren"), "callback_data": tp._cbdata(f"ta:p:{promo.pk}")})
    if promo.status in ("paused", "draft") and not _expired(promo):
        row.append({"text": "▶ " + _("Starten"), "callback_data": tp._cbdata(f"ta:a:{promo.pk}")})
    if promo.status in ("active", "paused"):
        row.append({"text": "⏹ " + _("Beenden"), "callback_data": tp._cbdata(f"ta:e:{promo.pk}")})
    rows = [row] if row else []
    second = [{"text": "📍 " + _("Wo?"), "callback_data": tp._cbdata(f"ta:w:{promo.pk}")}]
    if promo.status in REPEATABLE_STATUSES:
        second.append(
            {"text": "🔁 " + _("Wiederholen"), "callback_data": tp._cbdata(f"tp:rp:{promo.pk}")}
        )
    rows.append(second)
    base = tenant_base_url()
    if base:
        edit = reverse("promotions:promotion-edit", args=[promo.pk], urlconf=TENANT_URLCONF)
        flyer = reverse("promotions:promotion-flyer", args=[promo.pk], urlconf=TENANT_URLCONF)
        rows.append(
            [
                {"text": "✏️ " + _("Bearbeiten"), "url": base + edit},
                {"text": "📄 " + _("Aushang"), "url": base + flyer},
            ]
        )
    return {"inline_keyboard": rows}


def show_card(bot, chat, promo, note: str = "") -> str:
    tp = _tp()
    lines = [note] if note else []
    lines.append(f"{STATUS_ICON.get(promo.status, '•')} {promo.title_text or '—'}")
    lines.append(_("Status: %(status)s") % {"status": _status_word(promo.status)})
    period = _period(promo)
    if period:
        lines.append("🗓 " + period)
    tp._send(bot, chat, "\n".join(lines), _card_markup(promo))
    return "action_card"


def on_callback(bot, tenant, schema: str, chat: str, data: str) -> str:
    from apps.core import ratelimit
    from apps.core.fsm import IllegalTransition

    from . import limits, where
    from .state_machine import PromotionSM

    tp = _tp()
    match = CALLBACK_RE.match(data)
    if not match:
        return "skip"
    action, pk = match.groups()
    if ratelimit.hit("tg-actions", f"{schema}:{chat}", limit=ACTION_LIMIT, window=3600):
        tp._send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    promo = tp.source_promo(pk)
    if promo is None or promo.status == "archived":
        tp._send(bot, chat, _("Diese Aktion gibt es nicht mehr."))
        return "action_missing"
    if action == "s":
        return show_card(bot, chat, promo)
    if action == "w":
        tp._send(
            bot, chat, "\n".join([(promo.title_text or "—")[:80], *where.report(tenant, promo)])
        )
        return "where"
    if action == "e":
        tp._send(
            bot,
            chat,
            _("Aktion „%(title)s“ wirklich beenden? Das lässt sich nicht rückgängig machen.")
            % {"title": (promo.title_text or "—")[:80]},
            {
                "inline_keyboard": [
                    [
                        {
                            "text": "⏹ " + _("Ja, beenden"),
                            "callback_data": tp._cbdata(f"ta:E:{promo.pk}"),
                        },
                        {
                            "text": _("Abbrechen"),
                            "callback_data": tp._cbdata(f"ta:s:{promo.pk}"),
                        },
                    ]
                ]
            },
        )
        return "end_confirm"
    target = {"p": "paused", "a": "active", "E": "ended"}[action]
    if promo.status == target:  # двойное нажатие / старая кнопка — без повторных эффектов
        return show_card(bot, chat, promo, note=_("Schon erledigt."))
    if target == "active" and _expired(promo):
        # Срок прошёл: beat завершает только активные — оживлённая акция мигнула бы в
        # каналах и каталоге. Новый срок — через 🔁 (копия) или веб-форму.
        return show_card(bot, chat, promo, note=_("Abgelaufen — bitte 🔁 Wiederholen nutzen."))
    actor = tp.owner_user(tenant)
    try:
        if target == "active":
            limits.activate(promo, tenant, actor=actor)
        else:
            PromotionSM().apply(promo, target, actor=actor)
    except limits.ActivationLimit as exc:
        tp._send(bot, chat, limits.limit_message(exc.limit))
        return "limit"
    except IllegalTransition:
        promo.refresh_from_db()
        return show_card(bot, chat, promo, note=_("Nicht möglich im aktuellen Status."))
    promo.refresh_from_db()
    notes = {
        "paused": _("⏸ Pausiert — die Aktion ist nicht mehr sichtbar."),
        "active": _("▶ Aktiv."),
        "ended": _("⏹ Beendet."),
    }
    show_card(bot, chat, promo, note=notes[target])
    return f"action_{target}"
