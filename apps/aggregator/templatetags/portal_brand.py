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
