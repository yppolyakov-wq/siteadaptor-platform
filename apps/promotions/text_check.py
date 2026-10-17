"""T-8.10e (D2a-1): акция → `CheckInput` движка «Text-Check» (`apps.core.text_check`).

План — docs/d2-ai-text-check-plan-2026-10-17.md §3.1. Работает и с несохранённой акцией
(`QuickPromotionForm.build()`): только чтение, в БД ничего не пишется. Каждое свойство
цены читается отдельно и с подстраховкой — подсказки не стоят ошибки на экране."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import DatabaseError

from apps.core import text_check as tc

logger = logging.getLogger(__name__)


def _safe(fn, default=None):
    try:
        return fn()
    except DatabaseError:
        # Внутри atomic проглоченная ошибка БД сломала бы транзакцию — пусть всплывёт.
        raise
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


def _codes(value) -> frozenset:
    """Коды аллергенов/диет: только строки (JSON-поле может хранить что угодно)."""
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(v for v in value if isinstance(v, str))


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
        allergens = _codes(getattr(product, "allergens", None))
        diets = _codes(getattr(product, "diets", None))
        unit = getattr(product, "unit", "") or ""
        ingredients = bool((getattr(product, "ingredients", "") or "").strip())
        # У товара с вариантами Grundpreis у каждого варианта свой — акция его не считает.
        if unit and not _safe(lambda: product.has_variants, False):
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
        is_food=bool(_safe(lambda: _is_food(tenant), False)),
        has_product=product is not None,
        allergens=allergens,
        diets=diets,
        product_unit=unit,
        grundpreis_ok=grundpreis_ok,
        ingredients_present=ingredients,
    )


def for_promotion(promo, tenant, *, scope: str = tc.OWNER) -> list[tc.Finding]:
    return tc.run(input_from_promotion(promo, tenant), scope=scope)


# --- D2a-2: сырой POST живой проверки → несохранённая акция --------------------------------

_PRICE_LIMIT = Decimal("1000000")


def _dec(raw) -> Decimal | None:
    value = tc.to_decimal(str(raw or "")[:20])
    if value is None or not value.is_finite() or value < 0 or value > _PRICE_LIMIT:
        return None
    return value.quantize(Decimal("0.01"))


def _int(raw, *, high=1_000_000) -> int | None:
    try:
        value = int(str(raw or "").strip()[:9])
    except ValueError:
        return None
    return value if 0 <= value <= high else None


def _ends_at(data, tenant):
    from datetime import date

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from . import quick

    term = str(data.get("term") or "")
    if term:
        until = None
        try:
            until = (
                date.fromisoformat(str(data.get("until") or "")[:10]) if data.get("until") else None
            )
        except ValueError:
            until = None
        if term == quick.TERM_DATE and until is None:
            return None
        try:
            return quick.term_end(term, tenant, until=until)
        except Exception:  # noqa: BLE001 — незнакомый чип/битая дата: срока просто нет
            return None
    try:
        end = parse_datetime(str(data.get("ends_at") or "")[:32])
    except ValueError:
        return None
    if end is not None and timezone.is_naive(end):
        end = timezone.make_aware(end)
    return end


def _payload_texts(data, name: str) -> dict:
    from django.conf import settings

    out = {}
    base = data.get(name)
    if isinstance(base, str) and base.strip():
        out[settings.LANGUAGE_CODE] = base.strip()[: tc.MAX_TEXT]
    for code, _label in settings.LANGUAGES:
        value = data.get(f"{name}_{code}")
        if isinstance(value, str) and value.strip():
            out[code] = value.strip()[: tc.MAX_TEXT]
    return out


def _product(raw):
    from django.core.exceptions import ValidationError

    from apps.catalog.models import Product

    raw = str(raw or "").strip()[:64]
    if not raw:
        return None
    try:
        return Product.objects.filter(pk=raw).first()
    except (ValidationError, ValueError):
        return None


def promotion_from_payload(data, tenant):
    """Поля ассистента («title», «new_price», «term»…) или полной формы («title_de»,
    «price_override», «ends_at»…) → НЕСОХРАНЁННАЯ акция. Мусор в числах/датах = поле
    пусто; товар — одним запросом. В БД ничего не пишется."""
    from apps.core import price_conditions

    from .models import Promotion

    meta = {}
    if data.get("perishable") in ("on", "true", "1", True):
        meta["perishable"] = True
    if data.get("price_condition_kind"):
        cond = price_conditions.normalize(
            {
                "kind": data.get("price_condition_kind"),
                "n": data.get("price_condition_n"),
                "pay": data.get("price_condition_pay"),
                "note": str(data.get("price_condition_note") or "")[: price_conditions.NOTE_MAX],
            }
        )
        if cond:
            meta["price_condition"] = cond
    style = str(data.get("discount_style") or "")[:20]
    return Promotion(
        title=_payload_texts(data, "title"),
        description=_payload_texts(data, "description"),
        price_override=_dec(data.get("new_price") or data.get("price_override")),
        compare_at_price=_dec(data.get("old_price") or data.get("compare_at_price")),
        discount_percent=_int(data.get("percent") or data.get("discount_percent"), high=100),
        available_quantity=_int(data.get("quantity") or data.get("available_quantity")),
        ends_at=_ends_at(data, tenant),
        product=_product(data.get("product")),
        discount_style=style,
        is_surprise=data.get("is_surprise") in ("on", "true", "1", True),
        metadata=meta,
    )
