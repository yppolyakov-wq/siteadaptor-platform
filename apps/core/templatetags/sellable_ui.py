"""UB1-2: единая карточка продаваемой сущности (услуга/номер) — листинги + home-секции.

Идентичность/медиа/ссылка/CTA-подпись — из контракта `SellableEntity` (адаптеры
делегируют i18n/цену/фото модели); мета-строки и сырые цены для инлайн-прайс-эдита —
per-kind из `obj` в партиале. Контракт сознательно НЕ раздуваем (решение владельца
2026-07-02): бейджи/мета — параметры вызова; `badges` в контракте появится вместе с
product (UB1-3).
"""

from django import template
from django.utils.translation import get_language

from apps.core.sellable import sellable_for

register = template.Library()

# kind → data-edit-model инлайн-редактора канвы (site_inline_edit).
_EDIT_MODELS = {"service": "service", "stay": "stay"}


@register.inclusion_tag("storefront/_sellable_card.html", takes_context=True)
def sellable_card(
    context,
    kind,
    obj,
    variant="vertical",
    href="",
    query="",
    edit=True,
    cta="",
    badge="",
    price_total=None,
    show_area=False,
    show_min_nights=False,
    show_description=True,
    h2=False,
):
    """Карточка sellable-сущности для гридов листингов и home-секций.

    `href` — override ссылки (home-услуги ведут на слот-пикер, поиск по датам — на
    юнит с датами); `query` — доклейка к detail_url (embed); `edit=False` — без
    инлайн-едит-хуков (search-результаты); `cta` — "purchase" (пилюля
    purchase_label) | "select" (пилюля Select у date-search) | "" (без);
    `badge` — текст бейджа (Festpreis); `price_total` — цена за диапазон дат
    (date-search stays, вместо from-€/night); `show_area` — м² в мета-строке
    (home-номера); `show_min_nights` — заметка «min. N nights» (браузинг номеров);
    `show_description=False` — карточка без описания (search-результаты);
    `h2` — заголовок h2 (листинги) вместо h3 (home-секции)."""
    card = sellable_for(kind, obj, get_language())
    return {
        "card": card,
        "obj": obj,
        # ST-7c: глобальная ФОРМА карточки (site_defaults.card_style) — из
        # processor-переменной вызывающего контекста (inclusion-шаблон иначе
        # её не видит); "" = прежняя форма.
        "card_style": context.get("storefront_card_style", ""),
        # HF-2: пиктограммы удобств на карточке номера (пересечение выбора
        # владельца с удобствами номера; у прочих kind — пусто).
        "amenities": (
            obj.card_amenity_badges(only=context.get("storefront_card_amenities", ()))
            if kind == "stay"
            else []
        ),
        "variant": variant,
        "href": (href or card.detail_url) + query,
        "edit": edit,
        "edit_model": _EDIT_MODELS.get(kind, ""),
        "cta": cta,
        "badge": badge,
        "price_total": price_total,
        "show_area": show_area,
        "show_min_nights": show_min_nights,
        "show_description": show_description,
        "h2": h2,
    }


@register.inclusion_tag("storefront/_variant_picker.html", takes_context=True)
def variant_picker(context, product):
    """O-2: свотчи выбора варианта в выбранном владельцем виде.

    Вид: `product.variant_style` → дефолт магазина (`site_defaults.variant_style`)
    → "" (обычный список; тогда партиал ничего не рисует, и форма остаётся
    байт-в-байт прежней). Оси считаем ЗДЕСЬ, чтобы шаблон не тянул логику:
    уникальные цвета/размеры в порядке вариантов, цвет → HEX по словарю.
    """
    from apps.catalog import option_styles

    style = option_styles.variant_style(product, context.get("storefront_variant_style", ""))
    variants = list(product.active_variants) if style else []
    for v in variants:
        v.color_hex = option_styles.color_hex(v.color)
    colors, sizes = [], []
    for v in variants:
        if v.color and all(c["name"] != v.color for c in colors):
            colors.append(
                {"name": v.color, "hex": option_styles.color_hex(v.color), "image": v.image_url}
            )
        if v.size and v.size not in sizes:
            sizes.append(v.size)
    # Вид «две оси» без обеих осей выродился бы в один ряд — честно падаем в кнопки.
    if style == "axes" and not (colors and sizes):
        style = "buttons"
    return {
        "product": product,
        "variant_style": style,
        "variants": variants,
        "variant_colors": colors,
        "variant_sizes": sizes,
    }
