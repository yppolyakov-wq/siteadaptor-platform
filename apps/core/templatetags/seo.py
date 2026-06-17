"""Шаблонные теги SEO: LocalBusiness JSON-LD в <head> витрины (Track B5)."""

from django import template
from django.utils.safestring import mark_safe

from apps.core.seo import localbusiness_ld

register = template.Library()


def _tenant_rating():
    """(avg, count) рейтинга текущего тенанта из SHARED BusinessRating, или None.

    Ленивая зависимость на aggregator (импорт в теле функции) — core не тянет его
    на уровне модуля (иначе цикл: aggregator → core.seo). SEO не должен ронять
    <head>, поэтому ошибки гасим."""
    try:
        from django.db import connection

        from apps.aggregator.models import BusinessRating

        r = BusinessRating.objects.filter(
            tenant_schema=connection.schema_name, review_count__gt=0
        ).first()
        return (r.avg_rating, r.review_count) if r else None
    except Exception:  # noqa: BLE001 — SEO-обвязка не должна ломать страницу
        return None


@register.simple_tag
def business_rating():
    """(avg, count) рейтинга текущего тенанта или None — для звёзд на витрине (P3)."""
    return _tenant_rating()


@register.simple_tag(takes_context=True)
def localbusiness_jsonld(context):
    """Готовый <script type=application/ld+json> с LocalBusiness текущего тенанта.

    Тенант берём из request; вне витрины (нет request/tenant) — пусто. Если у
    бизнеса есть отзывы (G8) — добавляем AggregateRating (звёзды в сниппете).
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return ""
    payload = localbusiness_ld(
        tenant, url=request.build_absolute_uri("/"), aggregate_rating=_tenant_rating()
    )
    if not payload:
        return ""
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
