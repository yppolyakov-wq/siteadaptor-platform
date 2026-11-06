"""AIS A-3c: плавающая панель «✨ Assistent» — вкладки KI · Support · Kunden в шторке.

План — docs/ais-a3-assistant-panel-plan-2026-11-06.md. Панель — та же шторка помощника
(`assistant`), вкладки — ссылки `?tab=` (без JS — полная страница). Каждая вкладка видна,
только если её экран открывается этому запросу (права, пакет, Mini App — тот же
`setup_assistant.reachable`). Только чтение: тред поддержки и беседа клиента открываются на
своих страницах; новая заявка в поддержку — штатной формой `support:help`.
"""

from __future__ import annotations

import logging

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

TABS = ("ki", "support", "kunden")
LIST_MAX = 5

_LABELS = {"ki": _("KI-Assistent"), "support": _("Support"), "kunden": _("Kunden")}


def tab_of(request) -> str:
    tab = (request.GET.get("tab") or "").strip()
    return tab if tab in TABS else "ki"


def _reachable(request, url_name: str) -> bool:
    from apps.core import setup_assistant

    return setup_assistant.reachable(request, url_name)


def _available(request, key: str) -> bool:
    try:
        if key == "ki":
            return True
        if key == "support":
            return _reachable(request, "support:help")
        if key == "kunden":
            return request.tenant.is_module_active("inbox") and _reachable(request, "inbox:list")
    except Exception:  # noqa: BLE001 — вкладка-дополнение: при сбое её просто нет
        logger.warning("assistant panel: tab gate failed for %s", key, exc_info=True)
    return False


def tabs_for(request, active: str, seite: str = "") -> list[dict]:
    from urllib.parse import urlencode

    base = reverse("assistant")
    out = []
    for key in TABS:
        if not _available(request, key):
            continue
        query = {"tab": key} if key != "ki" else {}
        if seite:
            query["seite"] = seite
        out.append(
            {
                "key": key,
                "label": _LABELS[key],
                "url": base + (f"?{urlencode(query)}" if query else ""),
                "active": key == active,
            }
        )
    return out


def resolve_tab(request) -> str:
    """Запрошенная вкладка, если она доступна; иначе KI."""
    tab = tab_of(request)
    return tab if _available(request, tab) else "ki"


def support_unread(request) -> int:
    """Тредов, где поддержка ответила, а владелец ещё не прочёл (точка на кнопке)."""
    try:
        from apps.support.models import SupportThread

        return SupportThread.objects.filter(tenant=request.tenant, unread_for_owner=True).count()
    except Exception:  # noqa: BLE001 — точка-дополнение; поломку видно в логе, а не тихим нулём
        logger.warning("assistant panel: support unread failed", exc_info=True)
        return 0


def support_ctx(request) -> dict:
    from apps.support.models import SupportThread

    threads = list(
        SupportThread.objects.filter(tenant=request.tenant).order_by(
            "-unread_for_owner", "-last_message_at", "-created_at"
        )[:LIST_MAX]
    )
    return {"threads": threads, "help_url": reverse("support:help")}


def kunden_ctx(request) -> dict:
    """Последние беседы: непрочитанные первыми. Только тема, имя и время — контакты
    клиента (e-mail/телефон) в панель не выводятся."""
    from apps.inbox.models import Conversation

    rows = []
    qs = Conversation.objects.select_related("customer").order_by(
        "-unread_for_staff", "-last_message_at", "-created_at"
    )[:LIST_MAX]
    for conv in qs:
        rows.append(
            {
                "url": reverse("inbox:thread", args=[conv.pk]),
                "subject": conv.subject or conv.ref_label or "",
                "name": getattr(conv.customer, "name", "") if conv.customer_id else "",
                "unread": conv.unread_for_staff,
                "at": conv.last_message_at or conv.created_at,
            }
        )
    return {"conversations": rows, "inbox_url": reverse("inbox:list")}
