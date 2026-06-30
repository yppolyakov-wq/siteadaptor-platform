"""Шаблонные фильтры витрины (site_config UI)."""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from apps.tenants import siteconfig, video

register = template.Library()

# D.1 (анти-Битрикс Phase 2): реестр секций главной — key → партиал. Заменяет
# хардкод if/elif в storefront/home.html (single source of truth, разблокиратор
# для C-блоков и on-canvas «+»). Якоря секций (для меню типа anchor) — отдельно.
BLOCK_TEMPLATES = {
    "hero": "storefront/sections/_hero.html",
    "usp_bar": "storefront/sections/_usp_bar.html",
    "stay_search": "storefront/sections/_stay_search.html",
    "stay_rooms": "storefront/sections/_stay_rooms.html",
    "services": "storefront/sections/_services.html",
    "promotions": "storefront/sections/_promotions.html",
    "categories": "storefront/sections/_categories.html",
    "products": "storefront/sections/_products.html",
    "events": "storefront/sections/_events.html",
    "archetypes": "storefront/sections/_archetypes.html",
    "about": "storefront/sections/_about.html",
    "process": "storefront/sections/_process.html",
    "team": "storefront/sections/_team.html",
    "cta": "storefront/sections/_cta.html",
    "testimonials": "storefront/sections/_testimonials.html",
    "trust": "storefront/sections/_trust.html",
    "reviews": "storefront/sections/_reviews.html",
    "faq": "storefront/sections/_faq.html",
    "gallery": "storefront/sections/_gallery.html",
    "before_after": "storefront/sections/_before_after.html",
    "contact": "storefront/sections/_contact.html",
}
# Якорь-id обёртки секции (scroll-mt-24) — пункты меню типа «anchor» ведут на #id.
_BLOCK_ANCHOR_ID = {
    "stay_search": "buchen",
    "stay_rooms": "zimmer",
    "services": "leistungen",
    "about": "ueber-uns",
    "testimonials": "stimmen",
    "reviews": "bewertungen",
    "faq": "faq",
    "gallery": "galerie",
    "before_after": "referenzen",
    "contact": "kontakt",
}
# Секции с обёрткой scroll-mt-24 без id (плавная прокрутка, без якоря меню).
_BLOCK_WRAP_NOID = {"archetypes"}

# D.2: C-блоки (повторяемые «кубики») — key → партиал. Данные берутся из самого
# блока (`block.data`), а не из контекста вьюхи (в отличие от фикс-секций).
CBLOCK_TEMPLATES = {
    "text": "storefront/sections/_block_text.html",
    "image": "storefront/sections/_block_image.html",
    "image_text": "storefront/sections/_block_image_text.html",
    "button": "storefront/sections/_block_button.html",
    "spacer": "storefront/sections/_block_spacer.html",
}


@register.simple_tag(takes_context=True)
def render_block(context, block):
    """D.1/D.2: отрисовать секцию главной — фикс-секция (по ключу) или C-блок (dict).

    Принимает строку-ключ (фикс-секция, данные из контекста) ИЛИ dict-блок
    ({key,id,data}). C-блоки рендерятся со своими данными.
    """
    key = block if isinstance(block, str) else block.get("key")
    request = context.get("request")
    # D.2: C-блок — рендерим партиал с данными самого блока.
    if key in CBLOCK_TEMPLATES:
        data = block.get("data") if isinstance(block, dict) else {}
        html = render_to_string(
            CBLOCK_TEMPLATES[key],
            {**context.flatten(), "block": data or {}},
            request=request,
        )
        return mark_safe(html)
    tpl = BLOCK_TEMPLATES.get(key)
    if not tpl:
        return ""
    html = render_to_string(tpl, context.flatten(), request=request)
    anchor = _BLOCK_ANCHOR_ID.get(key)
    if anchor:
        return mark_safe(f'<div id="{anchor}" class="scroll-mt-24">{html}</div>')
    if key in _BLOCK_WRAP_NOID:
        return mark_safe(f'<div class="scroll-mt-24">{html}</div>')
    return mark_safe(html)


@register.simple_tag(name="grid_classes")
def grid_classes(site, key):
    """M20R-1: purge-safe Tailwind-грид секции `key` из site_config.

    Использование: <div class="{% grid_classes site 'products' %}">. Раскладка —
    из layout секции (пресет+override) или её дефолта (без визуальной регрессии).
    """
    return siteconfig.grid_class_string(siteconfig.section_layout(site, key))


@register.simple_tag(name="section_font_vars")
def section_font_vars(font_key):
    """H1.5: CSS-переменные шрифта секции (--font-body/--font-head) — оверрайд
    глобального для текстов этой секции. Пусто/неизвестный ключ → "" (наследует
    глобальные vars из _base.html). Каскадит даже через display:contents-обёртку."""
    if not font_key or font_key not in siteconfig.FONTS:
        return ""
    body, head = siteconfig.font_stacks(font_key)
    # Стеки содержат двойные кавычки ("Segoe UI"); это inline-style HTML-атрибут
    # (style="…") → двойные кавычки закрыли бы атрибут. В CSS '…' эквивалентны "…".
    body, head = body.replace('"', "'"), head.replace('"', "'")
    return mark_safe(f"--font-body:{body};--font-head:{head};")


@register.simple_tag(name="section_title")
def section_title(site, key):
    """M20U-7: кастомный заголовок секции главной (или "" → шаблон выводит дефолт)."""
    return siteconfig.section_title(site, key)


@register.simple_tag(name="section_show_all")
def section_show_all(site, key):
    """M20U-7: показывать ли ссылку «View all» секции (по умолчанию True)."""
    return siteconfig.section_show_all(site, key)


@register.simple_tag(name="purchase_label")
def purchase_label(module):
    """M20U-5: подпись действия покупки архетипа (Jetzt buchen / In den Warenkorb …)."""
    from apps.core import archetypes

    return archetypes.purchase_label(module)


@register.simple_tag(name="usp_icon")
def usp_icon(token):
    """A.3: emoji-символ пункта полосы доверия (usp_bar) по токену."""
    return siteconfig.usp_icon(token)


@register.filter(name="video_embed")
def video_embed(url):
    """URL видео → {"kind","src"} (см. apps.tenants.video.embed_info) или None."""
    return video.embed_info(url)


_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}


@register.filter(name="cursym")
def cursym(code):
    """Код валюты → символ («EUR» → «€»); неизвестный — как есть."""
    return _CURRENCY_SYMBOLS.get((code or "").strip().upper(), code)
