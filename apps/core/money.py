"""KA-M2: разбор суммы, введённой человеком, независимо от языка интерфейса.

«12,50» / «12.50» / «1.234,56» / «1 299» / «12,50 €» → Decimal. Встроенный
`DecimalField(localize=True)` тут не годится: его разбор зависит от активного языка, и при
кабинете на `en` «12,50» читался бы как 1250 (запятая — разделитель тысяч).

Правило (то же, что у `text_check.to_decimal`): группы по три цифры через пробел или
точку — это тысячи («1.234,56», «1 299», «1.234.567»); иначе запятая — десятичный знак.
Одиночная группа через точку без запятой («1.500», «0.125») неоднозначна — остаётся
десятичной, и поле с двумя знаками её отклоняет (ошибка лучше цены ×1000). Точка без групп по три
остаётся десятичной («12.50») — так приходят значения из тестов, Celery и API."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_THOUSANDS = re.compile(r"-?\d{1,3}(?:[ .]\d{3})+(?:,\d+)?")
_PLAIN = re.compile(r"-?\d+(?:\.\d+)?")


def _ambiguous_dot(s: str) -> bool:
    """«0.125», «1.500» без запятой: одна группа после точки — это может быть и тысяча, и
    дробь. Тихо читать как тысячи нельзя (цена ×1000); оставляем точку десятичной, и
    валидатор поля сам отклонит три знака после запятой — человек увидит ошибку."""
    if "," in s or " " in s:
        return False
    head, *groups = s.lstrip("-").split(".")
    return len(groups) == 1 or head.lstrip("0") == ""


def parse_money(raw) -> Decimal | None:
    """Сумма из строки. Пусто → None; не число → ValueError."""
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise ValueError(raw)
        return raw
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        raw = str(raw)
    s = str(raw).replace(" ", " ").replace("€", "").strip()
    if not s:
        return None
    if _THOUSANDS.fullmatch(s) and not _ambiguous_dot(s):
        s = s.replace(".", "").replace(" ", "").replace(",", ".")
    else:
        s = s.replace(" ", "")
        if s.count(",") > 1 or ("," in s and "." in s):
            raise ValueError(raw)
        s = s.replace(",", ".")
    if not _PLAIN.fullmatch(s):
        raise ValueError(raw)
    try:
        return Decimal(s)
    except InvalidOperation as exc:  # pragma: no cover — regex уже отсёк
        raise ValueError(raw) from exc
