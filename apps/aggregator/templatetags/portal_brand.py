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
