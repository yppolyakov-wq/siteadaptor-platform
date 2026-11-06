"""AIS A-5c: «und den Käsekuchen auch» — продолжение прошлого хода помощника.

План — docs/ais-a5-one-brain-plan-2026-11-06.md §3 + правки архитектора §9 п. 7–8.

Срабатывает, только если сошлось ВСЁ:
* во фразе есть маркер «auch / ebenfalls / тоже / также / теж / також / too / as well»;
* фраза не вопрос и не содержит собственного глагола (его поймали бы правила A-4b раньше);
* остаток называет РОВНО ОДИН существующий объект (как у правил A-4b);
* последний ход ЭТОГО пользователя (в этой схеме, не старше 15 минут) — пакет изменений с
  одним пунктом и известным действием (не массовый).

Из прошлого хода берётся только КОД действия (скрыть/показать/цена/перенос) — ни цены, ни
категории, ни пункты старого пакета: строится НОВЫЙ пункт тем же `item_for` (цену и цель
переноса владелец впишет сам). Дальше — обычный предпросмотр и «Alles übernehmen».
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

WINDOW = timedelta(minutes=15)
TEXT_MAX = 200

_W, _E = r"(?<!\w)", r"(?!\w)"
_MARKER = re.compile(
    _W + r"(?:auch|ebenfalls|genauso|тоже|также|теж|також|too|as\s+well)" + _E, re.IGNORECASE
)
_VERBS = ("hide", "show", "price", "move")


def _last_turn(request):
    from apps.core.models import AssistantTurn

    since = timezone.now() - WINDOW
    return (
        AssistantTurn.objects.filter(user=request.user, created_at__gte=since)
        .order_by("-created_at")
        .first()
    )


def _previous(request) -> dict | None:
    """Код и вид действия прошлого хода или None (не подходит для продолжения)."""
    turn = _last_turn(request)
    if turn is None:
        return None
    summary = (turn.entry or {}).get("summary") or []
    if (turn.entry or {}).get("outcome") != "actions" or len(summary) != 1:
        return None
    row = summary[0]
    if row.get("bulk") or row.get("verb") not in _VERBS:
        return None
    kind = str(row.get("action") or "").split(".")[0]
    if kind not in ("product", "service", "category"):
        return None
    return {"kind": kind, "verb": row["verb"]}


def _find(request, q: str):
    from apps.core import assistant_changes

    text = (q or "").strip()[:TEXT_MAX]
    if not _MARKER.search(text) or assistant_changes._looks_like_question(text):
        return None
    prev = _previous(request)
    if prev is None:
        return None
    kinds = assistant_changes._kinds_for(request.tenant, request.user, prev["verb"])
    if prev["kind"] not in kinds:
        return None
    rows = assistant_changes._index(request.tenant, (prev["kind"],))
    found, _start, _end = assistant_changes._matches(text.casefold(), rows, (prev["kind"],))
    if len({r["obj"].pk for r in found}) != 1:
        return None
    return prev, found[0]["obj"]


def intent(request, q: str):
    try:
        return _find(request, q)
    except Exception:  # noqa: BLE001 — fail closed: обычная цепочка
        logger.exception("assistant followup: intent failed")
        return None


def build(prev: dict, obj) -> list[dict]:
    from apps.core import assistant_changes

    note = ""
    if prev["verb"] == "price":
        note = _("Bitte einen Preis angeben.")
    item = assistant_changes.item_for(prev["kind"], prev["verb"], obj, "", note)
    return [item]
