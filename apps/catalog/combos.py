"""Комбо-наборы (A4 Gastro): расчёт цены и валидация выбора.

Зеркало apps.catalog.modifiers для комбо: цена = фикс Combo.price + Σ надбавок
выбранных опций; валидация выбора по правилам групп (min/max). Используется на
витрине (конфигуратор) и при оформлении заказа.
"""

from decimal import Decimal

from django.utils.translation import gettext as _

from .models import Combo, ComboOption


def options_from_ids(combo, option_ids):
    """[ComboOption] по списку id среди активных опций комбо (порядок групп).

    MEN-2: included-группы («Im Set enthalten») пропускаются — их стоимость уже
    заложена в Combo.price, и id их опций из POST не должны прибавлять надбавку.
    """
    ids = {str(i) for i in option_ids}
    out = []
    for group in combo.groups_active:
        if group.included:
            continue
        for opt in group.options_active:
            if str(opt.pk) in ids:
                out.append(opt)
    return out


def options_delta(options) -> Decimal:
    return sum((o.price_delta for o in options), Decimal("0"))


def combo_price(combo, options=()) -> Decimal:
    """Итоговая цена комбо: фикс-цена + надбавки выбранных опций."""
    return combo.price + options_delta(options)


def combo_price_from(combo) -> Decimal:
    """MEN-2: минимально возможная цена сборки («ab …») для карточек/агрегатора.

    Фикс-цена + по каждой ОБЯЗАТЕЛЬНОЙ группе выбора (min_select ≥ 1, не
    included) — min_select наименьших надбавок её опций.
    """
    total = combo.price
    for group in combo.groups_active:
        if group.included or group.min_select < 1:
            continue
        deltas = sorted(o.price_delta for o in group.options_active)
        total += sum(deltas[: group.min_select], Decimal("0"))
    return total


def validate_selection(combo, option_ids):
    """Проверить выбор по группам комбо. Возвращает (options, error_str).

    Каждая группа: min_select..max_select из своих опций. min>=1 — обязательная.
    Чужие/неактивные id игнорируются. error пустой = ок.
    """
    chosen = set(str(i) for i in option_ids)
    selected = []
    for group in combo.groups_active:
        # MEN-2: фикс-состав («Im Set enthalten») — показывается, но не выбирается.
        if group.included:
            continue
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
        # MX-0: id опции — тот же учётный ключ, что у модификаторов.
        snap.append({"id": str(o.pk), "label": label, "delta": str(o.price_delta)})
    return snap


def pool_products(combo):
    """MEN-4: пул «свободной сборки» — активные БЛЮДА категории набора.

    Блюдо = товар с указанным Gang'ом (`course`): в кейтеринг-категории рядом с
    блюдами лежат пакеты («Hochzeitsbuffet, 39 €/Gast») — предлагать их внутри
    конструктора блюд неверно. Если Gang не задан НИ У КОГО — берём всё
    (иначе конструктор был бы пуст у того, кто поля ещё не заполнил).
    """
    from .models import Product

    if not (combo.free_pool and combo.category_id):
        return []
    products = list(Product.objects.filter(is_active=True, category_id=combo.category_id))
    dishes = [p for p in products if p.course]
    return dishes or products


def validate_pool(combo, dish_ids):
    """MEN-4: (products, error) — выбор свободной сборки, СТРОГО.

    Чужой/протухший id — честная ошибка (молчаливый дроп менял бы цену заказа);
    минимум — одно блюдо. Дубли схлопываются, порядок = порядок пула.
    """
    ids = {str(i) for i in dish_ids}
    if not ids:
        return [], _("Please choose at least one dish.")
    pool = {str(p.pk): p for p in pool_products(combo)}
    if ids - set(pool):
        return [], _("Please review your selection — some dishes are unavailable.")
    return [p for k, p in pool.items() if k in ids], ""


def pool_price(combo, dishes) -> Decimal:
    """MEN-4: цена свободной сборки = базовая цена набора (обычно 0) + Σ à la
    carte (Product.base_price) — «свободное ≥ наборного» держится ценами блюд."""
    return combo.price + sum((d.base_price for d in dishes), Decimal("0"))


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
