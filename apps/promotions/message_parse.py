"""T-8.10b B-1: разбор сообщения владельца в Telegram → поля быстрой акции (без ИИ).

План — docs/t8-10b-telegram-promo-plan-2026-10-19.md §3. Чистые функции, без БД.
Каждое правило «съедает» свой фрагмент текста, следующие его уже не видят: так «4 Käse»
не станет количеством, а дата — ценой. Ничего не публикуется без превью: владелец видит
разобранное и подтверждает кнопкой. Числа приходят ТОЛЬКО отсюда (ИИ их не трогает).

Языки ключевых слов — объединением (de/en/ru/uk/tr): язык владельца заранее неизвестен.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

TITLE_MAX = 80
DESCRIPTION_MAX = 280
TEXT_MAX = 1000
QTY_MAX = 10_000
DAYS_MAX = 60

TERM_TODAY = "today"
TERM_WEEKEND = "weekend"
TERM_WEEK = "week"
TERM_DATE = "date"

_MONEY = r"\d{1,5}(?:[.,]\d{1,2})?"
_CUR = r"(?:€|eur\b|euro\b|,-|tl\b|₺)"
_UNTIL = r"(?:bis(?:\s+zum|\s+um)?|до|until|till)"

_RE_DATE_MARKED = re.compile(
    rf"(?i)\b{_UNTIL}\s+(\d{{1,2}})\.(\d{{1,2}})\.?(\d{{4}}|\d{{2}})?(?![\d,])"
)
_RE_DATE_DOT = re.compile(r"(?<![\d.,])(\d{1,2})\.(\d{1,2})\.(\d{4})?(?![\d,])")
_RE_TIME = re.compile(
    rf"(?i)(?:\b{_UNTIL}\s+|\bsaat\s+)(\d{{1,2}})(?:[:.](\d{{2}}))?\s*"
    r"(uhr\b|h\b|am\b|pm\b|'?[ea]\s+kadar\b)?"
)
_RE_TIME_AMPM = re.compile(r"(?i)\b(\d{1,2})\s*(am|pm)\b")
# «bis Sonntag 18 Uhr»: после дня недели «bis» уже съеден — голое «18 Uhr».
_RE_TIME_UHR = re.compile(r"(?i)(?<![\d.,])(\d{1,2})(?:[:.](?P<min>\d{2}))?\s*uhr\b")

_WEEKDAYS = {
    0: ("montag", "monday", "понедельник", "понедельника", "понеділка", "pazartesi"),
    1: ("dienstag", "tuesday", "вторник", "вторника", "вівторка", "salı"),
    2: ("mittwoch", "wednesday", "среда", "среды", "середи", "çarşamba"),
    3: ("donnerstag", "thursday", "четверг", "четверга", "четверга", "perşembe"),
    4: ("freitag", "friday", "пятница", "пятницы", "пʼятниці", "cuma"),
    5: ("samstag", "saturday", "суббота", "субботы", "суботи", "cumartesi"),
    6: ("sonntag", "sunday", "воскресенье", "воскресенья", "неділі", "pazar"),
}
_RE_WEEKDAY = re.compile(
    rf"(?i)\b{_UNTIL}\s+(?:zum\s+)?("
    + "|".join(sorted({w for names in _WEEKDAYS.values() for w in names}, key=len, reverse=True))
    + r")\b"
)
_RE_TODAY = re.compile(
    r"(?i)\b(?:nur\s+)?(?:heute|bis\s+ladenschluss|ladenschluss|сегодня|сьогодні|today|tonight|bugün)\b"
)
_RE_TOMORROW = re.compile(r"(?i)\b(?:morgen|завтра|tomorrow|yarın)\b")
_RE_WEEKEND = re.compile(
    r"(?i)\b(?:(?:am|übers|ubers)\s+)?(?:wochenende|weekend|выходные|вихідні|hafta\s+sonu)\b"
    r"|\bsa\s*\+\s*so\b"
)
_RE_DAYS = re.compile(r"(?i)\b(\d{1,2})\s*(?:tage|tagen|days|дней|дня|днів|gün)\b")
_RE_WEEK = re.compile(
    r"(?i)\b(?:eine|1|one|a)\s+(?:woche|week)\b|\bнеделю\b|\bтиждень\b|\bbir\s+hafta\b"
)

_RE_CONDITION = re.compile(
    r"(?i)\b\d\s?(?:für|for|за)\s?\d\b|\b\d\s?\+\s?\d\b|\b2\.\s?(?:stück|artikel)\b"
)
_RE_PERCENT = re.compile(
    r"(?i)(?<![\d])[−\-–]?\s?(\d{1,3})\s?(?:%|％|prozent\b|percent\b|процент\w*|відсот\w*)"
    r"(?:\s?(?:off|rabatt|indirim|скидк\w*|знижк\w*))?"
    r"|%\s?(\d{1,3})(?:\s?indirim)?"
    r"|(?<![\d])(\d{1,2})\s?off\b"
)
_RE_QTY = re.compile(
    r"(?i)(?<![\d.,])(\d{1,5})\s?(?:stück\b|stk\.?|st\.|x(?![\w-])|portionen\b|tüten\b|pcs\b|"
    r"шт\.?|штук\w*|штуки\b|adet\b)"
    r"|\bnur\s+noch\s+(\d{1,5})\b|\bnoch\s+(\d{1,5})\s+da\b|\bосталось\s+(\d{1,5})\b"
    r"|\bзалишилось\s+(\d{1,5})\b"
)
_OLD_MARK = r"(?:statt(?:\s+nur)?|vorher|uvp|alt|вместо|было|замість|instead\s+of|was)"
_NEW_MARK = r"(?:für|nur|jetzt|ab|за|только|лише|всего|for|only|now|sadece)"
_RE_OLD = re.compile(
    rf"(?i)\b{_OLD_MARK}\s*:?\s*(?:{_CUR}\s?)?({_MONEY})\s?{_CUR}?"
    rf"|({_MONEY})\s?{_CUR}?\s+yerine\b"
)
_RE_NEW_MARKED = re.compile(rf"(?i)\b{_NEW_MARK}\s*:?\s*(?:{_CUR}\s?)?({_MONEY})\s?{_CUR}")
_RE_PRICE_CUR = re.compile(
    rf"(?i)(?<![\d.,])({_MONEY})\s?{_CUR}|(?:€|eur\b|euro\b)\s?({_MONEY})(?![\d])"
)
# «Wein 0,75 l» — объём/вес, не цена.
_RE_PLAIN_DECIMAL = re.compile(
    r"(?i)(?<![\d.,])(\d{1,5}[.,]\d{2})(?![\d])(?!\s?(?:l|ml|cl|kg|g|cm|m|liter)\b)"
)
# «3 Euro 50» = 3,50 €.
_RE_EURO_CENT = re.compile(r"(?i)(?<![\d.,])(\d{1,5})\s?(?:€|euro\b|eur\b)\s?(\d{2})\b")
_RE_ARROW = re.compile(rf"({_MONEY})\s?{_CUR}?\s*(?:→|->|=>|/)\s*({_MONEY})\s?{_CUR}?")

_DANGLING = {
    "bis",
    "ab",
    "für",
    "nur",
    "statt",
    "je",
    "à",
    "heute",
    "jetzt",
    "noch",
    "до",
    "за",
    "по",
    "только",
    "only",
    "for",
    "until",
    "now",
    "am",
    "um",
    "zum",
    "und",
    "mit",
    "и",
    "rabatt",
    "off",
    "скидка",
    "indirim",
}


@dataclass(frozen=True)
class Parsed:
    title: str = ""
    description: str = ""
    new_price: Decimal | None = None
    old_price: Decimal | None = None
    percent: int | None = None
    quantity: int | None = None
    term: str = ""  # "" = срок не назван (вызывающий подставит default_term)
    until: date | None = None
    until_time: time | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def signals(self) -> bool:
        """Есть ли в сообщении хоть что-то про акцию (цена, скидка, срок, количество)."""
        return any(
            v is not None for v in (self.new_price, self.old_price, self.percent, self.quantity)
        ) or bool(self.term)


def _money(raw) -> Decimal | None:
    text = str(raw or "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value <= 0 or value >= Decimal("100000"):
        return None
    return value.quantize(Decimal("0.01"))


class _Text:
    """Текст, из которого правила «съедают» фрагменты (заменяя их пробелами)."""

    def __init__(self, text: str):
        self.text = text

    def take(self, regex):
        out = []
        while True:
            m = regex.search(self.text)
            if not m:
                return out
            out.append(m)
            self.text = self.text[: m.start()] + " " * (m.end() - m.start()) + self.text[m.end() :]

    def take_one(self, regex):
        m = regex.search(self.text)
        if m:
            self.text = self.text[: m.start()] + " " * (m.end() - m.start()) + self.text[m.end() :]
        return m


def _date(day: int, month: int, year, today: date, warnings: list) -> date | None:
    try:
        y = int(year) if year else today.year
        if y < 100:
            y += 2000
        value = date(y, month, day)
    except (TypeError, ValueError):
        warnings.append("date_invalid")
        return None
    if not year and value < today:
        try:
            value = date(today.year + 1, month, day)
        except ValueError:
            return None
        warnings.append("date_rolled")
    if value < today:
        warnings.append("date_past")
        return None
    return value


def _clean_title(text: str) -> str:
    words = [w for w in re.split(r"\s+", text) if w]
    stripped = [w.strip(",;:!?.-–—|·") for w in words]
    words = [w for w in stripped if w]
    while words and words[-1].casefold() in _DANGLING:
        words.pop()
    while words and words[0].casefold() in _DANGLING:
        words.pop(0)
    title = " ".join(words)
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX].rsplit(" ", 1)[0]
    return title.strip()


def parse(text: str, *, now=None) -> Parsed:
    """Сообщение → `Parsed`. Ничего не бросает; мусор даёт пустые поля."""
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    raw = (text or "")[:TEXT_MAX]
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    first = lines[0] if lines else ""
    rest = "\n".join(lines[1:])
    t = _Text(first)
    warnings: list[str] = []
    term, until, until_time = "", None, None

    # 1. Дата
    m = t.take_one(_RE_DATE_MARKED) or t.take_one(_RE_DATE_DOT)
    if m:
        until = _date(int(m.group(1)), int(m.group(2)), m.group(3), today, warnings)
        if until:
            term = TERM_DATE

    # 2. Относительный срок (до времени: «morgen bis 18 Uhr» — время относится к ЭТОМУ дню)
    if not term:
        if t.take_one(_RE_WEEKEND):
            term = TERM_WEEKEND
        elif t.take_one(_RE_TOMORROW):
            term, until = TERM_DATE, today + timedelta(days=1)
        elif m := t.take_one(_RE_WEEKDAY):
            word = m.group(1).casefold()
            wd = next(d for d, names in _WEEKDAYS.items() if word in names)
            term, until = TERM_DATE, today + timedelta(days=(wd - today.weekday()) % 7)
        elif m := t.take_one(_RE_DAYS):
            n = int(m.group(1))
            if 1 <= n <= DAYS_MAX:
                term, until = TERM_DATE, today + timedelta(days=n)
        elif t.take_one(_RE_WEEK):
            term = TERM_WEEK
        elif t.take_one(_RE_TODAY):
            term = TERM_TODAY
    t.take(_RE_TODAY)  # «heute bis 18 Uhr» — слово «heute» не в заголовок

    # 3. Время: только с «Uhr»/двоеточием/am-pm — «bis 18» без них может быть ценой.
    hour = minute = None
    m = _RE_TIME.search(t.text)
    if m and (m.group(2) or m.group(3)):
        t.take_one(re.compile(re.escape(m.group(0))))
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        suffix = (m.group(3) or "").lower()
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
    if hour is None:
        m = t.take_one(_RE_TIME_AMPM) or t.take_one(_RE_TIME_UHR)
        if m:
            hour, minute = int(m.group(1)), int(m.groupdict().get("min") or 0)
            if m.re is _RE_TIME_AMPM and m.group(2).lower() == "pm" and hour < 12:
                hour += 12
    if hour is not None:
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            warnings.append("time_invalid")
        elif term in (TERM_WEEKEND, TERM_WEEK):
            warnings.append("time_ignored")  # конец периода — не время дня
        else:
            until_time = time(hour, minute)
            day = until or today
            if datetime.combine(day, until_time) <= now.replace(tzinfo=None):
                warnings.append("time_past")
                until_time = None
            elif not term:
                term = TERM_TODAY

    # 4. Условие цены — не разбираем, только предупреждаем
    if t.take(_RE_CONDITION):
        warnings.append("price_condition")

    # 5. Процент
    percent = None
    for m in t.take(_RE_PERCENT):
        value = int(next(g for g in m.groups() if g))
        if 1 <= value <= 99:
            percent = percent or value
        else:
            warnings.append("percent_invalid")

    # 6. Количество
    quantity = None
    for m in t.take(_RE_QTY):
        value = int(next(g for g in m.groups() if g))
        if 1 <= value <= QTY_MAX and quantity is None:
            quantity = value

    # 7. Цены
    old = new = None
    if m := t.take_one(_RE_ARROW):
        a, b = _money(m.group(1)), _money(m.group(2))
        if a and b:
            old, new = max(a, b), min(a, b)
    for m in t.take(_RE_OLD):
        old = old or _money(m.group(1) or m.group(2))
    for m in t.take(_RE_NEW_MARKED):
        new = new or _money(m.group(1))
    bare = [_money(f"{m.group(1)}.{m.group(2)}") for m in t.take(_RE_EURO_CENT)]
    bare += [_money(m.group(1) or m.group(2)) for m in t.take(_RE_PRICE_CUR)]
    bare = [v for v in bare if v]
    if new is None and not bare:
        bare = [v for v in (_money(m.group(1)) for m in t.take(_RE_PLAIN_DECIMAL)) if v]
    if bare:
        if new is None and old is None and len(bare) >= 2:
            new, old = min(bare), max(bare)
        elif new is None:
            new = bare[0]
        elif old is None:
            old = bare[0]

    # 8. Согласование
    if new is not None and percent is not None:
        warnings.append("price_and_percent")
        percent = None
    if old is not None and new is not None and old <= new:
        warnings.append("old_not_higher")
        old = None

    title = _clean_title(t.text)
    description = " ".join(rest.split())[:DESCRIPTION_MAX].strip()
    return Parsed(
        title=title,
        description=description,
        new_price=new,
        old_price=old,
        percent=percent,
        quantity=quantity,
        term=term,
        until=until,
        until_time=until_time,
        warnings=tuple(dict.fromkeys(warnings)),
    )
