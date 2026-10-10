"""T-8.13b: своя категория бизнеса → категория каталога города (связь, не копия).

План — docs/t8-13b-category-mapping-plan-2026-10-10.md. Один резолвер на синк акций сейчас
и на товары каталога города (T-8.11): своё поле → вверх по родителям → подсказка по
названию → "".
"""

from __future__ import annotations

from apps.core import city_categories as cc

_MAX_DEPTH = 10  # страховка от цикла в дереве


def resolve(category) -> str:
    return _own_up(category) or suggested(category)


def _own_up(category) -> str:
    node, depth = category, 0
    while node is not None and depth < _MAX_DEPTH:
        own = cc.normalize_category(getattr(node, "city_category", ""))
        if own:
            return own
        node, depth = getattr(node, "parent", None), depth + 1
    return ""


def auto_for(category) -> str:
    """Что выйдет БЕЗ своего выбора у этой категории: родители → название."""
    if category is None:
        return ""
    return _own_up(getattr(category, "parent", None)) or suggested(category)


def suggested(category) -> str:
    """Подсказка по названию — от самой категории вверх (как видит её владелец)."""
    node, depth = category, 0
    while node is not None and depth < _MAX_DEPTH:
        hint = cc.suggest_for_name(_names(node))
        if hint:
            return hint
        node, depth = getattr(node, "parent", None), depth + 1
    return ""


def _names(node) -> str:
    name = getattr(node, "name", None)
    if isinstance(name, dict):
        return " ".join(str(v) for v in name.values() if v)
    return str(name or "")
