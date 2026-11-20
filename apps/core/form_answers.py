"""FB-33 M2i: свои вопросы формы и ответы на них — чистое ядро (без моделей и site_config).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i» (вердикт architect): одно ядро
«вопросы владельца → ответы клиента» для заявки и оформления заказа, чтобы не заводить третью
копию рядом с `Event.questions` и `apps/events/registration.py` (их перевод сюда — отложено).

* `normalize_questions` — вопросы владельца (капы, типы, монотонные id `q<n>`: номер удалённого
  вопроса не достаётся новому, иначе старый ответ получил бы чужую подпись);
* `collect` — ответы из POST только на заданные вопросы (лишнее отбрасывается);
* `validate` — какие обязательные вопросы без ответа (проверка сервера, не только HTML);
* `snapshot` — то, что хранит сделка: `{id: {"label", "value"}}` (у выбора значение — текст
  варианта) с подписью на момент ответа (переименование вопроса не обесценивает старые сделки).

До M2i-2 (миграции `custom_answers`) потребитель `collect`/`validate`/`snapshot` — только тесты:
это заготовка для вопросов заявки (M2i-2) и корзины (M2i-4), не мёртвый код.
"""

from __future__ import annotations

import math
import re
from datetime import date

TYPES = ("text", "textarea", "choice", "bool", "number", "date")
MODES = ("opt", "req")
MAX_QUESTIONS = 10
MAX_OPTIONS = 20
LABEL_MAX = 120
ANSWER_MAX = 500
_ID = re.compile(r"^q([1-9][0-9]{0,3})$")
ID_MAX = 9999  # q1…q9999 (формат id)
#: невидимые символы (нулевой ширины, BOM) — строка из них не «заполнена»
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def clean_text(value, limit: int) -> str:
    """Строка без невидимых символов и лишних пробелов (общая для подписей и ответов)."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", _INVISIBLE.sub("", value)).strip()[:limit]


_s = clean_text


def normalize_questions(raw, next_id=0) -> tuple[list[dict], int]:
    """Вопросы владельца и следующий свободный номер. Мусор отбрасывается молча (это настройка,
    не ввод клиента); вопрос без подписи или выбор без вариантов — не вопрос."""
    try:
        counter = min(max(int(next_id), 0), ID_MAX)
    except (TypeError, ValueError, OverflowError):  # inf/мусор в настройке — с нуля
        counter = 0
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or len(out) >= MAX_QUESTIONS:
            continue
        match = _ID.match(str(item.get("id") or ""))
        label = _s(item.get("label"), LABEL_MAX)
        kind = item.get("type") if item.get("type") in TYPES else "text"
        if not match or not label or item["id"] in seen:
            continue
        question = {"id": item["id"], "type": kind, "label": label}
        if kind == "choice":
            options = []
            for opt in item.get("options") if isinstance(item.get("options"), list) else []:
                text = _s(opt, LABEL_MAX)
                if text and text not in options:
                    options.append(text)
                if len(options) >= MAX_OPTIONS:
                    break
            if not options:
                continue
            question["options"] = options
        if item.get("mode") == "req":
            question["mode"] = "req"
        seen.add(item["id"])
        counter = max(counter, int(match.group(1)))
        out.append(question)
    return out, counter


def new_id(next_id: int) -> str:
    """Номер следующего вопроса (писатель хранит `next_id` рядом со списком)."""
    return f"q{int(next_id) + 1}"


def _value(question: dict, raw: str):
    """Значение ответа или None (пусто/битое). Разбор мягкий: битое = нет ответа."""
    raw = (
        clean_text(raw, 10_000)
        if question["type"] != "textarea"
        else _INVISIBLE.sub("", raw or "").strip()
    )
    kind = question["type"]
    if kind == "bool":
        return True if raw in ("1", "on", "true", "yes") else None
    if not raw:
        return None
    if kind == "choice":
        return raw if raw in question.get("options", []) else None
    if kind == "number":
        try:
            number = float(raw.replace(",", "."))
        except ValueError:
            return None
        if not math.isfinite(number) or abs(number) > 1e9:
            return None  # nan/inf и гигантские — не ответ (обязательный — не заполнен)
        return int(number) if number.is_integer() else number
    if kind == "date":
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            return None
    limit = ANSWER_MAX if kind == "textarea" else LABEL_MAX * 2
    return raw[:limit]


def collect(questions: list[dict], post, prefix: str = "") -> dict:
    """Ответы {id: значение} только на заданные вопросы; лишние поля POST игнорируются."""
    out = {}
    for question in questions:
        value = _value(question, post.get(prefix + question["id"], ""))
        if value is not None:
            out[question["id"]] = value
    return out


def validate(questions: list[dict], answers: dict) -> list[str]:
    """id обязательных вопросов без ответа (порядок вопросов)."""
    return [q["id"] for q in questions if q.get("mode") == "req" and q["id"] not in answers]


def snapshot(questions: list[dict], answers: dict) -> dict:
    """Что хранит сделка: подпись вопроса на момент ответа и значение."""
    out = {}
    for question in questions:
        if question["id"] in answers:
            out[question["id"]] = {
                "label": question["label"],
                "value": answers[question["id"]],
                "type": question["type"],  # показ (дата, «да») — по типу вопроса
            }
    return out


def rows(stored) -> list[tuple[str, str]]:
    """Что показывают карточка сделки, письмо владельцу и PDF: [(подпись, значение)] из
    сохранённого снимка (порядок вопросов на момент ответа). Пусто/мусор — [] (старые сделки
    ничего не рисуют). Поиска по ответам нет: поле зашифровано (решение M2i)."""
    from datetime import date as _date

    from django.utils.formats import date_format
    from django.utils.translation import pgettext

    out = []
    for item in (stored or {}).values() if isinstance(stored, dict) else ():
        if not isinstance(item, dict) or not item.get("label"):
            continue
        value = item.get("value")
        kind = item.get("type") or "text"  # старые снимки без типа — как текст
        if value is True:
            shown = pgettext("answer yes", "Ja")
        elif kind == "date" and isinstance(value, str):
            try:
                shown = date_format(_date.fromisoformat(value), "d.m.Y")
            except ValueError:
                shown = value
        elif value is None or value == "":
            continue
        else:
            shown = str(value)
        out.append((str(item["label"]), shown))
    return out
