"""AIS A-5b: уточняющий вопрос помощника вместо тупикового «bitte genauer».

План — docs/ais-a5-one-brain-plan-2026-11-06.md §2 + правки архитектора §9 п. 3–6.

Строители пакета (A-4b `assistant_changes.build`, A-4d `assistant_bulk.expand`, A-4e
`assistant_ai_actions.check_actions`) оставляют прежний `blocked` (запасной текст) и
добавляют к пункту данные вопроса: `item["clarify"] = {slot, options, …}`. Здесь — один
пост-шаг: первый такой пункт превращает запись задачи в вопрос с кнопками (`outcome="ask"`);
ответ выбирает ОДИН вариант из записанных в кэше (не из POST и не из истории) и собирает
пункт ЗАНОВО тем же строителем — со свежим «vorher» и проверкой прав при показе/применении.

Слоты:
* `pick_target` — два объекта с одним именем («Käsekuchen» в двух категориях);
* `direction` — «alle Kuchen um 10 %» без «teurer/günstiger».

Не больше двух вопросов на задачу; после — прежний `blocked` со ссылкой на экран.
Модель на ответ не зовётся.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

MAX_ROUNDS = 2
MAX_OPTIONS = 6

SLOTS = ("pick_target", "direction")


def question(slot: str) -> str:
    return {
        "pick_target": _("Welchen Eintrag meinen Sie?"),
        "direction": _("Teurer oder günstiger?"),
    }.get(slot, _("Bitte genauer sagen."))


def _first(items: list[dict]) -> int | None:
    for i, item in enumerate(items or ()):
        c = item.get("clarify")
        if isinstance(c, dict) and c.get("slot") in SLOTS and len(c.get("options") or ()) >= 2:
            return i
    return None


def _strip(items: list[dict]) -> list[dict]:
    """Пункты без данных вопроса (остаются прежние `blocked` — тупик честный)."""
    return [{k: v for k, v in it.items() if k != "clarify"} for it in items]


def wrap(job: str, items: list[dict], summary: list, q: str, round_: int = 1) -> dict | None:
    """Готовая запись «вопрос» для пакета или None — вопросов нет (обычный предпросмотр)."""
    at = _first(items) if round_ <= MAX_ROUNDS else None
    if at is None:
        return None
    clarify = items[at]["clarify"]
    return {
        "state": "done",
        "outcome": "ask",
        "job": job,
        "slot": clarify["slot"],
        "options": [dict(o) for o in clarify["options"][:MAX_OPTIONS]],
        "at": at,
        "round": round_,
        "base": items,
        "question": q,  # в историю — когда пакет будет готов (не сам вопрос)
        "summary": summary,
    }


def done_entry(job: str, items: list[dict], summary: list, source: str = "") -> dict:
    entry = {
        "state": "done",
        "outcome": "actions",
        "actions": _strip(items),
        "job": job,
        "summary": summary,
    }
    if source:
        entry["source"] = source
    return entry


class AnswerError(Exception):
    pass


def answer(request, entry: dict, option: str) -> list[dict]:
    """Ответ на вопрос → новые пункты пакета (тот же порядок). Бросает AnswerError на чужой
    вариант, удалённый объект или сбой строителя."""
    from apps.core import assistant_actions, assistant_bulk, assistant_changes

    ids = {str(o.get("id")) for o in entry.get("options") or ()}
    option = str(option or "")
    if option not in ids:
        raise AnswerError("option")
    base = list(entry.get("base") or [])
    at = entry.get("at")
    if not isinstance(at, int) or not 0 <= at < len(base):
        raise AnswerError("state")
    clarify = base[at].get("clarify") or {}
    if clarify.get("slot") == "pick_target":
        kind, _sep, pk = option.partition(":")
        if kind not in ("product", "category", "service"):
            raise AnswerError("option")
        obj = assistant_actions._manager(kind).filter(pk=pk).first()
        if obj is None or getattr(obj, "deleted_at", None):
            raise AnswerError("gone")
        verb = clarify.get("verb") or ""
        if kind != "product" and verb == "move":
            raise AnswerError("option")
        item = assistant_changes.item_for(
            kind, verb, obj, clarify.get("value") or "", clarify.get("note") or ""
        )
        if clarify.get("fixed"):
            item["fixed"] = True
        base[at] = item
        return base
    if clarify.get("slot") == "direction":
        from apps.catalog.models import Category

        cat = Category.objects.filter(pk=clarify.get("cat")).first()
        if cat is None:
            raise AnswerError("gone")
        word = "teurer" if option == "up" else "günstiger"
        return assistant_bulk.expand(
            request.tenant, cat, "price", f"{clarify.get('text', '')} {word}"
        )
    raise AnswerError("state")


def summary_for(items: list[dict]) -> list[dict]:
    """Сводка для истории по ГОТОВЫМ пунктам (после ответа массовый пакет мог смениться)."""
    from apps.core import assistant_bulk

    if not items:
        return []
    bulk = assistant_bulk.meta(items)
    if bulk is not None:
        return [{"action": items[0]["action"], "name": bulk["title"], "bulk": True}]
    return [
        {
            "action": it["action"],
            "name": (it.get("values") or {}).get("name", ""),
            # A-5c: для «und den Käsekuchen auch» — КОД действия (без цен и pk)
            "verb": _verb_of(it),
        }
        for it in items
    ]


def _verb_of(item: dict) -> str:
    action = str(item.get("action") or "")
    if action.endswith(".visibility"):
        return "show" if (item.get("values") or {}).get("visible") else "hide"
    if action.endswith(".price"):
        return "price"
    if action.endswith(".move"):
        return "move"
    return ""


def options_for_rows(rows: list[dict]) -> list[dict]:
    """Варианты «какой из одноимённых» — с подписью, по которой их различить."""
    from apps.catalog.models import Category
    from apps.core import assistant_changes

    # категории товаров — одним запросом (≤ 6 вариантов, без N+1)
    cat_ids = {
        r["obj"].category_id for r in rows if r["kind"] == "product" and r["obj"].category_id
    }
    cats = {c.pk: c for c in Category.objects.filter(pk__in=cat_ids)} if cat_ids else {}
    for r in rows:
        if r["kind"] == "product":
            r["obj"]._clarify_cat = cats.get(r["obj"].category_id)
    out, seen = [], set()
    for row in rows:
        key = f"{row['kind']}:{row['obj'].pk}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": key, "label": _label(row["kind"], row["obj"], assistant_changes)})
        if len(out) >= MAX_OPTIONS:
            break
    # одинаковые подписи (одно имя в одной категории) различаем номером: кнопки не путаются
    counts: dict[str, int] = {}
    for o in out:
        counts[o["label"]] = counts.get(o["label"], 0) + 1
    seen_n: dict[str, int] = {}
    for o in out:
        if counts[o["label"]] > 1:
            seen_n[o["label"]] = seen_n.get(o["label"], 0) + 1
            o["label"] = f"{o['label']} ({seen_n[o['label']]})"
    return out


def _label(kind: str, obj, assistant_changes) -> str:
    name = assistant_changes._display(kind, obj)
    if kind == "product":
        cat = getattr(obj, "_clarify_cat", None)
        where = cat.get_i18n("name") if cat is not None else _("ohne Kategorie")
        state = "" if obj.is_active else " · " + _("ausgeblendet")
        return f"{name} · {where}{state}"
    kinds = {"category": _("Kategorie"), "service": _("Leistung")}
    return f"{name} · {kinds.get(kind, '')}"
