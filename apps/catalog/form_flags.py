"""FB-33 M5d-8 (E7, ревью M5): флаги вида формы товара — какие части формы видит этот бизнес.

Раньше жили во вьюхе (`catalog/views.py::_product_form_flags`); их же читает окно «Inhalt»
(`apps/core/window_parts.py`): пункт «Woher» показывается, если поле видно в форме бизнеса
или заполнено. Один источник — здесь; вьюха и окно берут его, своей копии нет.
"""

from apps.core.archetypes import FOOD_BUSINESS_TYPES

# M1 Boutique: типы с текстильной маркировкой (Textilkennzeichnung EU 1007/2011).
TEXTILE_BUSINESS_TYPES = frozenset({"clothing"})

#: поле формы товара → флаг части формы, в которой оно стоит (`product_form.html`): «Marke &
#: Zustand» (вкладка «Grundlagen»), пищевая и текстильная секции вкладки «Kennzeichnung».
#: Поля без флага секции стоят на вкладке «Kennzeichnung» вне секций — видны вместе с ней.
FIELD_FLAGS = {
    "brand": "show_retail_fields",
    "condition": "show_retail_fields",
    "material": "show_textile_labeling",
    "care": "show_textile_labeling",
    "allergens": "show_food_labeling",
    "additives": "show_food_labeling",
    "origin": "show_labeling_tab",
    "ingredients": "show_labeling_tab",
}


def product_form_flags(tenant) -> dict:
    """W2: флаги вида формы товара — гейт пищевой секции. M1 Boutique: текстильная маркировка
    (material/care) — вкладка Kennzeichnung видна и одежде (W0-инвариант: поля всегда в DOM,
    скрытие CSS). Без запросов: только `tenant.business_type`."""
    bt = getattr(tenant, "business_type", "") or ""
    show_food = bt in FOOD_BUSINESS_TYPES
    show_textile = bt in TEXTILE_BUSINESS_TYPES
    return {
        "show_food_labeling": show_food,
        "show_textile_labeling": show_textile,
        "show_labeling_tab": show_food or show_textile,
        # KA-12 WR-3 (E3.11): «Marke & Zustand» и UVP — товарная розница/аутлет, не кухня.
        # Заполненное значение у гастро всё равно видно (шаблон), поля всегда в DOM (W0).
        "show_retail_fields": not show_food,
    }


def field_shown(tenant, name: str, product=None) -> bool:
    """Видно ли поле `name` в форме товара этого бизнеса (секция и её вкладка). Поле не из
    `FIELD_FLAGS` — видно (у него нет своего гейта). «Marke & Zustand» форма показывает и
    при скрытой секции, если у товара `product` заполнено одно из двух (`product_form.html`)."""
    flag = FIELD_FLAGS.get(name)
    if flag is None:
        return True
    flags = product_form_flags(tenant)
    if flag == "show_retail_fields" and product is not None:
        return flags[flag] or bool(product.brand or product.condition)
    if flag in ("show_textile_labeling", "show_food_labeling"):
        return flags[flag] and flags["show_labeling_tab"]
    return flags[flag]
