"""Оценка стоимости вызова: `AI_PRICES = {"<модель>": [центов за 1M входных, за 1M
выходных]}` (env JSON). Неизвестная цена → 0 (бюджет занижен — system check ai.W002)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

MILLION = Decimal(1_000_000)


def price_for(model: str):
    prices = getattr(settings, "AI_PRICES", None) or {}
    pair = prices.get(model)
    if not pair or len(pair) != 2:
        return None
    return Decimal(str(pair[0])), Decimal(str(pair[1]))


def cost_cents(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    pair = price_for(model)
    if pair is None:
        return Decimal(0)
    return ((pair[0] * tokens_in + pair[1] * tokens_out) / MILLION).quantize(Decimal("0.0001"))
