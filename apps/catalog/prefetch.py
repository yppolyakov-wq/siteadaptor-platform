"""KA-12 E10: предзагрузка того, что читает карточка товара, — одним запросом на список.

Карточка спрашивает «есть ли варианты» (`has_variants`, до 4 раз), «от какой цены»
(`price_from`), «в наличии ли» (`in_stock`) и «есть ли опции» (`has_modifiers`) — без
предзагрузки каждое свойство идёт в базу отдельно: на странице каталога в 24 товара это
было ~200 запросов. Здесь — по одному запросу на варианты, группы опций и сами опции на
весь список. Модель читает предзагруженное, если оно есть (`Product.active_variants`,
`modifier_groups_active`, `ModifierGroup.active_options`), иначе ходит в базу как раньше.

Только для ПОКАЗА: покупка и проверка выбора берут свежий объект.
"""

from django.db.models import Prefetch, prefetch_related_objects


def prefetch_cards(products) -> list:
    """Предзагрузить варианты и опции товаров списка (повторный вызов — без запросов)."""
    from .models import ModifierGroup, ModifierOption, Product, ProductVariant

    products = list(products)
    # Только сохранённые товары: заглушки тестов секций и несохранённые объекты
    # (UUID назначается в __init__ — несохранённость видна по `_state.adding`) — как были.
    todo = [
        p
        for p in products
        if isinstance(p, Product)
        and not p._state.adding
        and "_pf_active_variants" not in p.__dict__
    ]
    if not todo:
        return products
    prefetch_related_objects(
        todo,
        Prefetch(
            "variants",
            queryset=ProductVariant.objects.filter(is_active=True),
            to_attr="_pf_active_variants",
        ),
        Prefetch(
            "modifier_groups",
            queryset=ModifierGroup.objects.filter(is_active=True).prefetch_related(
                Prefetch(
                    "options",
                    queryset=ModifierOption.objects.filter(is_active=True),
                    to_attr="_pf_active_options",
                )
            ),
            to_attr="_pf_modifier_groups",
        ),
    )
    return products
