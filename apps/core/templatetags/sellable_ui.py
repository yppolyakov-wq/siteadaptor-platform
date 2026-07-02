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


@register.inclusion_tag("storefront/_sellable_card.html")
def sellable_card(
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
    `h2` — заголовок h2 (листинги) вместо h3 (home-секции)."""
    card = sellable_for(kind, obj, get_language())
    return {
        "card": card,
        "obj": obj,
        "variant": variant,
        "href": (href or card.detail_url) + query,
        "edit": edit,
        "edit_model": _EDIT_MODELS.get(kind, ""),
        "cta": cta,
        "badge": badge,
        "price_total": price_total,
        "show_area": show_area,
        "show_min_nights": show_min_nights,
        "h2": h2,
    }
