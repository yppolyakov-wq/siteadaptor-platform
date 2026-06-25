"""Шаблонные фильтры витрины (site_config UI)."""

from django import template

from apps.tenants import siteconfig, video

register = template.Library()


@register.simple_tag(name="grid_classes")
def grid_classes(site, key):
    """M20R-1: purge-safe Tailwind-грид секции `key` из site_config.

    Использование: <div class="{% grid_classes site 'products' %}">. Раскладка —
    из layout секции (пресет+override) или её дефолта (без визуальной регрессии).
    """
    return siteconfig.grid_class_string(siteconfig.section_layout(site, key))


@register.simple_tag(name="purchase_label")
def purchase_label(module):
    """M20U-5: подпись действия покупки архетипа (Jetzt buchen / In den Warenkorb …)."""
    from apps.core import archetypes

    return archetypes.purchase_label(module)


@register.filter(name="video_embed")
def video_embed(url):
    """URL видео → {"kind","src"} (см. apps.tenants.video.embed_info) или None."""
    return video.embed_info(url)


_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}


@register.filter(name="cursym")
def cursym(code):
    """Код валюты → символ («EUR» → «€»); неизвестный — как есть."""
    return _CURRENCY_SYMBOLS.get((code or "").strip().upper(), code)
