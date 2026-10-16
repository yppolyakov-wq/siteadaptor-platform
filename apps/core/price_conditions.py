"""В2: условие цены акции — «2. Stück −50 %», «2 für 1», «ab 3 Stück −20 %».

План `docs/v2-v4-conditions-condition-plan-2026-10-16.md`. Акция с условием
снижает цену НЕ каждой штуки: показывать её «цену за штуку × (100 − %)» нечестно
(PAngV/UWG), а применять к каждой строке корзины — потеря денег. Поэтому при
условии акция не меняет цену штуки вовсе (`Promotion.new_price` = обычная цена),
а условие выводится подписью-бейджем.

Хранение — `Promotion.metadata["price_condition"]` (прецедент `response`/
`perishable`, без миграции): ``{"kind", "n", "pay", "note": {loc: text}}``.
Мусор → «условия нет» (fail-safe: страница не падает, цена остаётся обычной).
"""

from __future__ import annotations

import contextlib

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

NTH = "nth"  # каждая n-я штука −p %
X_FOR_Y = "x_for_y"  # n штук по цене pay
MIN_QTY = "min_qty"  # от n штук −p %
OTHER = "other"  # своё условие текстом

KINDS = (NTH, X_FOR_Y, MIN_QTY, OTHER)
PERCENT_KINDS = (NTH, MIN_QTY)
NOTE_MAX = 80

#: Выбор в форме владельца ("" = условия нет).
CHOICES = [
    ("", _("Keine Bedingung")),
    (NTH, _("Jedes n-te Stück reduziert")),
    (X_FOR_Y, _("n Stück zum Preis von m")),
    (MIN_QTY, _("Ab einer Stückzahl")),
    (OTHER, _("Andere Bedingung")),
]

_N_RANGE = {NTH: (2, 10), X_FOR_Y: (2, 10), MIN_QTY: (2, 99)}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _note(raw) -> dict:
    if isinstance(raw, str):
        raw = {settings.LANGUAGE_CODE: raw}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for loc, text in raw.items():
        if isinstance(loc, str) and isinstance(text, str) and text.strip():
            out[loc] = text.strip()[:NOTE_MAX]
    return out


def normalize(raw) -> dict | None:
    """Проверенное условие или None. Порядок ключей и типы постоянны — снимок
    каталога сравнивается равенством, иначе сверка переписывала бы строки."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if kind not in KINDS:
        return None
    note = _note(raw.get("note"))
    if kind == OTHER:
        return {"kind": OTHER, "n": None, "pay": None, "note": note} if note else None
    n = _int(raw.get("n"))
    low, high = _N_RANGE[kind]
    if n is None or not low <= n <= high:
        return None
    pay = None
    if kind == X_FOR_Y:
        pay = _int(raw.get("pay"))
        if pay is None or not 1 <= pay < n:
            return None
    return {"kind": kind, "n": n, "pay": pay, "note": note}


def of(promo) -> dict | None:
    """Условие акции (None — нет). Mystery сильнее: условие раскрыло бы скидку."""
    if getattr(promo, "discount_style", "") == "mystery":
        return None
    meta = getattr(promo, "metadata", None)
    if not isinstance(meta, dict):
        return None
    return normalize(meta.get("price_condition"))


def label(cond, percent=None, locale: str | None = None) -> str:
    """Короткая подпись бейджа на языке посетителя (или `locale`)."""
    cond = normalize(cond) if cond and "kind" in cond else None
    if not cond:
        return ""
    with translation.override(locale) if locale else contextlib.nullcontext():
        note = cond["note"]
        lang = locale or translation.get_language() or settings.LANGUAGE_CODE
        note_text = (
            note.get(lang) or note.get(settings.LANGUAGE_CODE) or next(iter(note.values()), "")
        )
        kind, n, pay = cond["kind"], cond["n"], cond["pay"]
        pct = _int(percent)
        if kind == NTH:
            text = (
                gettext("%(n)s. Stück −%(p)s %%") % {"n": n, "p": pct}
                if pct
                else gettext("%(n)s. Stück reduziert") % {"n": n}
            )
        elif kind == X_FOR_Y:
            text = gettext("%(n)s für %(pay)s") % {"n": n, "pay": pay}
        elif kind == MIN_QTY:
            text = (
                gettext("ab %(n)s Stück −%(p)s %%") % {"n": n, "p": pct}
                if pct
                else gettext("ab %(n)s Stück") % {"n": n}
            )
        else:
            return note_text
    return f"{text} · {note_text}" if note_text else text
