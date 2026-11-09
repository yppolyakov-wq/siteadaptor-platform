"""Теги бренда портала (PH-1): вордмарк «<Город>Markt»."""

from django import template

from apps.aggregator import branding

register = template.Library()


@register.simple_tag
def portal_wordmark(portal):
    """{"dark", "accent"}: «SolingenMarkt» → «Solingen» + «Markt»; иначе весь заголовок акцентом."""
    if portal is None:
        return {"dark": "", "accent": ""}
    dark, accent = branding.wordmark(portal.title_text, getattr(portal, "city", ""))
    return {"dark": dark, "accent": accent}


@register.simple_tag
def portal_districts(portal):
    """PH-11a: районы города портала для «Wo» шапки — [(slug, name)] из реестра, без БД."""
    from apps.core import districts

    if not portal:
        return []
    return [(d.slug, d.name) for d in districts.districts_for(getattr(portal, "city", ""))]


@register.filter
def card_action(kind):
    """PH-3: подпись пилюли действия карточки по виду листинга."""
    from apps.aggregator.portal_cards import action_label

    return action_label(kind or "")


@register.filter
def card_action_for(listing):
    """PH-9: подпись пилюли по отклику акции (если есть), иначе по виду."""
    from apps.aggregator.portal_cards import card_action

    return card_action(listing)


@register.filter
def few_left(listing):
    """PH-9: остаток лимита акции, если он мал (≤10) — иначе None."""
    from apps.aggregator.portal_cards import REMAINING_SHOW

    n = getattr(listing, "remaining", None)
    return n if n and n <= REMAINING_SHOW else None


FOOTER_CACHE = 5 * 60


@register.simple_tag
def portal_footer(portal):
    """PH-11e (макет K1): данные тёмного подвала — виды, по которым есть предложения, отрасли
    («Branche») и районы с предложениями. Подвал на КАЖДОЙ странице портала: кэш на портал и
    язык 5 минут (как мега-меню), fail-open. Только ссылки на непустые ленты — мёртвых нет."""
    if not portal:
        return {}
    from django.core.cache import cache
    from django.utils.translation import get_language

    key = f"portal_footer:{portal.pk}:{get_language() or ''}"
    try:
        data = cache.get(key)
    except Exception:  # noqa: BLE001 — кэш недоступен: считаем напрямую
        data = None
    if data is not None:
        return data
    data, ttl = _footer_data(portal), FOOTER_CACHE
    if data is None:  # ошибка БД: подвал на КАЖДОЙ странице — не роняем страницу, пусто ненадолго
        data, ttl = {"kinds": [], "districts": []}, 30
    try:
        cache.set(key, data, ttl)
    except Exception:  # noqa: BLE001
        pass
    return data


def _footer_data(portal) -> dict | None:
    """Ссылки подвала (запросы к БД). None — ошибка: вызывающий отдаёт пустой подвал."""
    import logging

    from django.urls import reverse

    from apps.aggregator import portal_home_blocks as home
    from apps.aggregator import portal_scope, portal_views
    from apps.aggregator.platform_links import platform_url

    try:
        home_url = reverse("portal-home")
        kinds = set(
            portal_scope.pool(portal).order_by().values_list("listing_kind", flat=True).distinct()
        )
        return {
            "kinds": [
                {
                    "label": str(t.label),
                    "url": home.scope_url(home_url, home.FeedScope(kind_key=t.key)),
                }
                for t in home.TABS
                if t.key != "alle" and kinds & set(t.kinds)
            ],
            "districts": portal_views._district_choices(portal),
            "start_url": platform_url("quick-start"),
            "agb_url": platform_url("platform-agb"),
        }
    except Exception:  # noqa: BLE001 — подвал не должен ронять страницу
        logging.getLogger(__name__).exception("portal_footer: data failed")
        return None


CURRENCY_SIGNS = {"EUR": "€", "GBP": "£", "USD": "$"}


@register.filter
def currency_sign(code):
    """Видимая цена: «5,00 €», а не «5,00 EUR» (прод-разбор PH-10). Машиночитаемое (JSON-LD,
    фид) остаётся кодом ISO; неизвестная валюта (CHF) — кодом."""
    code = (code or "").strip()
    return CURRENCY_SIGNS.get(code.upper(), code)


@register.simple_tag
def portal_colors(portal):
    """PH-12b: цвета портала для `:root` — бренд (только `#rrggbb`, иначе тёмный — защита от
    CSS-инъекции из админки), чернила поверх бренда (≥ 4,5:1) и цвет ссылок на белом."""
    from apps.core import colors

    color = colors.normalize_hex(getattr(portal, "primary_color", "") if portal else "")
    return {
        "color": color,
        "ink": colors.ink_on(color),
        "link": colors.readable_on_white(color),
    }
