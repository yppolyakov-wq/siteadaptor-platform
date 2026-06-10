"""Резолвер мульти-доменных порталов агрегатора (P2.1a/b).

На public-схеме сопоставляет request.get_host() → AggregatorPortal: кладёт его в
request.portal и подменяет request.urlconf на config.urls_portal (корень хоста =
страницы портала). Карта host→id кэшируется в Redis и сбрасывается сигналом при
изменении портала (см. apps.py::ready). На субдоменах бизнеса (tenant-схема) и
на основном домене без портала request.portal = None — поведение текущих
страниц не меняется.
"""

from django.core.cache import cache
from django_tenants.utils import get_public_schema_name

_CACHE_KEY = "aggregator:portal_host_map"
_CACHE_TTL = 300  # сек; плюс явный сброс сигналом при save/delete портала


def portal_host_map() -> dict:
    """{host(lower): portal_id} активных порталов. Кэш в Redis (TTL + сигнал)."""
    mapping = cache.get(_CACHE_KEY)
    if mapping is None:
        from .models import AggregatorPortal

        mapping = {
            host.lower(): pid
            for host, pid in AggregatorPortal.objects.filter(is_active=True).values_list(
                "host", "id"
            )
        }
        cache.set(_CACHE_KEY, mapping, _CACHE_TTL)
    return mapping


def clear_portal_cache(**_kwargs) -> None:
    """Сигнал-обработчик: сбросить карту host→портал."""
    cache.delete(_CACHE_KEY)


def resolve_portal(request):
    """AggregatorPortal для запроса либо None. Только на public-схеме."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or tenant.schema_name != get_public_schema_name():
        return None
    host = request.get_host().split(":")[0].lower()
    portal_id = portal_host_map().get(host)
    if portal_id is None:
        return None
    from .models import AggregatorPortal

    return AggregatorPortal.objects.filter(pk=portal_id, is_active=True).first()


class AggregatorPortalMiddleware:
    """Кладёт request.portal (+ urlconf портала). Сразу после TenantMainMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal = resolve_portal(request)
        if request.portal is not None:
            request.urlconf = "config.urls_portal"
        return self.get_response(request)
