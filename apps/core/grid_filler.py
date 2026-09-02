"""DL-11 «Volle Reihen»: плитка-подсказка для неполного последнего ряда листинга.

На листингах (каталог, страница акций, наборы, «похожие товары») контент прятать
нельзя — там ряд добивается ОДНОЙ плиткой `.sf-filler` (всегда последний ребёнок
сетки). CSS (scripts/gen_fill_rows_css.py) растягивает её на остаток ряда на каждом
брейкпоинте и прячет, когда ряд и так полный. Содержимое — полезный CTA по гейтам
модулей: акции → рассылка → Merkzettel → заявка → сортимент → контакт (контакт есть
у каждого сайта → плитка никогда не бывает пустой).

`filler_for(kind, tenant)` → dict(key, kicker, title, text, url, label) | None.
Порядок кандидатов зависит от страницы (`kind`): на /aktionen/ звать на акции
бессмысленно, на каталоге — в первую очередь.
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.core import modules

ORDER = {
    "catalog": ("promotions", "newsletter", "wishlist", "anfrage", "contact"),
    "categories": ("promotions", "newsletter", "contact"),
    "promotions": ("newsletter", "wishlist", "catalog", "contact"),
    "combos": ("anfrage", "catalog", "contact"),
    "related": ("catalog", "promotions", "contact"),
    "default": ("catalog", "contact"),
}


def _url(name, fragment=""):
    try:
        return reverse(name) + fragment
    except NoReverseMatch:  # pragma: no cover — маршрут витрины всегда есть
        return ""


def _promotions(tenant):
    if not modules.is_module_active(tenant, "promotions"):
        return None
    from apps.promotions.models import Promotion

    if not Promotion.objects.filter(status="active").exists():
        return None
    return {
        "key": "promotions",
        "kicker": _("Aktionen"),
        "title": _("Aktuelle Angebote"),
        "text": _("Jede Woche neue Aktionen — reinschauen lohnt sich."),
        "url": _url("storefront-aktionen"),
        "label": _("Zu den Aktionen"),
    }


def _newsletter(tenant):
    # Страница /newsletter/ (DOI, UWG §7) есть у каждой витрины — модуля-гейта нет;
    # порядок кандидатов ставит её после акций, чтобы не звать в рассылку там, где
    # есть более сильное действие.
    return {
        "key": "newsletter",
        "kicker": _("Newsletter"),
        "title": _("Kein Angebot verpassen"),
        "text": _("Neue Aktionen direkt ins Postfach — jederzeit abbestellbar."),
        "url": _url("storefront-newsletter"),
        "label": _("Newsletter abonnieren"),
    }


def _wishlist(tenant):
    from apps.orders import wishlist

    if not wishlist.enabled(tenant):
        return None
    return {
        "key": "wishlist",
        "kicker": _("Merkzettel"),
        "title": _("Lieblinge merken"),
        "text": _("Angebote mit ♡ merken und später wiederfinden."),
        "url": _url("storefront-wishlist"),
        "label": _("Zum Merkzettel"),
    }


def _anfrage(tenant):
    if not modules.is_module_active(tenant, "jobs"):
        return None
    return {
        "key": "anfrage",
        "kicker": _("Anfrage"),
        "title": _("Nicht das Richtige dabei?"),
        "text": _("Schreiben Sie uns — wir machen Ihnen ein Angebot."),
        "url": _url("storefront-anfrage"),
        "label": _("Anfrage senden"),
    }


def _catalog(tenant):
    if not modules.is_module_active(tenant, "catalog"):
        return None
    return {
        "key": "catalog",
        "kicker": _("Sortiment"),
        "title": _("Ganzes Sortiment"),
        "text": _("Alle Kategorien und Produkte auf einen Blick."),
        "url": _url("storefront-products"),
        "label": _("Sortiment ansehen"),
    }


def _contact(tenant):
    return {
        "key": "contact",
        "kicker": _("Kontakt"),
        "title": _("Fragen? Wir helfen gern."),
        "text": _("Rufen Sie an oder schreiben Sie uns — wir melden uns schnell."),
        "url": _url("storefront-home", "#kontakt"),
        "label": _("Kontakt"),
    }


_RESOLVERS = {
    "promotions": _promotions,
    "newsletter": _newsletter,
    "wishlist": _wishlist,
    "anfrage": _anfrage,
    "catalog": _catalog,
    "contact": _contact,
}


def filler_for(kind, tenant, exclude=()):
    """Первая подходящая подсказка для страницы `kind`; `exclude` — ключи, которые на
    этой странице не нужны (напр. "catalog" на самом каталоге)."""
    for key in ORDER.get(kind, ORDER["default"]):
        if key in exclude:
            continue
        try:
            item = _RESOLVERS[key](tenant)
        except Exception:  # fail-safe: подсказка не имеет права ронять листинг
            item = None
        if item and item.get("url"):
            return item
    return _contact(tenant)
