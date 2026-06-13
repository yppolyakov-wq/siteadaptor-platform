"""Публичные страницы локального агрегатора (основной домен, public-схема).

Это «портал по умолчанию» над пулом AggregatorListing. Выборка — listings_for()
(seam для мульти-доменных порталов Phase 2 P2.1). Курсорная пагинация (apps.core).
"""

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.core.pagecache import cache_public_page
from apps.core.pagination import paginate
from apps.core.seo import itemlist_ld
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


def split_featured(qs, *, first_page: bool, limit: int = 6):
    """(featured, остальная лента) — платное продвижение (P2.4a).

    Featured закреплены сверху ПЕРВОЙ страницы выдачи (с бейджем) и исключены
    из обычной ленты, чтобы keyset-пагинация не давала дублей; на cursor-страницах
    блок не повторяется.
    """
    from django.utils import timezone

    featured_qs = qs.filter(featured_until__gt=timezone.now()).order_by("featured_until", "pk")
    featured = list(featured_qs[:limit]) if first_page else []
    rest = qs.exclude(pk__in=featured_qs.values_list("pk", flat=True))
    return featured, rest


@cache_public_page
def discover_index(request):
    cities = (
        AggregatorListing.objects.filter(is_active=True)
        .exclude(city="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )
    return render(request, "aggregator/index.html", {"cities": cities})


@cache_public_page
def city_listing(request, city, business_type=None):
    from . import geo

    pool = listings_for(city=city, business_type=business_type)
    near_lat, near_lng = geo.parse_latlng(request)
    if near_lat is not None:  # G8c: «рядом» — ближайшие сверху, без пагинации
        cards = geo.nearest(pool, near_lat, near_lng)
        page = None
    else:
        cursor = request.GET.get("cursor")
        featured, rest = split_featured(pool, first_page=not cursor)
        page = paginate(rest, order_field="created_at", limit=24, cursor=cursor)
        cards = featured + page.items  # продвинутые — сверху первой страницы
    types = (
        listings_for(city=city)
        .exclude(business_type="")
        .values_list("business_type", flat=True)
        .distinct()
        .order_by("business_type")
    )
    # Перелинковка (P2.2a): соседние города пула + брендированный портал города.
    from .models import AggregatorPortal

    other_cities = (
        AggregatorListing.objects.filter(is_active=True)
        .exclude(city="")
        .exclude(city__iexact=city)
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")[:12]
    )
    city_portal = AggregatorPortal.objects.filter(
        is_active=True, kind=AggregatorPortal.KIND_CITY, city__iexact=city
    ).first()
    import json

    from . import reviews

    reviews.attach_ratings(cards)  # G8b: звёзды в выдаче
    return render(
        request,
        "aggregator/listing.html",
        {
            "city": city,
            "business_type": business_type,
            "business_type_label": _BTYPE_LABELS.get(business_type, business_type),
            "types": [(t, _BTYPE_LABELS.get(t, t)) for t in types],
            "page": page,
            "cards": cards,
            "near_active": near_lat is not None,  # G8c
            "map_points_json": json.dumps(geo.map_points(cards)),
            "canonical": request.build_absolute_uri(request.path),
            "other_cities": other_cities,
            "city_portal_url": f"{request.scheme}://{city_portal.host}/" if city_portal else "",
            "city_portal_title": city_portal.title_text if city_portal else "",
            "ld_itemlist": itemlist_ld([(it.title_text, it.detail_url) for it in cards]),
        },
    )


def sitemap_xml(request):
    """Sitemap агрегатора (Track B5): /entdecken + города + город/тип.

    Карточки ведут на витрины тенантов (у каждой свой sitemap) — здесь только
    публичные посадочные страницы основного домена.
    """
    from xml.sax.saxutils import escape

    active = AggregatorListing.objects.filter(is_active=True)
    urls = [request.build_absolute_uri(reverse("aggregator-index"))]
    urls += [
        request.build_absolute_uri(reverse("aggregator-city", args=[c]))
        for c in active.exclude(city="").values_list("city", flat=True).distinct().order_by("city")
    ]
    urls += [
        request.build_absolute_uri(reverse("aggregator-city-type", args=[c, bt]))
        for c, bt in active.exclude(city="")
        .exclude(business_type="")
        .values_list("city", "business_type")
        .distinct()
        .order_by("city", "business_type")
    ]
    body = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return HttpResponse(xml, content_type="application/xml")


def robots_txt(request):
    """robots.txt основного домена: всё открыто + ссылка на sitemap агрегатора."""
    sitemap = request.build_absolute_uri(reverse("aggregator-sitemap"))
    return HttpResponse(f"User-agent: *\nAllow: /\nSitemap: {sitemap}\n", content_type="text/plain")
