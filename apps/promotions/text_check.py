"""T-8.10e (D2a-1): акция → `CheckInput` движка «Text-Check» (`apps.core.text_check`).

План — docs/d2-ai-text-check-plan-2026-10-17.md §3.1. Работает и с несохранённой акцией
(`QuickPromotionForm.build()`): только чтение, в БД ничего не пишется. Каждое свойство
цены читается отдельно и с подстраховкой — подсказки не стоят ошибки на экране."""

from __future__ import annotations

import logging

from apps.core import text_check as tc

logger = logging.getLogger(__name__)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — свойство цены не должно ронять проверку
        logger.exception("text_check: promotion property failed")
        return default


def _locale_texts(value) -> dict:
    if isinstance(value, str):
        value = {"de": value}
    if not isinstance(value, dict):
        return {}
    return {
        str(loc): text.strip()[: tc.MAX_TEXT]
        for loc, text in value.items()
        if isinstance(text, str) and text.strip()
    }


def _is_food(tenant) -> bool:
    if tenant is None:
        return False
    from . import reference_price

    return reference_price.food_allowed(tenant)


def input_from_promotion(promo, tenant) -> tc.CheckInput:
    from apps.core import price_conditions

    texts = {
        name: found
        for name in ("title", "description")
        if (found := _locale_texts(getattr(promo, name, None)))
    }
    condition = _safe(lambda: price_conditions.of(promo))
    if condition and (note := _locale_texts(condition.get("note"))):
        texts["condition_note"] = note

    has_discount = bool(_safe(lambda: promo.has_discount, False))
    product = _safe(lambda: promo.product if promo.product_id else None)
    allergens = diets = frozenset()
    unit = ""
    ingredients = False
    grundpreis_ok = None
    if product is not None:
        allergens = frozenset(getattr(product, "allergens", None) or ())
        diets = frozenset(getattr(product, "diets", None) or ())
        unit = getattr(product, "unit", "") or ""
        ingredients = bool((getattr(product, "ingredients", "") or "").strip())
        if unit:
            grundpreis_ok = _safe(lambda: promo.grundpreis) is not None

    return tc.CheckInput(
        texts=texts,
        new_price=_safe(lambda: promo.new_price),
        old_price=_safe(lambda: promo.old_price) if has_discount else None,
        percent=_safe(lambda: promo.discount_percent_display),
        ends_at=promo.ends_at,
        quantity=promo.available_quantity,
        price_condition=condition,
        mystery=bool(promo.is_surprise or promo.discount_style == "mystery"),
        perishable=bool(_safe(lambda: promo.is_perishable, False)),
        is_food=_is_food(tenant),
        has_product=product is not None,
        allergens=allergens,
        diets=diets,
        product_unit=unit,
        grundpreis_ok=grundpreis_ok,
        ingredients_present=ingredients,
    )


def for_promotion(promo, tenant, *, scope: str = tc.OWNER) -> list[tc.Finding]:
    return tc.run(input_from_promotion(promo, tenant), scope=scope)
