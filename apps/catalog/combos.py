"""Комбо-наборы (A4 Gastro): расчёт цены и валидация выбора.

Зеркало apps.catalog.modifiers для комбо: цена = фикс Combo.price + Σ надбавок
выбранных опций; валидация выбора по правилам групп (min/max). Используется на
витрине (конфигуратор) и при оформлении заказа.
"""

from decimal import Decimal

from django.utils.translation import gettext as _

from .models import Combo, ComboOption


def options_from_ids(combo, option_ids):
    """[ComboOption] по списку id среди активных опций комбо (порядок групп)."""
    ids = {str(i) for i in option_ids}
    out = []
    for group in combo.groups_active:
        for opt in group.options_active:
            if str(opt.pk) in ids:
                out.append(opt)
    return out


def options_delta(options) -> Decimal:
    return sum((o.price_delta for o in options), Decimal("0"))


def combo_price(combo, options=()) -> Decimal:
    """Итоговая цена комбо: фикс-цена + надбавки выбранных опций."""
    return combo.price + options_delta(options)


def validate_selection(combo, option_ids):
    """Проверить выбор по группам комбо. Возвращает (options, error_str).

    Каждая группа: min_select..max_select из своих опций. min>=1 — обязательная.
    Чужие/неактивные id игнорируются. error пустой = ок.
    """
    chosen = set(str(i) for i in option_ids)
    selected = []
    for group in combo.groups_active:
        opt_ids = {str(o.pk) for o in group.options_active}
        picked = [o for o in group.options_active if str(o.pk) in chosen]
        n = len(picked)
        if n < group.min_select:
            return [], _("Please choose for: %(g)s") % {"g": group.label}
        if group.max_select and n > group.max_select:
            return [], _("Too many chosen for: %(g)s") % {"g": group.label}
        selected.extend(picked)
        chosen -= opt_ids
    return selected, ""


def combo_snapshot(combo, options):
    """Снимок состава для заказа: [{label, delta}] — название товара + надбавка."""
    snap = []
    for o in options:
        label = str(o.product) if o.product_id else ""
        snap.append({"label": label, "delta": str(o.price_delta)})
    return snap


def active_combos():
    """Активные комбо с предзагруженными группами/опциями/товарами."""
    return (
        Combo.objects.filter(is_active=True)
        .prefetch_related("groups__options__product")
        .order_by("sort_order", "created_at")
    )


def get_active(pk):
    return (
        Combo.objects.filter(pk=pk, is_active=True)
        .prefetch_related("groups__options__product")
        .first()
    )


# импорт для типизации/реэкспорта
__all__ = [
    "ComboOption",
    "options_from_ids",
    "options_delta",
    "combo_price",
    "validate_selection",
    "combo_snapshot",
    "active_combos",
    "get_active",
]
