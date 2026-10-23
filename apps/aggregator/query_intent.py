"""T-8.26 п.5a: разбор намерения запроса — правила без БД.

Житель пишет «Winterjacke unter 100 Euro», «Restaurant heute geöffnet», «Friseur in
Solingen-Wald»; движок умеет это как GET-фильтры (`preis_bis`, `offen`, `datum`,
`stadtteil`), но текст разбирать не умел — аудит §7.2. Здесь фразы с надёжной формой
переводятся в фильтры, вырезаются из запроса и показываются пилюлями «Erkannt: …» с ✕.

Честность (план Р-3/Р-4): явный GET сильнее вывода; выведенное НЕ прилипает к форме (в
форме остаётся сырой `q`, вывод повторяется детерминированно); ✕ у цены/времени/offen =
запрос без фразы, ✕ у района = `roh=ort` (слово остаётся текстом). Вид бизнеса
(«Restaurant», «Friseur») НЕ выводим — это работа полнотекста. Признаки (vegetarisch…)
— только подсказка-ссылка, данных с признаками мало. Без ML/LLM (ИИ-поиск — T-8.10d).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from apps.core import city_categories as cc
from apps.core import districts

# ключ пилюли = имя GET-параметра, который она представляет (кроме groesse — v1 без фильтра)
KEY_PRICE_TO, KEY_PRICE_FROM, KEY_DATE, KEY_OPEN, KEY_DISTRICT, KEY_SIZE = (
    "preis_bis",
    "preis_von",
    "datum",
    "offen",
    "stadtteil",
    "groesse",
)
ROH_ORT = "ort"  # ?roh=ort — «район — просто слово»
HINTS_MAX = 3  # подсказок признаков на запрос (каждая — один .exists())

# число: «100», «12,50», «1.000» (тысячи точкой) — без хвоста «:30»/«.30» (время)
_NUM = r"(\d{1,3}(?:\.\d{3})+|\d{1,5}(?:,\d{1,2})?)(?![.:,]\d)"
_CUR = r"(?:€|euro|eur)"
# не цена: время, доли, счётчики, расстояния, возраст, рейтинг
_NOT_UNIT = (
    r"(?!\s*(?:uhr|h\b|%|personen|pers\.?|teilnehmer|stück|stk\.?|kg|g\b|cm|mm|km|m\b|"
    r"tage?n?|jahren?|sterne?|min\.?|minuten|std\.?|stunden|plätze?|gäste))"
)
_RE_OPEN = re.compile(
    r"\b(?:(?:jetzt|heute|gerade)\s+)?(?:geöffnet|geoeffnet|offen)(?:\s+(?:heute|jetzt))?\b"
    r"|\bhat\s+offen\b"
    # «Pizza morgen» на портале пишут и на языке посетителя (ru/uk/en/tr)
    r"|\bopen\s+now\b|\bnow\s+open\b"
    r"|\b(?:сейчас\s+)?открыт[оаы]?(?:\s+сейчас)?\b"
    r"|\b(?:зараз\s+)?відчинен[оаі]?(?:\s+зараз)?\b|\b(?:зараз\s+)?відкрит[оаі]?(?:\s+зараз)?\b"
    r"|\b(?:şimdi\s+)?açık(?:\s+şimdi)?\b",
    re.I,
)
_RE_RANGE = re.compile(rf"\b{_NUM}\s*(?:-|–|bis)\s*{_NUM}\s*{_CUR}", re.I)
# «unter N» — валюта необязательна (но не единица); «bis/max/höchstens N» — ТОЛЬКО с валютой
# (иначе «für 2 bis 4», «bis 18:30», «max 10 Teilnehmer» становились ценой)
_RE_TO = re.compile(
    rf"\bunter\s+{_NUM}{_NOT_UNIT}\s*{_CUR}?(?!\w)"
    rf"|\b(?:bis|max(?:imal)?|höchstens|hoechstens)\s+{_NUM}\s*{_CUR}(?!\w)",
    re.I,
)
_RE_FROM = re.compile(rf"\b(?:ab|von|mindestens)\s+{_NUM}\s*{_CUR}(?!\w)", re.I)
_RE_HEUTE = re.compile(r"\b(?:heute|today|сегодня|сьогодні|bugün)\b", re.I)
_RE_MORGEN = re.compile(r"\b(?:morgen|tomorrow|завтра|yarın|yarin)\b", re.I)
_RE_WE = re.compile(
    r"\b(?:(?:am|dieses|übers|uebers)\s+)?wochenende\b"
    r"|\b(?:(?:this|on\s+the|at\s+the)\s+)?weekend\b"
    r"|\b(?:на\s+|в\s+)?выходны[хе]\b|\b(?:на\s+|у\s+)?вихідн(?:их|і)\b"
    r"|\bhafta\s*sonu(?:nda)?\b",
    re.I,
)
#: Дни недели на языках портала → немецкий ключ _WEEKDAYS.
_WEEKDAY_ALIASES = {
    "monday": "montag",
    "tuesday": "dienstag",
    "wednesday": "mittwoch",
    "thursday": "donnerstag",
    "friday": "freitag",
    "saturday": "samstag",
    "sunday": "sonntag",
    "понедельник": "montag",
    "вторник": "dienstag",
    "среду": "mittwoch",
    "среда": "mittwoch",
    "четверг": "donnerstag",
    "пятницу": "freitag",
    "пятница": "freitag",
    "субботу": "samstag",
    "суббота": "samstag",
    "воскресенье": "sonntag",
    "понеділок": "montag",
    "вівторок": "dienstag",
    "середу": "mittwoch",
    "середа": "mittwoch",
    "четвер": "donnerstag",
    "пʼятницю": "freitag",
    "п'ятницю": "freitag",
    "пʼятниця": "freitag",
    "суботу": "samstag",
    "субота": "samstag",
    "неділю": "sonntag",
    "неділя": "sonntag",
    "pazartesi": "montag",
    "salı": "dienstag",
    "çarşamba": "mittwoch",
    "perşembe": "donnerstag",
    "cuma": "freitag",
    "cumartesi": "samstag",
    "pazar günü": "sonntag",
}
_WEEKDAYS = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")
_RE_WEEKDAY = re.compile(
    r"\b(?:am\s+|on\s+|в\s+|во\s+|у\s+)?("
    r"montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonnabend|sonntag|"
    + "|".join(sorted((re.escape(k) for k in _WEEKDAY_ALIASES), key=len, reverse=True))
    + r")\b",
    re.I,
)
_RE_SIZE = re.compile(
    r"\b(?:größe|groesse|grösse|gr\.?)\s*(xxs|xs|s|m|l|xl|xxl|xxxl|[0-9]{2,3})\b", re.I
)
# районы: голые многозначные слова («Wald», «Burg», «Mitte») одним словом не трогаем
_AMBIGUOUS = frozenset({"wald", "burg", "mitte"})
_TAG_SYNONYMS = {
    "veggie": "vegetarisch",
    "vegetarian": "vegetarisch",
    "fleischlos": "vegetarisch",
    "pflanzlich": "vegan",
    "plantbased": "vegan",
}


@dataclass(frozen=True)
class Chip:
    key: str  # имя параметра (preis_bis | preis_von | datum | offen | stadtteil | groesse)
    label: str  # «bis 100 €», «Am Wochenende», «Stadtteil Wald»
    phrase: str  # что вырезано из запроса (как написал житель)
    q_without: str  # запрос без этой фразы (✕ для всех ключей, кроме района)
    value: str = ""  # нормализованное значение (для GET/журнала)


@dataclass(frozen=True)
class Intent:
    rest_q: str
    delta: dict = field(default_factory=dict)  # поля SearchFilters, выведенные из текста
    chips: tuple[Chip, ...] = ()
    hints: tuple[str, ...] = ()  # ключи признаков (подсказка-ссылка, не фильтр)


def _fmt(value: Decimal) -> str:
    """100 → «100», 12.50 → «12,50» (Decimal.normalize дал бы 1E+2)."""
    from django.utils.formats import number_format

    text = f"{value:f}"
    digits = text.split(".")[1].rstrip("0") if "." in text else ""
    return number_format(value, len(digits))


def _grp(m) -> str:
    """Первая непустая группа (у _RE_TO две альтернативы, каждая со своим числом)."""
    return next((g for g in m.groups() if g), "")


def _money(raw: str) -> Decimal | None:
    """«1.000» → 1000 (тысячи точкой), «12,50» → 12.50."""
    try:
        text = raw.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw) else raw
        return Decimal(text.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _cut(text: str, span: tuple[int, int]) -> str:
    return _squash(text[: span[0]] + " " + text[span[1] :])


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;-–")


def _next_weekday(today: date, name: str) -> date:
    name = _WEEKDAY_ALIASES.get(name, name)
    idx = _WEEKDAYS.index("samstag" if name == "sonnabend" else name)
    return today + timedelta(days=(idx - today.weekday()) % 7)


def _district(text: str, city: str) -> tuple[str, tuple[int, int]] | None:
    """Надёжные формы района: «<город>-<район>», «in <район>», однозначное имя/алиас."""
    if not city or not districts.city_key(city):
        return None
    ck = districts.city_key(city)
    # «Solingen-Wald», «in Solingen-Wald»
    m = re.search(rf"\b(?:in\s+)?{re.escape(ck)}-([^\W\d_]+(?:/[^\W\d_]+)?)", text, re.I)
    if m and districts.normalize(city, m.group(1)):
        return districts.normalize(city, m.group(1)), m.span()
    # «in Wald», «in Gräfrath» — каждое «in X», не только первое («Jacke in Blau in Wald»)
    for m in re.finditer(r"\bin\s+([^\W\d_]+(?:[/-][^\W\d_]+)?)\b", text, re.I):
        if districts.normalize(city, m.group(1)):
            return districts.normalize(city, m.group(1)), m.span()
    # однозначное имя/алиас одним словом («Ohligs», «Höhscheid»), многозначные — нет
    for m in re.finditer(r"[^\W\d_]+", text):
        word = m.group(0)
        if word.casefold() in _AMBIGUOUS:
            continue
        slug = districts.normalize(city, word)
        if slug:
            return slug, m.span()
    return None


def parse(q: str, *, city: str = "", today: date | None = None, roh=frozenset()) -> Intent:
    """Чистый разбор: ничего не читает из БД. Порядок правил — «открыто» ДО времени
    («heute geöffnet» — не дата), потом цена, время, размер, район, подсказки признаков."""
    text = (q or "").strip()
    if not text:
        return Intent(rest_q="")
    today = today or timezone.localdate()
    delta: dict = {}
    chips: list[Chip] = []
    roh = frozenset(roh or ())

    def take(key, label, value, span, **fields):
        nonlocal text
        phrase = text[span[0] : span[1]].strip()
        delta.update(fields)
        chips.append(
            Chip(
                key,
                label,
                phrase,
                _cut(q_without_track[0], _find(q_without_track[0], phrase)),
                str(value),
            )
        )
        text = _cut(text, span)

    # ✕-пилюля вырезает ТОЛЬКО свою фразу из СЫРОГО запроса — ведём его отдельно
    q_without_track = [text]

    def _find(src, phrase):
        i = src.lower().find(phrase.lower())
        return (i, i + len(phrase)) if i >= 0 else (0, 0)

    m = _RE_OPEN.search(text)
    if m:
        take(KEY_OPEN, _("Jetzt geöffnet"), "1", m.span(), open_now=True)

    m = _RE_RANGE.search(text)
    if m:
        lo, hi = _money(m.group(1)), _money(m.group(2))
        if lo is not None and hi is not None and lo <= hi:
            delta.update(price_from=lo, price_to=hi)
            phrase = text[m.start() : m.end()].strip()
            chips.append(
                Chip(
                    KEY_PRICE_TO,
                    _("%(a)s – %(b)s €") % {"a": _fmt(lo), "b": _fmt(hi)},
                    phrase,
                    _cut(q_without_track[0], _find(q_without_track[0], phrase)),
                    str(hi),
                )
            )
            text = _cut(text, m.span())
    if "price_to" not in delta:
        m = _RE_TO.search(text)
        if m and (val := _money(_grp(m))) is not None:
            take(KEY_PRICE_TO, _("bis %(p)s €") % {"p": _fmt(val)}, val, m.span(), price_to=val)
    if "price_from" not in delta:
        m = _RE_FROM.search(text)
        if m and (val := _money(m.group(1))) is not None:
            take(
                KEY_PRICE_FROM,
                _("ab %(p)s €") % {"p": _fmt(val)},
                val,
                m.span(),
                price_from=val,
            )

    m = _RE_WE.search(text)
    if m:
        take(KEY_DATE, _("Am Wochenende"), "wochenende", m.span(), date="wochenende")
    elif (m := _RE_HEUTE.search(text)) is not None:
        take(KEY_DATE, _("Heute"), "heute", m.span(), date="heute")
    elif (m := _RE_MORGEN.search(text)) is not None:
        d = today + timedelta(days=1)
        take(KEY_DATE, _("Morgen"), d.isoformat(), m.span(), date=d.isoformat())
    elif (m := _RE_WEEKDAY.search(text)) is not None:
        d = _next_weekday(today, m.group(1).lower())
        take(KEY_DATE, date_format(d, "D, j.n."), d.isoformat(), m.span(), date=d.isoformat())

    m = _RE_SIZE.search(text)
    if m:
        size = m.group(1).upper()
        take(KEY_SIZE, _("Größe %(s)s") % {"s": size}, size, m.span(), size=size)

    if ROH_ORT not in roh:
        found = _district(text, city)
        if found:
            slug, span = found
            take(
                KEY_DISTRICT,
                _("Stadtteil %(d)s") % {"d": districts.label(city, slug) or slug},
                slug,
                span,
                district=slug,
            )

    tag_keys = {k for k, _l in cc.TAGS}
    hints = []
    for word in re.findall(r"[^\W\d_]+", text.lower()):
        stem = re.sub(r"(e|es|er|en|em)$", "", word)
        key = _TAG_SYNONYMS.get(word) or (
            word if word in tag_keys else stem if stem in tag_keys else ""
        )
        if key and key not in hints:
            hints.append(key)

    return Intent(rest_q=_squash(text), delta=delta, chips=tuple(chips), hints=tuple(hints))


def apply(intent: Intent, explicit):
    """Наложить вывод на ЯВНЫЕ фильтры: явный GET сильнее (пилюля такого вывода не
    показывается — житель уже выбрал сам). → (q_eff, filters_eff, chips)."""
    eff = explicit
    chips = []
    overridden = set()
    delta = dict(intent.delta)
    # диапазон цен — одно решение: явная ЛЮБАЯ граница снимает вывод обеих (иначе
    # невидимый «von 50 bis 30» без пилюли)
    if "price_from" in delta and "price_to" in delta:
        if _is_set(explicit.price_from) or _is_set(explicit.price_to):
            overridden.update({"price_from", "price_to"})
            delta.pop("price_from"), delta.pop("price_to")
    for name, value in delta.items():
        if _is_set(getattr(explicit, name)):
            overridden.add(name)
            continue
        eff = replace(eff, **{name: value})
    for c in intent.chips:
        if c.key == KEY_PRICE_TO and ("price_to" in overridden or "price_from" in overridden):
            continue
        if c.key == KEY_PRICE_FROM and "price_from" in overridden:
            continue
        if c.key == KEY_DATE and "date" in overridden:
            continue
        if c.key == KEY_OPEN and "open_now" in overridden:
            continue
        if c.key == KEY_DISTRICT and "district" in overridden:
            continue
        if c.key == KEY_SIZE and "size" in overridden:
            continue
        chips.append(c)
    return intent.rest_q, eff, tuple(chips)


def _is_set(value) -> bool:
    if value is None or value is False:
        return False
    return value != "" and value != ()  # Decimal(0) — задано (0 == False — ловушка)


def auto_keys(chips) -> str:
    """Для журнала поиска: какие фильтры выведены из текста («datum,preis»)."""
    names = sorted({"preis" if c.key.startswith("preis") else c.key for c in chips})
    return ",".join(names)
