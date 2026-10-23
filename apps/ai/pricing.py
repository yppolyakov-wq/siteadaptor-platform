"""Оценка стоимости вызова: `AI_PRICES = {"<модель>": [центов за 1M входных, за 1M
выходных]}` (env JSON). Неизвестная цена → пессимистичная `AI_DEFAULT_PRICE` (уровень
сильнейших моделей): денежный лимит работает и без таблицы цен, а ai.W002 напоминает её
задать. Фейк бесплатен."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

MILLION = Decimal(1_000_000)


def _pair(raw):
    if not raw or len(raw) != 2:
        return None
    try:
        return Decimal(str(raw[0])), Decimal(str(raw[1]))
    except ArithmeticError:
        return None


def price_for(model: str):
    if model == "fake":
        return Decimal(0), Decimal(0)
    from . import config

    prices = config.get("AI_PRICES") or {}
    return _pair(prices.get(model)) or _pair(getattr(settings, "AI_DEFAULT_PRICE", None))


def cost_cents(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    pair = price_for(model)
    if pair is None:
        return Decimal(0)
    return ((pair[0] * tokens_in + pair[1] * tokens_out) / MILLION).quantize(Decimal("0.0001"))
