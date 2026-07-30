"""S7: резолв многоуровневого меню витрины из site_config['menus'].

Узел (siteconfig._clean_menu_node) → готовый пункт {label, url, icon, children}
для шапки/нижнего меню. Тип определяет построение ссылки и гейтинг по активному
модулю. Узлы без ссылки и без детей отбрасываются; «group»-родитель остаётся,
если есть хоть один резолвимый ребёнок. url НЕ резолвится в шаблоне — здесь, и
недоступный маршрут (NoReverseMatch) гасит узел.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.core import modules

from . import siteconfig

_PAGE_URL_NAMES = {
    "home": "storefront-home",
    "offers": "storefront-home",
    "about": "storefront-about",
}


def _reverse(name: str):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _archetype_url(tenant, key: str):
    spec = modules.get_module(key)
    if spec is None or not spec.storefront_landing:
        return None
    if not modules.is_module_active(tenant, key):
        return None
    return _reverse(spec.storefront_landing)


def _category_url(tenant, slug: str):
    if not slug or not modules.is_module_active(tenant, "catalog"):
        return None
    from apps.catalog.models import Category

    if not Category.objects.filter(slug=slug, is_active=True).exists():
        return None
    base = _reverse("storefront-products")
    return f"{base}?kategorie={slug}" if base else None


def _promo_group_url(tenant, group: str):
    if not group or not modules.is_module_active(tenant, "promotions"):
        return None
    from apps.promotions.models import Promotion

    if not Promotion.objects.filter(status="active", group=group).exists():
        return None
    base = _reverse("storefront-aktionen")
    if not base:
        return None
    from urllib.parse import quote

    return f"{base}?gruppe={quote(group)}"


def _node_url(tenant, node: dict):
    ntype, target = node["type"], node["target"]
    if ntype == "archetype":
        return _archetype_url(tenant, target)
    if ntype == "category":
        return _category_url(tenant, target)
    if ntype == "promo_group":
        return _promo_group_url(tenant, target)
    if ntype == "page":
        name = _PAGE_URL_NAMES.get(target)
        return _reverse(name) if name else None
    if ntype == "url":
        return target or None
    if ntype == "anchor":
        if not target:
            return None
        return target if target.startswith(("#", "/")) else f"/#{target}"
    # group: своей ссылки нет — родитель выпадающего подменю, держится на детях.
    # Фидбэк 2026-07-30 («кнопка Акция не кликабельная»): если ВСЕ дети —
    # promo_group, у группы есть осмысленная цель — страница всех акций;
    # клик по пункту ведёт туда, hover по-прежнему раскрывает подменю.
    if ntype == "group":
        kids = node.get("children") or []
        if kids and all(k.get("type") == "promo_group" for k in kids):
            return (
                _reverse("storefront-aktionen") if tenant.is_module_active("promotions") else None
            )
    return None


# Якоря перевода: стандартные подписи меню приходят из ДАННЫХ (site_config/демо-
# киты), а не из gettext-литералов, поэтому makemessages их не извлечёт. Перечисляем
# их здесь gettext_lazy, чтобы msgid'ы жили в каталогах и переводились на язык
# витрины через фолбэк _node_label. (Кастомные подписи владельца — не msgid'ы,
# gettext вернёт их без изменений.)
_MENU_LABEL_ANCHORS = (
    _("Start"),
    _("Galerie"),
    _("Zimmer & Preise"),
    _("Bewertungen"),
    _("Hausordnung"),
    _("FAQ"),
    _("Über uns"),
    _("Kontakt"),
    _("Jetzt buchen"),
    _("Buchen"),
    _("Zimmer"),
    _("Speisekarte"),
    _("Angebote"),
    _("Termine"),
    _("Leistungen"),
    _("Anfahrt"),
)


def _node_label(node: dict) -> str:
    """Подпись узла на текущей локали (i18n): явный `label_i18n[locale]` →
    иначе gettext базовой подписи. Стандартные пункты («Kontakt», «Galerie»,
    «Jetzt buchen» …) — msgid'ы хрома и переводятся на язык витрины; кастомные
    подписи владельца не являются msgid'ами → gettext вернёт их без изменений."""
    from django.utils.translation import get_language, gettext

    li18n = node.get("label_i18n") or {}
    explicit = li18n.get(get_language() or "de")
    return explicit or gettext(node["label"])


def _resolve(tenant, node: dict):
    if not node.get("enabled", True):
        return None
    children = [c for c in (_resolve(tenant, k) for k in node.get("children", [])) if c]
    url = _node_url(tenant, node)
    if url is None and not children:
        return None
    return {
        "label": _node_label(node),
        "url": url,
        "icon": node.get("icon", ""),
        "children": children,
    }


def resolve_menu(tenant, side: str) -> list[dict]:
    """Готовое дерево пунктов для стороны меню ('top' | 'bottom')."""
    cfg = siteconfig.normalize(tenant.site_config)["menus"].get(side, {})
    return [r for r in (_resolve(tenant, n) for n in cfg.get("items", [])) if r]


def top_meta(tenant) -> tuple[str, bool]:
    """(style, sticky) верхнего меню."""
    top = siteconfig.normalize(tenant.site_config)["menus"]["top"]
    return top["style"], top["sticky"]


def bottom_enabled(tenant) -> bool:
    return siteconfig.normalize(tenant.site_config)["menus"]["bottom"]["enabled"]
