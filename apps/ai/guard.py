"""Общие проверки текста от ИИ: ссылки, контакты, деньги, проценты, числа, язык.

Вынесено из `apps/inbox/ai_reply.py` (T-8.10g) без изменений поведения — им пользуются
черновик ответа клиенту и ИИ-ответ помощника кабинета (AIS A-2). Правило обоих потребителей:
текст с тем, чего нет в доверенном источнике, отбрасывается целиком, а не «чинится»."""

from __future__ import annotations

import re
from decimal import Decimal

from apps.core import text_check as tc

PII_MARKERS = ("‹email›", "‹nummer›", "‹iban›")
_INVISIBLE_OK = "\n"
DOT_LOOKALIKES = str.maketrans({"。": ".", "．": ".", "｡": ".", "٫": "."})
DOMAIN_RE = re.compile(r"(?<![\w@])(?:[\w-]+\.)+[^\W\d_]{2,}(?![\w-])(?:/\S*)?")
OBFUSCATED_LINK_RE = re.compile(
    r"(?i)hxxps?|https?:|\[\s*(?:\.|dot|punkt)\s*\]|\(\s*(?:\.|dot|punkt)\s*\)"
    r"|\b(?:dot|punkt|точка)\b\s*(?:de|com|net|org|eu|ru|ua|tr|me|io)\b|\]\("
)
HANDLE_RE = re.compile(r"(?<![\w.])@[\w.]{2,}")
IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
PHONE_RE = re.compile(r"\+?\d[\d\s./()\-]{5,}\d")
NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,:]\d+)*")
RANGE_RE = re.compile(r"\d+(?:[.:,]\d+)?\.?\s*[-–—]\s*\d+(?:[.:,]\d+)?")
PERCENT_EXTRA_RE = re.compile(
    r"(?i)(?<![\w.,])(\d+(?:[.,]\d+)?)\s?(?:percent|per\s?cent|процент\w*|відсот\w*)"
    r"|(?:%|yüzde)\s?(\d+(?:[.,]\d+)?)"
)
NUMBER_WORDS = (
    "null|ein|eine|einen|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf"
    "|zwanzig|dreißig|vierzig|fünfzig|hundert|tausend|one|two|three|four|five|six|seven"
    "|eight|nine|ten|eleven|twelve|twenty|thirty|fifty|hundred|thousand|один|одна|два|две"
    "|три|четыре|пять|шесть|десять|двадцать|пятьдесят|сто|тысяча|тысячи|дві|п'ять|bir|iki"
    "|üç|beş|yirmi|elli|yüz"
)
SPELLED_AMOUNT_RE = re.compile(
    r"(?i)(?<!\w)(?:" + NUMBER_WORDS + r")(?!\w)\s+(?:\w+\s+)?"
    r"(?:euro|€|cent|prozent|percent|процент\w*|відсот\w*|евро|євро|uhr|o'clock|lira)(?!\w)"
)
# Деньги в валютах, которых нет в text_check.MONEY_RE (ответ на языке клиента).
EXTRA_MONEY_RE = re.compile(r"(?i)(?<![\w.,])(\d+(?:[.,]\d+)?)\s?(?:евро|євро|tl|lira)(?!\w)")


CYRILLIC_RE = re.compile(r"[а-яёіїєґ]", re.IGNORECASE)
LETTER_RE = re.compile(r"[^\W\d_]")


def normalize(text: str) -> str:
    """NFKC + раскрытые HTML-сущности + без невидимых (Cf/Cc) символов."""
    import html
    import unicodedata

    text = unicodedata.normalize("NFKC", html.unescape(str(text or "")))
    text = "".join(
        c for c in text if c in _INVISIBLE_OK or unicodedata.category(c) not in ("Cf", "Cc")
    )
    return text.translate(DOT_LOOKALIKES)


def _num_token(token: str) -> str:
    """«19.10.» → «19.10»; «07:00» → «7:00»; «18:00» → тот же токен."""
    token = token.strip(".,")
    if ":" in token:
        hour, _, rest = token.partition(":")
        token = f"{int(hour)}:{rest}" if hour.isdigit() else token
    return token


def _tokens(text: str) -> set[str]:
    out = set()
    for raw in NUMBER_TOKEN_RE.findall(text or ""):
        token = _num_token(raw)
        out.add(token)
        if ":" in token and token.endswith(":00"):
            out.add(token[:-3])  # «18:00» разрешает «18 Uhr»
    return out


def _range_key(raw: str) -> str:
    left, right = re.split(r"\s*[-–—]\s*", raw.strip(), maxsplit=1)
    return f"{_num_token(left).removesuffix(':00')}-{_num_token(right).removesuffix(':00')}"


def _ranges(text: str) -> set[str]:
    return {_range_key(m.group(0)) for m in RANGE_RE.finditer(text or "")}


def _money(text: str) -> set[Decimal]:
    out = set()
    for regex in (tc.MONEY_RE, EXTRA_MONEY_RE):
        for m in regex.finditer(text or ""):
            raw = next((g for g in m.groups() if g), "")
            value = tc.to_decimal(raw)
            if value is not None:
                out.add(value)
    return out


def _percents(text: str) -> set[Decimal]:
    out = set()
    for regex in (tc.PERCENT_RE, PERCENT_EXTRA_RE):
        for m in regex.finditer(text or ""):
            raw = next((g for g in m.groups() if g), "")
            value = tc.to_decimal(raw)
            if value is not None:
                out.add(value)
    return out


def _words(text: str) -> set[str]:
    return {w.casefold() for w in re.findall(r"[\w-]+", text or "")}


def _cyrillic_share(text: str) -> float | None:
    letters = LETTER_RE.findall(text or "")
    if len(letters) < 10:
        return None
    return len([c for c in letters if CYRILLIC_RE.match(c)]) / len(letters)
