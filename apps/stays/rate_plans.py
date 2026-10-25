"""KA-12 Z-4 (E4.6c): выбор тарифа с учётом категорий — единственная точка.

Только чтение: ``active_plans`` (один набор с prefetch категорий на запрос),
``plans_for`` (фильтр в памяти, без запросов), ``resolve_choice`` (POST-значение
формы брони → тариф или None; неприменимое — отказ, без тихого фолбэка).
"""

import uuid

from django.db.models import Prefetch

from apps.stays.models import RatePlan, StayUnit


def parse_uuid(raw):
    """Строгий UUID из формы (pk тарифов и категорий — UUID); мусор → None."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 36 or not raw.isascii():
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def parse_pks(values, *, limit=200) -> list:
    """Список pk из формы (чекбоксы): только валидные UUID, без дублей, не больше
    ``limit``. Мусор отбрасывается."""
    out = []
    for v in values[:limit]:
        pk = parse_uuid(v)
        if pk is not None and pk not in out:
            out.append(pk)
    return out


class RatePlanInvalid(Exception):
    """Тариф не существует, неактивен или не применим к выбранной категории."""


def active_plans() -> list:
    """Активные тарифы с категориями (2 запроса), порядок sort_order, name."""
    return list(
        RatePlan.objects.filter(is_active=True).prefetch_related(
            Prefetch("units", queryset=StayUnit.objects.only("pk", "name", "name_i18n"))
        )
    )


def plans_for(unit, plans) -> list:
    """Тарифы из ``plans``, применимые к категории ``unit`` (0 запросов при prefetch)."""
    return [rp for rp in plans if rp.applies_to(unit)]


def resolve_choice(unit, raw, *, plans, empty="first"):
    """Значение поля ``rate_plan`` → тариф.

    Пустое: ``empty="first"`` (витрина — паритет с отмеченным первым радио) →
    первый применимый или None; ``empty="none"`` (стойка) → None. Непустое, но
    не UUID или не среди применимых активных → ``RatePlanInvalid``."""
    if isinstance(raw, (list, tuple)):  # POST.getlist: больше одного значения — подделка
        if len(raw) > 1:
            raise RatePlanInvalid("multiple")
        raw = raw[0] if raw else ""
    raw = (raw or "").strip()
    applicable = plans_for(unit, plans)
    if not raw:
        return applicable[0] if (empty == "first" and applicable) else None
    pk = parse_uuid(raw)
    if pk is None:
        raise RatePlanInvalid(raw)
    for rp in applicable:
        if rp.pk == pk:
            return rp
    raise RatePlanInvalid(raw)
