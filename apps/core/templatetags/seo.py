"""Шаблонные теги SEO: LocalBusiness JSON-LD в <head> витрины (Track B5)."""

from django import template
from django.utils.safestring import mark_safe

from apps.core.seo import localbusiness_ld

register = template.Library()


@register.simple_tag(takes_context=True)
def localbusiness_jsonld(context):
    """Готовый <script type=application/ld+json> с LocalBusiness текущего тенанта.

    Тенант берём из request; вне витрины (нет request/tenant) — пусто.
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return ""
    payload = localbusiness_ld(tenant, url=request.build_absolute_uri("/"))
    if not payload:
        return ""
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
