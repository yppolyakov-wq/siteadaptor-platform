"""Разбор полей форм кабинета номеров (UX-D D4.0: вынесено из views, чтобы модуль
настроечных действий `settings_actions` и экраны волны D4 разбирали ввод одинаково)."""

from __future__ import annotations

import re

from . import rate_plans as rate_plans_mod
from .models import StayUnit


def _int(raw, default, lo, hi) -> int:
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        return default


def _eur_to_cents(raw) -> int:
    """«80» / «79,50» → центы (анти-кривой ввод → 0)."""
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError, OverflowError):  # «1e999» → inf → OverflowError
        return 0


_HOUR_RE = re.compile(r"[0-9]{1,2}")


def _parse_hour(raw):
    """Z-5: час 0..23 строго ASCII-цифрами (``"٣".isdigit()`` — True); иначе None."""
    raw = (raw or "").strip()
    if not _HOUR_RE.fullmatch(raw):
        return None
    hour = int(raw)
    return hour if 0 <= hour <= 23 else None


def _rateplan_pk(post):
    """pk тарифа из формы — строгий UUID; мусор → None (404/ничего), не 500."""
    return rate_plans_mod.parse_uuid(post.get("rateplan"))


def _rateplan_scope(post):
    """Охват тарифа из формы: None — поля нет (не трогать); (True, []) — все
    категории; (False, [StayUnit…]) — выбранные (только существующие pk)."""
    scope = post.get("rate_scope")
    if scope == "all":
        return (True, [])
    if scope != "some":
        return None
    pks = rate_plans_mod.parse_pks(post.getlist("units"))
    return (False, list(StayUnit.objects.filter(pk__in=pks)))
