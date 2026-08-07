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
    # ST-8: отдельные страницы. Ссылка ставится ТОЛЬКО при наличии контента —
    # см. _page_has_content: пустая страница отдаёт 404, поэтому и пункт меню
    # на неё вести не должен.
    "gallery": "storefront-gallery",
    "team": "storefront-team",
    "reviews": "storefront-reviews",
    # 2026-08-06 (аудит демо): существующие страницы витрины, до которых не было
    # НИ ОДНОГО пути из меню — посетитель мог попасть только по прямой ссылке.
    "loyalty": "storefront-loyalty",  # /treue/ — бонусная программа
    "gift": "storefront-gutschein",  # /gutschein/ — подарочные сертификаты
    "combos": "storefront-combos",  # /kombi/ — наборы
    "finder": "storefront-finder",  # /finder/ — подбор «3 вопроса»
    "wishlist": "storefront-wishlist",  # /merkzettel/ — избранное
    "account": "account-home",  # /konto/ — личный кабинет клиента
    # Кит TOURS ссылался на страницу "contact" — цели с таким именем не было,
    # и пункт молча выпадал из меню (узел без ссылки отбрасывается).
    "contact": "storefront-message",  # /nachricht/ — форма связи
}

# Гейт по МОДУЛЮ для страниц, у которых он есть (пункт гаснет при выключенном
# модуле — как у archetype-узлов). Ключ = target страницы.
_PAGE_MODULE_GATES = {
    "loyalty": "loyalty",
    "gift": "gift",
    "combos": "orders",
    # finder — ОПЦИЯ, а не модуль реестра: у него свой гейт finder.enabled ниже
    # (is_module_active("finder") всегда False и гасил бы пункт).
    "wishlist": "orders",
    "account": "customer_account",
    "contact": "inbox",
}

# ST-8: чем «наполнена» страница (ключ site_config или запрос) — гейт пункта меню.
_PAGE_CONTENT_GATES = ("gallery", "team", "reviews", "combos")


def _page_has_content(tenant, target: str) -> bool:
    """Есть ли что показать на странице ST-8 (иначе пункт меню гасим)."""
    if target not in _PAGE_CONTENT_GATES:
        return True
    if target == "combos":
        # Модуль orders активен почти у всех, но наборы есть у единиц — без этого
        # гейта пункт «Kombi-Angebote» встал бы в шапку каждого тенанта и вёл на
        # пустую страницу.
        from apps.catalog.combos import active_combos

        return bool(active_combos())
    cfg = siteconfig.normalize(tenant.site_config)
    if target == "gallery":
        return bool(cfg.get("gallery") or cfg.get("gallery_video"))
    if target == "team":
        return bool(cfg.get("team"))
    # reviews: два источника — портальные отзывы (SHARED-модель, читаем тем же
    # тегом: он сам гасит ошибки и не роняет меню) и кураторские `testimonials`.
    if cfg.get("testimonials"):
        return True
    from apps.core.templatetags.seo import storefront_reviews

    return bool(storefront_reviews(1))


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
        if not name or not _page_has_content(tenant, target):
            return None
        gate = _PAGE_MODULE_GATES.get(target)
        if gate and not modules.is_module_active(tenant, gate):
            return None
        if target == "finder":
            from apps.core import finder as _finder

            if not _finder.enabled(tenant):
                return None
        return _reverse(name)
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
    # ST-8: подписи новых страниц (галерея/отзывы/команда) в демо-меню.
    _("Unser Team"),
    _("Meister"),
    _("Referenzen"),
    # 2026-08-06 (аудит демо): 23 подписи демо-меню не были объявлены здесь и
    # потому оставались немецкими на всех языках витрины.
    _("Damen"),
    _("Herren"),
    _("Accessoires"),
    _("Shop"),
    _("Catering"),
    _("Retreats"),
    _("Touren"),
    _("Events & Ausflüge"),
    _("Wellness & Extras"),
    _("Treue & Aktionen"),
    _("Einzelsitzung"),
    _("Sitzung"),
    _("Lehrer"),
    _("Teile"),
    _("Partyservice"),
    _("Party"),
    _("Korb"),
    _("Vorbestellung"),
    _("Wochenangebote"),
    _("Hausmacher-Wochen"),
    _("Dauertiefpreis"),
    _("Anti-Food-Waste"),
    _("Räumung"),
    # Аудит 2026-08-06: размещение ретрита в меню (номера/места в общей комнате).
    _("Unterkunft"),
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
