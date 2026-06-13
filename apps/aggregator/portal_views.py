"""Страницы мульти-доменных порталов (P2.1b/c, config.urls_portal).

Корень портального хоста — листинги фильтра портала (city/business_type из
AggregatorPortal); /<facet>/ — уточнение по свободной оси: городской портал →
тип бизнеса, вертикальный → город, combo — без уточнения. Выборка —
listings_for() (общий пул AggregatorListing), пагинация курсорная (apps.core).
SEO (P2.1c): canonical + CollectionPage/ItemList JSON-LD + sitemap/robots по
хосту портала (домен из request, без django.contrib.sites — как в Track B5).
"""

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.core.pagecache import cache_public_page
from apps.core.pagination import paginate
from apps.core.seo import collectionpage_ld
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


def _facet_choices(portal) -> tuple[str | None, list[tuple[str, str]]]:
    """(ось, [(значение, подпись), …]) — значения свободной оси в пуле портала."""
    axis = _free_axis(portal)
    base = listings_for(city=portal.city or None, business_type=portal.business_type or None)
    if axis == "business_type":
        values = (
            base.exclude(business_type="")
            .values_list("business_type", flat=True)
            .distinct()
            .order_by("business_type")
        )
        return axis, [(v, _BTYPE_LABELS.get(v, v)) for v in values]
    if axis == "city":
        values = base.exclude(city="").values_list("city", flat=True).distinct().order_by("city")
        return axis, [(v, v) for v in values]
    return None, []


@cache_public_page
def portal_home(request, facet=None):
    portal = getattr(request, "portal", None)
    if portal is None:  # urlconf портала без резолва хоста (прямой вызов)
        raise Http404
    city = portal.city or None
    business_type = portal.business_type or None
    axis, facets = _facet_choices(portal)

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

    import json

    from . import geo
    from .views import split_featured

    pool = listings_for(city=city, business_type=business_type)
    near_lat, near_lng = geo.parse_latlng(request)
    if near_lat is not None:  # G8c: «рядом» — ближайшие сверху, без пагинации
        cards = geo.nearest(pool, near_lat, near_lng)
        page = None
    else:
        cursor = request.GET.get("cursor")
        featured, rest = split_featured(pool, first_page=not cursor)
        page = paginate(rest, order_field="created_at", limit=24, cursor=cursor)
        cards = featured + page.items  # продвинутые — сверху первой страницы (P2.4a)
    from . import reviews

    reviews.attach_ratings(cards)  # G8b: звёзды в выдаче
    canonical = request.build_absolute_uri(request.path)
    page_name = f"{facet_label} — {portal.title_text}" if facet_label else portal.title_text
    # Перелинковка сети (P2.2a): ссылки на остальные активные порталы.
    from .models import AggregatorPortal

    other_portals = [
        (f"{request.scheme}://{p.host}/", p.title_text)
        for p in AggregatorPortal.objects.filter(is_active=True).exclude(pk=portal.pk)[:12]
    ]
    # Сердечки избранного (P2.3b) — только вошедшим; анонимы получают эту
    # страницу из кэша (cache_public_page пропускает непустые сессии мимо).
    from . import auth
    from .models import FavoriteListing

    user = auth.current_portal_user(request)
    fav_ids = (
        set(FavoriteListing.objects.filter(user=user).values_list("listing_id", flat=True))
        if user
        else set()
    )
    return render(
        request,
        "aggregator/portal_home.html",
        {
            "portal": portal,
            "page": page,
            "cards": cards,
            "facets": facets,
            "facet": facet,
            "facet_label": facet_label,
            "business_link": True,  # G8b: на порталах звёзды ведут на страницу бизнеса
            "near_active": near_lat is not None,  # G8c
            "map_points_json": json.dumps(geo.map_points(cards)),
            "canonical": canonical,
            "other_portals": other_portals,
            "fav_ids": fav_ids,
            "ld_collection": collectionpage_ld(
                name=page_name,
                url=canonical,
                items=[(it.title_text, it.detail_url) for it in cards],
            ),
        },
    )


def portal_sitemap_xml(request):
    """Sitemap портала: корень + страницы уточнения по свободной оси."""
    from xml.sax.saxutils import escape

    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    urls = [request.build_absolute_uri(reverse("portal-home"))]
    _, facets = _facet_choices(portal)
    urls += [request.build_absolute_uri(reverse("portal-facet", args=[v])) for v, _label in facets]
    body = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return HttpResponse(xml, content_type="application/xml")


def portal_robots_txt(request):
    """robots.txt портала: всё открыто + ссылка на sitemap его хоста."""
    sitemap = request.build_absolute_uri(reverse("portal-sitemap"))
    return HttpResponse(f"User-agent: *\nAllow: /\nSitemap: {sitemap}\n", content_type="text/plain")
