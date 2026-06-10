"""Страницы мульти-доменных порталов (P2.1b, config.urls_portal).

Корень портального хоста — листинги фильтра портала (city/business_type из
AggregatorPortal); /<facet>/ — уточнение по свободной оси: городской портал →
тип бизнеса, вертикальный → город, combo — без уточнения. Выборка —
listings_for() (общий пул AggregatorListing), пагинация курсорная (apps.core).
"""

from django.http import Http404
from django.shortcuts import render

from apps.core.pagination import paginate
from apps.tenants.models import Tenant

from .views import listings_for

_BTYPE_LABELS = dict(Tenant.BUSINESS_TYPES)


def _free_axis(portal) -> str | None:
    """Свободная ось уточнения портала: 'business_type' | 'city' | None (combo)."""
    if portal.city and not portal.business_type:
        return "business_type"
    if not portal.city:
        return "city"
    return None


def portal_home(request, facet=None):
    portal = getattr(request, "portal", None)
    if portal is None:  # urlconf портала без резолва хоста (прямой вызов)
        raise Http404
    city = portal.city or None
    business_type = portal.business_type or None

    # Чипы уточнения — значения свободной оси, реально присутствующие в пуле.
    axis = _free_axis(portal)
    base = listings_for(city=city, business_type=business_type)
    if axis == "business_type":
        values = (
            base.exclude(business_type="")
            .values_list("business_type", flat=True)
            .distinct()
            .order_by("business_type")
        )
        facets = [(v, _BTYPE_LABELS.get(v, v)) for v in values]
    elif axis == "city":
        values = base.exclude(city="").values_list("city", flat=True).distinct().order_by("city")
        facets = [(v, v) for v in values]
    else:
        facets = []

    facet_label = None
    if facet:
        known = {v.lower(): (v, label) for v, label in facets}
        if facet.lower() not in known:  # combo-портал или мусорный сегмент
            raise Http404
        facet, facet_label = known[facet.lower()]
        if axis == "business_type":
            business_type = facet
        else:
            city = facet

    page = paginate(
        listings_for(city=city, business_type=business_type),
        order_field="created_at",
        limit=24,
        cursor=request.GET.get("cursor"),
    )
    return render(
        request,
        "aggregator/portal_home.html",
        {
            "portal": portal,
            "page": page,
            "facets": facets,
            "facet": facet,
            "facet_label": facet_label,
        },
    )
