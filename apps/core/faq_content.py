"""FB-33 M3-5b: вопросы FAQ сайта — один писатель (`site_config["faq"]` и его переводы).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3» (FAQ M3-5b), решения владельца:
1) переводы `i18n[<язык>]["faq"]` позиционные (витрина байт-в-байт), при перестановке,
   удалении и вставке они едут за вопросом по ИНДЕКСУ ИСТОЧНИКА (`src` — номер вопроса в
   списке, с которого начата правка), без id и без переноса данных;
2) правка немецкого текста вопроса или ответа снимает перевод ИМЕННО этого поля — у всех
   писателей одинаково (Студия, окно блока «Seitenaufbau», канва `set_text`).

Пишут только через этот модуль: Студия (`put`), черновик «Seitenaufbau» (`put` при
«Speichern», `apply_ops` в окне), канва (`set_text`). Исключения — демо-киты и их переводы
(`demo_kits`, `demo_i18n`): они собирают конфиг целиком (замок «один писатель»).

Межзапросные писатели (Студия со старой страницы или восстановленный `_draft`, канва)
несут отпечаток списка, с которого начата правка (`base_fp`): не совпал с сохранённым —
индексы ничего не значат, переводы сопоставляются по тексту вопроса (тот же путь, что
запись поверх конфликта), в лог — предупреждение.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

#: потолки — только на вводе (сохранённое не режется), с сообщением владельцу
MAX_ITEMS = 12
MAX_Q = 200
MAX_A = 2000
FIELDS = ("q", "a")
#: строки, в окне которых правятся вопросы: секция главной и блок-ссылка на страницах
ROW_KEYS = ("faq", "faq_ref")


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def base_items(config: dict) -> list[dict]:
    """Сохранённые вопросы {q, a} (как их держит `normalize`)."""
    out = []
    for item in (config or {}).get("faq") or ():
        if isinstance(item, dict) and _s(item.get("q")):
            out.append({"q": _s(item.get("q")), "a": _s(item.get("a"))})
    return out


def fingerprint(items) -> str:
    """Отпечаток списка вопросов (только тексты, порядок важен)."""
    rows = [[_s((i or {}).get("q")), _s((i or {}).get("a"))] for i in items or ()]
    raw = json.dumps(rows, ensure_ascii=False).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def revision(items, src) -> str:
    """Отпечаток СОСТОЯНИЯ правки (тексты и источники) — кнопки окна (↑↓, Entfernen) несут
    его, чтобы вторая вкладка браузера не нажала их по устаревшему номеру."""
    raw = json.dumps([fingerprint(items), list(src or ())]).encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:12]


def limit_note() -> str:
    return _("Zu lange Fragen oder Antworten wurden gekürzt (höchstens %(q)s / %(a)s Zeichen).") % {
        "q": MAX_Q,
        "a": MAX_A,
    }


def full_note() -> str:
    return _("Höchstens %(n)s Fragen — weitere wurden nicht übernommen.") % {"n": MAX_ITEMS}


def clean_input(rows, notes: list | None = None) -> tuple[list[dict], list]:
    """Ввод владельца → ([{q, a}], src). Пустой вопрос — вопроса нет; длины и число режутся
    с сообщением. `rows` — [{q, a, src}] (src — индекс источника или None)."""
    items, src, cut, over = [], [], False, False
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        q, a = _s(row.get("q")), _s(row.get("a"))
        if not q:
            continue
        if len(items) >= MAX_ITEMS:
            over = True
            break
        if len(q) > MAX_Q or len(a) > MAX_A:
            cut = True
            q, a = q[:MAX_Q], a[:MAX_A]
        items.append({"q": q, "a": a})
        s = row.get("src")
        src.append(s if isinstance(s, int) and not isinstance(s, bool) and s >= 0 else None)
    if notes is not None:
        if cut:
            notes.append(limit_note())
        if over:
            notes.append(full_note())
    return items, src


def from_form(get, notes: list | None = None) -> tuple[list[dict], list] | None:
    """Пары Студии `faq_q_<i>` / `faq_a_<i>` (сентинел `faq_present`): номер поля — индекс
    вопроса в списке, с которого открыта форма (источник). Без сентинела — None (старая форма
    `faq_text` идёт прежним разбором, переводы — по тексту)."""
    if not _s(get("faq_present", "")):
        return None
    rows = []
    for i in range(MAX_ITEMS * 4):
        q = get(f"faq_q_{i}", None)
        if q is None:
            continue
        rows.append({"q": q, "a": get(f"faq_a_{i}", ""), "src": i})
    return clean_input(rows, notes)


def _ov_entry(entry) -> dict:
    """Запись перевода — только строки q/a (мусор оверлея ничего не значит)."""
    if not isinstance(entry, dict):
        return {}
    return {k: entry[k] for k in FIELDS if isinstance(entry.get(k), str) and entry[k].strip()}


def _text_mapping(old: list[dict], new: list[dict]) -> list:
    """Запасное сопоставление по тексту вопроса: каждый старый вопрос — не больше одного раза
    (два одинаковых вопроса не делят один перевод)."""
    free: dict[str, list[int]] = {}
    for i, item in enumerate(old):
        free.setdefault(item["q"], []).append(i)
    out = []
    for item in new:
        slots = free.get(item["q"])
        out.append(slots.pop(0) if slots else None)
    return out


def _mapping(old: list[dict], new: list[dict], src, by_text: bool) -> list:
    if by_text or src is None:
        return _text_mapping(old, new)
    seen, out = set(), []
    for j in range(len(new)):
        s = src[j] if j < len(src) else None
        if isinstance(s, int) and 0 <= s < len(old) and s not in seen:
            seen.add(s)
            out.append(s)
        else:
            out.append(None)
    return out


def put(config: dict, items, src=None, base_fp: str | None = None) -> None:
    """Записать вопросы `items` ([{q, a}]) в базу и переставить переводы по `src`.

    `src[j]` — индекс вопроса j в СОХРАНЁННОМ списке (None — новый вопрос). `base_fp` —
    отпечаток списка, от которого считаны индексы: не совпал с сохранённым (или `src` нет) —
    сопоставление по тексту вопроса. Перевод поля, чей немецкий текст изменился, снимается.
    Мутирует `config`."""
    old = base_items(config)
    new = [{"q": _s(i.get("q")), "a": _s(i.get("a"))} for i in items or () if _s(i.get("q"))]
    by_text = base_fp is not None and base_fp != fingerprint(old)
    if by_text:
        logger.warning("faq_content: base changed meanwhile — translations matched by text")
    mapping = _mapping(old, new, src, by_text)
    config["faq"] = new
    overlay = config.get("i18n")
    if not isinstance(overlay, dict):
        return
    for loc in list(overlay):
        node = overlay[loc]
        if not isinstance(node, dict) or "faq" not in node:
            continue
        tr = node["faq"] if isinstance(node["faq"], list) else []
        moved = []
        for j, s in enumerate(mapping):
            entry = _ov_entry(tr[s]) if s is not None and s < len(tr) else {}
            for field in FIELDS:
                if s is not None and old[s][field] != new[j][field]:
                    entry.pop(field, None)  # немецкий текст изменился — перевод устарел
            moved.append(entry)
        while moved and not moved[-1]:
            moved.pop()  # хвост без переводов не храним
        if moved:
            node["faq"] = moved
        else:
            node.pop("faq")


def set_text(config: dict, index: int, field: str, value: str, locale: str = "") -> bool:
    """Канва: одно поле вопроса `index`. На языке перевода — перевод этого поля; на основном —
    база, а перевод именно этого поля у всех языков снимается (как у `put`). False — индекса
    или поля нет (или пустой вопрос, который удалил бы пару)."""
    from apps.tenants import siteconfig

    old = base_items(config)
    if field not in FIELDS or not (0 <= index < len(old)):
        return False
    value = _s(value)
    if field == "q" and not value:
        return False
    if locale:
        siteconfig.set_overlay_value(config, locale, ("faq", index, field), value)
        return True
    if old[index][field] == value:
        return True
    new = copy.deepcopy(old)
    new[index][field] = value
    put(config, new, list(range(len(new))))
    return True


# ───────────── окно блока «Seitenaufbau» (вкладка «Texte») ─────────────


def state(config: dict, draft: dict | None = None) -> tuple[list[dict], list]:
    """Текущее состояние правки: черновика (если в нём есть вопросы) или сохранённое."""
    pending = (draft or {}).get("faq")
    if isinstance(pending, dict) and isinstance(pending.get("items"), list):
        return copy.deepcopy(pending["items"]), list(pending.get("src") or ())
    items = base_items(config)
    return items, list(range(len(items)))


def _index(value, size: int):
    try:
        i = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return i if 0 <= i < size else None


def apply_ops(items: list[dict], src: list, post, notes: list | None = None):
    """Форма окна → новое (items, src). Тексты `faq_<i>_q|a` (пустой вопрос — удалить),
    кнопки `faq_remove=<i>`, `faq_move=<i>:up|down`, новый вопрос `faq_new_q|a`. Сначала
    тексты, затем кнопка — набранное не теряется."""
    rows = []
    for i, item in enumerate(items):
        q = post.get(f"faq_{i}_q")
        a = post.get(f"faq_{i}_a")
        rows.append(
            {
                "q": item["q"] if q is None else q,
                "a": item["a"] if a is None else a,
                "src": src[i] if i < len(src) else None,
            }
        )
    remove = _index(post.get("faq_remove"), len(rows))
    if remove is not None:
        rows.pop(remove)
    move = str(post.get("faq_move") or "")
    at, _sep, way = move.partition(":")
    at = _index(at, len(rows))
    if at is not None and way in ("up", "down"):
        to = at - 1 if way == "up" else at + 1
        if 0 <= to < len(rows):
            rows[at], rows[to] = rows[to], rows[at]
    new_q = _s(post.get("faq_new_q"))
    if new_q:
        rows.append({"q": new_q, "a": post.get("faq_new_a", ""), "src": None})
    return clean_input(rows, notes)


def stale_note() -> str:
    return _(
        "Die Fragen wurden inzwischen an anderer Stelle geändert – nichts übernommen. "
        "Bitte noch einmal versuchen."
    )


def panel(items: list[dict], src: list, config: dict) -> dict:
    """Модель части «Fragen» окна блока."""
    return {
        "items": [{"i": i, "n": i + 1, "q": it["q"], "a": it["a"]} for i, it in enumerate(items)],
        "free": len(items) < MAX_ITEMS,
        "max": MAX_ITEMS,
        "max_q": MAX_Q,
        "max_a": MAX_A,
        "rev": revision(items, src),
        "base": fingerprint(base_items(config)),
    }
