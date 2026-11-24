"""FB-33 M2i: свои вопросы формы и ответы на них — чистое ядро (без моделей и site_config).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i» (вердикт architect): одно ядро
«вопросы владельца → ответы клиента» для заявки и оформления заказа, чтобы не заводить третью
копию рядом с `Event.questions` и `apps/events/registration.py` (их перевод сюда — отложено).

* `normalize_questions` — вопросы владельца (капы, типы, монотонные id `q<n>`: номер удалённого
  вопроса не достаётся новому, иначе старый ответ получил бы чужую подпись);
* `collect` — ответы из POST только на заданные вопросы (лишнее отбрасывается);
* `validate` — какие обязательные вопросы без ответа (проверка сервера, не только HTML);
* `snapshot` — то, что хранит сделка: `{id: {"label", "value"}}` (у выбора значение — текст
  варианта) с подписью на момент ответа (переименование вопроса не обесценивает старые сделки);
* `answers_for_deal` — снимок для сделки (корзина, заявка) одним путём: FB-33 D1 (решение
  владельца, вариант A) — ответ на вопрос, удалённый между показом формы и отправкой, и выбор
  вне текущих вариантов не пропадают молча, а хранятся с признаком `stale` (`dropped` — что
  не легло ответом; в лог только id).

До M2i-2 (миграции `custom_answers`) потребитель `collect`/`validate`/`snapshot` — только тесты:
это заготовка для вопросов заявки (M2i-2) и корзины (M2i-4), не мёртвый код.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date

logger = logging.getLogger(__name__)

TYPES = ("text", "textarea", "choice", "bool", "number", "date")
MODES = ("opt", "req")
MAX_QUESTIONS = 10
MAX_OPTIONS = 20
LABEL_MAX = 120
ANSWER_MAX = 500
_ID = re.compile(r"^q([1-9][0-9]{0,3})$")
ID_MAX = 9999  # q1…q9999 (формат id)
#: FB-33 M2i-5: временный id нового вопроса в черновике «Seitenaufbau» (настоящий `q<n>`
#: назначает только запись черновика под блокировкой — `form_spec.put`)
TEMP_ID = re.compile(r"^n[0-9]{1,3}$")
#: FB-33 D1: сколько «осиротевших» ответов сделка хранит (POST не раздувает зашифрованное поле)
STALE_MAX = 10
#: сколько id лишних ответов пишет одна строка лога (ключей `q<n>` в POST может быть тысячи)
LOG_IDS_MAX = 20
STALE_REMOVED = "removed"  # вопроса больше нет — подпись «Entfernte Frage» при показе
STALE_CHANGED = "changed"  # выбор вне текущих вариантов — подпись вопроса и пометка
#: невидимые символы (нулевой ширины, BOM) — строка из них не «заполнена»
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def clean_text(value, limit: int) -> str:
    """Строка без невидимых символов и лишних пробелов (общая для подписей и ответов)."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", _INVISIBLE.sub("", value)).strip()[:limit]


_s = clean_text


def overlay_locales() -> list[str]:
    """FB-33 M2i-5b: языки переводов (реестр `settings.LANGUAGES` без основного), по порядку —
    тот же набор, что `siteconfig.overlay_locales` (модуль без импорта `siteconfig`)."""
    from django.conf import settings

    return sorted({code for code, _label in settings.LANGUAGES} - {settings.LANGUAGE_CODE})


def translations(raw, base: str, limit: int) -> dict:
    """FB-33 M2i-5b: переводы одного текста `{язык: текст}` — только языки платформы, текст
    чистится как основной, пустой и равный основному не хранится (показ возьмёт основной)."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for loc in overlay_locales():
        text = clean_text(raw.get(loc), limit)
        if text and text != base:
            out[loc] = text
    return out


def normalize_questions(raw, next_id=0, temp: bool = False) -> tuple[list[dict], int]:
    """Вопросы владельца и следующий свободный номер. Мусор отбрасывается молча (это настройка,
    не ввод клиента); вопрос без подписи или выбор без вариантов — не вопрос. `temp` — черновик
    «Seitenaufbau» (FB-33 M2i-5): новые вопросы с временным id `n<k>` (номер не считают)."""
    try:
        counter = min(max(int(next_id), 0), ID_MAX)
    except (TypeError, ValueError, OverflowError):  # inf/мусор в настройке — с нуля
        counter = 0
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or len(out) >= MAX_QUESTIONS:
            continue
        match = _ID.match(str(item.get("id") or ""))
        draft_id = temp and not match and bool(TEMP_ID.match(str(item.get("id") or "")))
        label = _s(item.get("label"), LABEL_MAX)
        kind = item.get("type") if item.get("type") in TYPES else "text"
        if not (match or draft_id) or not label or item["id"] in seen:
            continue
        question = {"id": item["id"], "type": kind, "label": label}
        if kind == "choice":
            options = []
            for opt in item.get("options") if isinstance(item.get("options"), list) else []:
                text = _s(opt, LABEL_MAX)
                if text and text not in options:  # дубли вариантов схлопываются (порядок — первый)
                    options.append(text)
                if len(options) >= MAX_OPTIONS:
                    break
            if not options:
                continue
            question["options"] = options
        # FB-33 M2i-5b: переводы подписи и вариантов — по тексту варианта на основном языке
        # (не по позиции: перестановка не уводит перевод к чужому варианту)
        label_tr = translations(item.get("label_i18n"), label, LABEL_MAX)
        if label_tr:
            question["label_i18n"] = label_tr
        if kind == "choice":
            raw_opts = (
                item.get("options_i18n") if isinstance(item.get("options_i18n"), dict) else {}
            )
            opts_tr = {}
            for opt in question["options"]:
                tr = translations(raw_opts.get(opt), opt, LABEL_MAX)
                if tr:
                    opts_tr[opt] = tr
            if opts_tr:
                question["options_i18n"] = opts_tr
        if item.get("mode") == "req":
            question["mode"] = "req"
        seen.add(item["id"])
        if match:
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


def _filled_raw(post, key: str) -> str:
    raw = post.get(key, "")
    return _INVISIBLE.sub("", raw).strip() if isinstance(raw, str) else ""


def dropped(questions: list[dict], post, prefix: str = "") -> list[str]:
    """FB-33 D1: id ключей POST вида `q<n>` (ровно, `fullmatch`: `q1` ≠ `q10`, `q5\\n` — не id)
    с непустым значением, которые не легли ответом в `collect`: вопроса нет или значение
    негодно (выбор вне вариантов, битое число/дата). Порядок — по номеру."""
    answers = collect(questions, post, prefix)
    out = []
    for key in post.keys() if hasattr(post, "keys") else ():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        qid = key[len(prefix) :]
        if not (qid.isascii() and _ID.fullmatch(qid)) or qid in answers:
            continue
        if _filled_raw(post, key):
            out.append(qid)
    return sorted(set(out), key=lambda qid: int(qid[1:]))


def answers_for_deal(questions: list[dict], post, *, kind: str, next_id, prefix: str = "") -> dict:
    """FB-33 D1: снимок ответов сделки (корзина — `kind="order"`, заявка — `"job"`).

    Сверх `snapshot` (решение владельца, вариант A) хранит «осиротевшие» ответы, не больше
    `STALE_MAX`, значение — текст ≤ `LABEL_MAX * 2`:
    * ответ на вопрос, которого нет в текущем списке, — только если номер бизнес выдавал
      (`n <= next_id` писателя `form_spec`; `next_id == 0` — вопросов не было, не хранить):
      `{"label": "", "type": "text", "stale": "removed"}` — подпись из POST не берём;
    * выбор вне текущих вариантов — подпись вопроса и `"stale": "changed"`.
    Битые число и дата — ошибка ввода гостя, не правка владельца: не хранятся. Всё, что не
    легло обычным ответом, — строка INFO с id и числом, без значений (ПДн)."""
    out = snapshot(questions, collect(questions, post, prefix))
    lost = dropped(questions, post, prefix)
    if not lost:
        return out
    try:
        issued = min(max(int(next_id or 0), 0), ID_MAX)
    except (TypeError, ValueError, OverflowError):
        issued = 0
    by_id = {q["id"]: q for q in questions}
    stored = []
    for qid in lost:
        if len(stored) >= STALE_MAX:
            break
        question = by_id.get(qid)
        if question is None and int(qid[1:]) <= issued:
            label, stale = "", STALE_REMOVED
        elif question is not None and question["type"] == "choice":
            label, stale = question["label"], STALE_CHANGED
        else:
            continue
        value = clean_text(post.get(prefix + qid), LABEL_MAX * 2)
        if value:
            out[qid] = {"label": label, "value": value, "type": "text", "stale": stale}
            stored.append(qid)
    logger.info(
        "%s: answers to %d unknown/changed questions not taken as answers: %s; kept as stale: %s",
        kind,
        len(lost),
        ",".join(lost[:LOG_IDS_MAX]) + (",..." if len(lost) > LOG_IDS_MAX else ""),
        ",".join(stored) or "-",
    )
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
        if not isinstance(item, dict):
            continue
        stale = item.get("stale")
        # FB-33 D1 (ревью M1): строка удалённого вопроса — с пустой подписью; признак раньше
        # проверки подписи, подпись — при показе (язык читателя)
        if stale == STALE_REMOVED:
            label = pgettext("form answer", "Entfernte Frage")
        elif item.get("label"):
            label = str(item["label"])
        else:
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
        if stale == STALE_CHANGED:
            note = pgettext("form answer", "(nicht mehr in der Liste)")
            shown = shown + " " + note
        out.append((label, shown))
    return out
