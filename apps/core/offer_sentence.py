"""AIS-2: «Beschreiben Sie Ihr Geschäft in einem Satz» → строки для «Angebot prüfen».

Тонкий адаптер поверх `setup_assistant.build_plan` (правила + ИИ с пост-проверкой): из
фразы владельца получаем до `MAX_STEPS` позиций и превращаем их в ТЕКСТ строк формата
`offer_lines` («Name — 0,50 €», у услуги ещё «— 30 min»). Адаптер ничего не пишет в базу и
ничего не добавляет к плану, кроме разделителей: имя, цена и длительность — только из плана,
а план — только из слов владельца. Создание — штатным «Übernehmen» шага.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from apps.core import ratelimit, setup_assistant
from apps.core.offer_lines import MAX_LINE

logger = logging.getLogger(__name__)

TEXT_MAX = setup_assistant.TEXT_MAX
#: Плановые сущности → вид ввода шага «Angebot prüfen». product — «умолчание по цене» у
#: правил (позиция без слова-вида), поэтому её строки подходят любому виду.
KIND_ENTITY = {
    "waren": "product",
    "speisekarte": "product",
    "anfragen": "product",
    "termine": "service",
    "zimmer": "room",
    "tickets": "event",
}
LINE_ENTITIES = frozenset(KIND_ENTITY.values())

_INTRO_RE = re.compile(r"^([^:\d]{1,60}):\s*(.+)$", re.DOTALL)


@dataclass(frozen=True)
class Result:
    lines: list[dict] = field(default_factory=list)  # [{"e": entity, "t": text}]
    note: object = ""


def _strip_intro(text: str) -> str:
    """«Bäckerei: Brötchen 0,50 €, …» → «Brötchen 0,50 €, …». Вступление не становится
    позицией; но «Brötchen: 0,50 €» — это имя с ценой, его не режем."""
    m = _INTRO_RE.match(text)
    if not m:
        return text
    rest = m.group(2).strip()
    first = setup_assistant._SPLIT_RE.split(rest, maxsplit=1)[0]
    if not re.search(r"[^\W\d_]", first.replace("€", "")):
        return text
    return rest


def _line(step: dict) -> str:
    parts = [step["name"]]
    if step.get("price"):
        parts.append(f"{step['price']} €")
    if step["entity"] == setup_assistant.ENTITY_SERVICE and step.get("duration"):
        parts.append(f"{step['duration']} min")
    return " — ".join(parts)[:MAX_LINE]


def build(tenant, user, text: str) -> Result:
    """Фраза → строки. Никогда не бросает и ничего не пишет."""
    text = (text or "").strip()[:TEXT_MAX]
    if not text:
        return Result()
    body = _strip_intro(text)
    allowed = setup_assistant.allowed_entities(tenant, user)
    if ratelimit.hit(
        "setup-plan",
        str(user.pk),
        limit=_plan_limit(),
        window=_plan_window(),
    ):
        # лимит не блокирует мастер: правила без ИИ
        plan = setup_assistant.plan_from_rules(body, tenant, allowed) if allowed else None
    else:
        plan = setup_assistant.build_plan(body, tenant, user)
    if plan is None:
        return Result(note=_("Sie dürfen hier nichts anlegen."))
    data = setup_assistant.plan_to_data(plan)
    lines = [
        {"e": st["entity"], "t": _line(st)}
        for st in data["steps"]
        if st["entity"] in LINE_ENTITIES and st.get("name")
    ]
    note = data.get("note") or ""
    if not lines:
        note = note or _("Keine Angebote erkannt — tragen Sie sie im nächsten Schritt ein.")
    elif any(st["entity"] not in LINE_ENTITIES for st in data["steps"]):
        note = _("Kategorien und Aktionen legen Sie später an.")
    return Result(lines=lines, note=note)


def _plan_limit() -> int:
    from apps.core import page_templates

    return page_templates.PLAN_LIMIT


def _plan_window() -> int:
    from apps.core import page_templates

    return page_templates.PLAN_WINDOW


def clean_lines(raw) -> list[dict]:
    """Сохранённые строки из состояния мастера — только известные сущности и строки."""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw[: setup_assistant.MAX_STEPS]:
        if not isinstance(item, dict):
            continue
        entity, value = item.get("e"), item.get("t")
        if entity in LINE_ENTITIES and isinstance(value, str) and value.strip():
            out.append({"e": entity, "t": value.strip()[:MAX_LINE]})
    return out


def lines_for_kind(lines, kind: str) -> str:
    """Текст для textarea вида: строки его сущности + товарные (умолчание по цене)."""
    want = KIND_ENTITY.get(kind)
    if not want:
        return ""
    return "\n".join(x["t"] for x in clean_lines(lines) if x["e"] == want or x["e"] == "product")
