"""Публичные страницы локального агрегатора (основной домен, public-схема).

Это «портал по умолчанию» над пулом AggregatorListing. Выборка — listings_for()
(seam для мульти-доменных порталов Phase 2 P2.1). Курсорная пагинация (apps.core).
"""

from django.shortcuts import render

from apps.core.pagination import paginate
from apps.tenants.models import Tenant

from .models import AggregatorListing

_BTYPE_LABELS = dict(Tenant.BUSINESS_TYPES)


def listings_for(*, city=None, business_type=None):
    """Активные листинги по фильтру. Переиспользуется порталами Phase 2."""
    qs = AggregatorListing.objects.filter(is_active=True)
    if city:
        qs = qs.filter(city__iexact=city)
    if business_type:
        qs = qs.filter(business_type=business_type)
    return qs


def discover_index(request):
    cities = (
        AggregatorListing.objects.filter(is_active=True)
        .exclude(city="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )
    return render(request, "aggregator/index.html", {"cities": cities})


def city_listing(request, city, business_type=None):
    page = paginate(
        listings_for(city=city, business_type=business_type),
        order_field="created_at",
        limit=24,
        cursor=request.GET.get("cursor"),
    )
    types = (
        listings_for(city=city)
        .exclude(business_type="")
        .values_list("business_type", flat=True)
        .distinct()
        .order_by("business_type")
    )
    return render(
        request,
        "aggregator/listing.html",
        {
            "city": city,
            "business_type": business_type,
            "business_type_label": _BTYPE_LABELS.get(business_type, business_type),
            "types": [(t, _BTYPE_LABELS.get(t, t)) for t in types],
            "page": page,
        },
    )
