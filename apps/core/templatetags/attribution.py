"""В5 V5-5: `{% portal_attribution_fields %}` — канал и карточку каталога города несут
скрытые поля формы (без cookie, решение владельца §13).

Источник — `attr` из контекста вьюхи, иначе ТОЛЬКО `request.GET`. Referer и сессию тег
не читает: страница без query может уйти в общий кэш, и чужой канал запёкся бы в неё.
Без валидных значений тег пуст — формы без атрибуции байт-в-байт прежние."""

from django import template
from django.utils.html import format_html_join

from apps.core import attribution

register = template.Library()


@register.simple_tag(takes_context=True)
def portal_attribution_fields(context):
    data = context.get("attr")
    if not data:
        request = context.get("request")
        data = getattr(request, "GET", None) or {}
    channel = attribution.clean_channel(data.get("ch"))
    if not channel:
        return ""
    pairs = [("ch", channel)]
    listing = attribution.clean_listing(data.get("cl"))
    if listing:
        pairs.append(("cl", listing))
    return format_html_join("", '<input type="hidden" name="{}" value="{}">', pairs)
