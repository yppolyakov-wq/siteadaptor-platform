"""AIS-W W4-2: разбор строк «Name — Preis» шага мастера «Angebot prüfen» (без ИИ, без БД).

Владелец вставляет список: одна строка — одно предложение. Чистые функции: строка → `Line`
(имя, цена, длительность/гости/дата по направлению, ошибки и предупреждения). Ничего не
создаётся — создание идёт позже, после проверки таблицы (`offer_batch`).

Одна точка истины: `parse_lines` (текст) и `validate_row` (строка таблицы, присланная при
подтверждении) идут через `_build` — правила одинаковы. Суммы — только `money.parse_amount`
(свой разбор денег здесь запрещён замком)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import money

#: Виды ввода шага (ключи направлений `apps/core/directions.py`; столы — вне шага).
KINDS = ("waren", "speisekarte", "termine", "zimmer", "tickets", "anfragen")
#: Где цена обязательна и > 0.
_PAID = frozenset({"waren", "speisekarte", "termine", "zimmer"})

MAX_LINES = 50
MAX_TEXT = 8000
MAX_NAME = 120
MIN_DURATION, MAX_DURATION = 5, 600
MAX_GUESTS = 20
DEFAULT_GUESTS = 2
DEFAULT_HOUR = 19

_SPACES = re.compile(r"[    ]")
_BULLET = re.compile(r"^\s*(?:[•*·]|-(?=\s)|\d{1,2}[.)](?=\s+\D))\s*")
_LEADERS = re.compile(r"\s*\.{3,}\s*")
_SEPARATOR = re.compile(r"\s+[—–-]\s+|\t+|\s*\|\s*|\s*;\s*|:\s+")
_NAME_TRIM = " \t—–-:;|.,"

_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d+)?"
_CUR = r"(?:€|EUR|Euro|CHF)"
_PRICE = re.compile(
    rf"(?P<neg>(?<![\w.,])-)?(?:{_CUR}\s*)?(?P<num>{_NUM})(?P<dash>,[-–])?(?:\s*{_CUR})?",
    re.IGNORECASE,
)
_RANGE = re.compile(rf"(?P<a>{_NUM})\s*(?:[–-]|bis)\s*(?P<b>{_NUM})", re.IGNORECASE)
_TAIL = re.compile(
    rf"\s+(?:ab\s+)?(?:{_CUR}\s*)?(?:{_NUM})(?:,[-–])?\s*{_CUR}?\s*$",
    re.IGNORECASE,
)
_AB = re.compile(r"\bab\b", re.IGNORECASE)
_FREE = re.compile(r"\b(?:gratis|kostenlos|frei|free)\b", re.IGNORECASE)
_UNIT = re.compile(r"(?:/|\bpro\b)\s*(?:\d+\s*)?(?:kg|g|l|ml|stück|stk)\b", re.IGNORECASE)
_CHF = re.compile(r"\bCHF\b", re.IGNORECASE)

_DUR_CLOCK = re.compile(r"(?<![\d.,])(\d{1,2}):(\d{2})\s*h\b", re.IGNORECASE)
_DUR = re.compile(
    r"(?<![\d.,])(\d{1,3})(?:[.,](\d{1,2}))?\s*"
    r"(?P<unit>minuten|min\.?|stunden|stunde|std\.?|h|')(?![a-zäöü])",
    re.IGNORECASE,
)
_GUESTS = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:pers(?:onen)?\.?|gäste|gast)(?![a-zäöü])|\bfür\s+(\d{1,2})\b",
    re.IGNORECASE,
)
_DZ = re.compile(r"\bDZ\b")
_EZ = re.compile(r"\bEZ\b")
_DATE = re.compile(
    r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?"
    r"(?:\s+(\d{1,2})(?::(\d{2}))?\s*uhr|\s+(\d{1,2}):(\d{2}))?",
    re.IGNORECASE,
)


class OfferTextTooLong(ValueError):
    """Текст длиннее MAX_TEXT — форма отказывает целиком (не режем молча)."""


@dataclass(frozen=True)
class Line:
    idx: int
    raw: str
    name: str
    price: Decimal | None = None
    price_from: bool = False
    duration_min: int | None = None
    guests: int | None = None
    starts_at: datetime | None = None
    example: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class Parsed:
    lines: list[Line]
    notes: list[str] = field(default_factory=list)


def _clean(raw: str) -> str:
    s = _SPACES.sub(" ", raw).strip()
    s = _BULLET.sub("", s, count=1)
    return _LEADERS.sub(" — ", s).strip()


def _cut(text: str, match: re.Match) -> str:
    return (text[: match.start()] + " " + text[match.end() :]).strip()


def _duration(text: str) -> tuple[int | None, str]:
    m = _DUR_CLOCK.search(text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)), _cut(text, m)
    m = _DUR.search(text)
    if not m:
        return None, text
    whole, frac = int(m.group(1)), m.group(2) or ""
    unit = m.group("unit").lower()
    value = Decimal(whole) + (Decimal(int(frac)) / (10 ** len(frac)) if frac else 0)
    if unit.startswith(("std", "stunde", "h")):
        value *= 60
    return int(value), _cut(text, m)


def _guests(text: str) -> tuple[int | None, str]:
    m = _GUESTS.search(text)
    if m:
        return int(m.group(1) or m.group(2)), _cut(text, m)
    if _DZ.search(text):
        return 2, text
    if _EZ.search(text):
        return 1, text
    return None, text


def _date(text: str, today: date) -> tuple[datetime | None, str, list[str], list[str]]:
    errors, warnings = [], []
    m = _DATE.search(text)
    if not m:
        return None, text, errors, warnings
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    hour = m.group(4) or m.group(6)
    minute = m.group(5) or m.group(7) or "0"
    if hour is None:
        hour = DEFAULT_HOUR
        warnings.append(_("Keine Uhrzeit — %(hour)s:00 Uhr angenommen.") % {"hour": hour})
    try:
        clock = time(int(hour), int(minute))
        if year:
            y = int(year) + (2000 if len(year) == 2 else 0)
            day_ = date(y, month, day)
        else:
            day_ = date(today.year, month, day)
            if day_ < today:
                day_ = date(today.year + 1, month, day)
    except ValueError:
        errors.append(_("Datum ungültig."))
        return None, _cut(text, m), errors, warnings
    if day_ < today:
        errors.append(_("Datum liegt in der Vergangenheit."))
    starts = timezone.make_aware(datetime.combine(day_, clock))
    return starts, _cut(text, m), errors, warnings


def _amount(match_num: str, dash: str | None) -> Decimal:
    raw = match_num + (",00" if dash else "")
    return money.parse_amount(raw)


def _price(text: str, kind: str):
    """(цена, «ab», ошибки, предупреждения) из текста атрибутов строки."""
    errors, warnings = [], []
    price, price_from = None, bool(_AB.search(text))
    if _UNIT.search(text):
        warnings.append(_("Einheit erkannt — Grundpreis richten Sie später ein."))
    if _CHF.search(text):
        warnings.append(_("Währung CHF — gespeichert in €."))
    rng = _RANGE.search(text)
    try:
        if rng:
            price, price_from = money.parse_amount(rng.group("a")), True
            warnings.append(
                _("Preisspanne — gespeichert als „ab %(price)s €“.")
                % {"price": f"{price:.2f}".replace(".", ",", 1)}
            )
        else:
            found = list(_PRICE.finditer(text))
            if found:
                first = found[0]
                if first.group("neg"):
                    raise ValueError(first.group(0))
                price = _amount(first.group("num"), first.group("dash"))
                if len(found) > 1:
                    warnings.append(_("Zweiter Preis — später als Variante anlegen."))
            elif _FREE.search(text):
                price = Decimal("0")
    except ValueError:
        errors.append(_("Preis nicht lesbar — bitte z. B. „3,50“ schreiben."))
        return None, False, errors, warnings
    if price is None:
        if kind in _PAID or kind == "tickets":
            errors.append(_("Preis fehlt."))
    elif price == 0 and kind in _PAID:
        errors.append(_("Preis 0 € — ohne Preis tragen Sie es unter „Anfragen“ ein."))
    return price, price_from, errors, warnings


def _build(idx, raw, name, attrs, kind, today, examples) -> Line:
    """Общий конструктор: имя + текст атрибутов → Line с проверками по виду."""
    errors, warnings = [], []
    duration = guests = starts = None
    if kind == "termine":
        duration, attrs = _duration(attrs)
        if duration is None:
            errors.append(_("Dauer fehlt — ohne Dauer gibt es keine freien Termine."))
        elif not MIN_DURATION <= duration <= MAX_DURATION:
            errors.append(_("Dauer zwischen 5 Minuten und 10 Stunden angeben."))
    elif kind == "zimmer":
        guests, attrs = _guests(attrs)
        if guests is None:  # «DZ Garten» / «EZ» — сокращение стоит в самом имени
            guests = 2 if _DZ.search(name or "") else 1 if _EZ.search(name or "") else None
        if guests is None:
            guests = DEFAULT_GUESTS
            warnings.append(_("Gäste: %(n)s angenommen.") % {"n": DEFAULT_GUESTS})
        elif not 1 <= guests <= MAX_GUESTS:
            errors.append(_("Gäste zwischen 1 und 20 angeben."))
    elif kind == "tickets":
        starts, attrs, d_err, d_warn = _date(attrs, today)
        if starts is None and not d_err:
            d_err.append(_("Datum fehlt, z. B. „20.07. 19 Uhr“."))
        errors += d_err
        warnings += d_warn
    price, price_from, p_err, p_warn = _price(attrs, kind)
    errors += p_err
    warnings += p_warn
    name = (name or "").strip(_NAME_TRIM)
    if not name:
        errors.insert(0, _("Name fehlt."))
    elif len(name) > MAX_NAME:
        name = name[:MAX_NAME].rstrip()
        warnings.append(_("Name gekürzt auf 120 Zeichen."))
    return Line(
        idx=idx,
        raw=raw,
        name=name,
        price=price,
        price_from=price_from,
        duration_min=duration,
        guests=guests,
        starts_at=starts,
        example=raw.strip() in examples,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _split(line: str, kind: str) -> tuple[str, str]:
    """Строка → (имя, атрибуты). Сначала вырезаем распознанные по виду части (длительность,
    гости, дата), затем делим по разделителю; без разделителя цена берётся с хвоста."""
    parts = [p for p in _SEPARATOR.split(line) if p.strip()]
    if len(parts) > 1:
        return parts[0], " ".join(parts[1:])
    attrs = ""
    work = line
    if kind == "termine":
        _d, rest = _duration(work)
        if _d is not None:
            m = _DUR_CLOCK.search(work) or _DUR.search(work)
            attrs, work = m.group(0), rest
    tail = _TAIL.search(work)
    if tail:
        return work[: tail.start()], (attrs + " " + tail.group(0)).strip()
    return work, attrs


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown offer kind: {kind!r}")


def parse_lines(text: str, kind: str, *, examples=frozenset(), today=None) -> Parsed:
    """Текст textarea → строки с проверками. Пустые строки пропускаются; > MAX_LINES — обрезка
    с пометкой; дубль имени внутри пачки — ошибка у второй строки."""
    _check_kind(kind)
    if len(text or "") > MAX_TEXT:
        raise OfferTextTooLong(len(text))
    today = today or timezone.localdate()
    raws = [r for r in (text or "").splitlines() if r.strip()]
    notes = []
    if len(raws) > MAX_LINES:
        notes.append(
            _("Nur die ersten %(n)s Zeilen werden geprüft — den Rest danach.") % {"n": MAX_LINES}
        )
        raws = raws[:MAX_LINES]
    lines, seen = [], set()
    for idx, raw in enumerate(raws):
        cleaned = _clean(raw)
        name, attrs = _split(cleaned, kind)
        line = _build(idx, raw, name, attrs, kind, today, examples)
        key = line.name.casefold()
        if key and key in seen:
            line = replace(line, errors=(*line.errors, _("Doppelt in der Liste.")))
        seen.add(key)
        lines.append(line)
    return Parsed(lines=lines, notes=notes)


def validate_row(data: dict, kind: str, *, idx: int = 0, today=None) -> Line:
    """Строка таблицы «Prüfen» (поля из POST) → Line теми же правилами, что `parse_lines`.

    Имя берётся как есть: разделители внутри — часть имени."""
    _check_kind(kind)
    today = today or timezone.localdate()
    values = {f: str(data.get(f) or "").strip()[:200] for f in ("duration", "guests", "starts_at")}
    # Таблица присылает голые числа («45», «2») — дописываем единицу, как в строке.
    if values["duration"].isdigit():
        values["duration"] += " Min"
    if values["guests"].isdigit():
        values["guests"] += " Pers."
    values["price"] = str(data.get("price") or "").strip()[:200]
    attrs = " ".join(v for v in values.values() if v)
    name = _SPACES.sub(" ", str(data.get("name") or ""))[: MAX_NAME * 2]
    return _build(idx, name, name, attrs, kind, today, frozenset())
