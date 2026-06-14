"""Выбор модификаторов на витрине (A4b): валидация и сумма надбавок.

Используется и при добавлении в корзину (валидация выбора по правилам групп),
и при восстановлении выбора из ключа корзины / создании заказа. Возвращаем сами
объекты ModifierOption — снимок (label + delta) кладёт в заказ orders.services.
"""

from decimal import Decimal

from django.utils.translation import gettext as _


def validate_selection(product, option_ids):
    """Проверить выбор опций по правилам активных групп товара.

    option_ids — итерируемое строк (pk опций из формы). Возвращает
    (options, error): options — список выбранных ModifierOption (в порядке групп
    и опций, без дублей), error — текст ошибки (str) или '' если всё ок.
    """
    selected = {str(oid) for oid in option_ids}
    chosen = []
    for group in product.modifier_groups_active:
        picked = [o for o in group.active_options if str(o.pk) in selected]
        count = len(picked)
        if count < group.min_select:
            return [], _("Please choose an option for “%(group)s”.") % {"group": group.name}
        if group.max_select and count > group.max_select:
            return [], _("Too many options for “%(group)s”.") % {"group": group.name}
        chosen.extend(picked)
    return chosen, ""


def options_from_ids(product, option_ids):
    """Активные опции товара по списку id (для восстановления из корзины).

    Без проверки min/max — просто отбрасываем исчезнувшие/чужие/неактивные,
    сохраняя порядок групп. Цена пересчитывается по тому, что осталось.
    """
    selected = {str(oid) for oid in option_ids}
    return [
        o
        for group in product.modifier_groups_active
        for o in group.active_options
        if str(o.pk) in selected
    ]


def options_delta(options) -> Decimal:
    """Сумма надбавок выбранных опций (Decimal)."""
    return sum((Decimal(str(o.price_delta)) for o in options), Decimal("0"))
