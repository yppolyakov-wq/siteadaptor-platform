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


def _collapse_hotels(cards):
    """H8a: для hotel-портала схлопнуть листинги номеров (KIND_STAY) в одну карточку
    на отель — дешёвый номер («ab …€») как представитель, заголовок = имя отеля,
    ``room_count`` = сколько типов номеров. Не-stay карточки проходят как есть.
    Порядок — по первому появлению (featured/гео сохраняются)."""
    out, by_tenant = [], {}
    for c in cards:
        if c.listing_kind != c.KIND_STAY:
            out.append(c)
            continue
        key = c.tenant_schema
        rep = by_tenant.get(key)
        if rep is None:
            c.room_count = 1
            c.title = {"de": c.business_name}  # карточка про отель, не про номер
            by_tenant[key] = c
            out.append(c)
        else:
            rep.room_count += 1
            # дешевейший номер как «ab …€»
            if c.new_price is not None and (rep.new_price is None or c.new_price < rep.new_price):
                rep.new_price = c.new_price
                rep.detail_url = c.detail_url
    return out


def _with_dates(url, von, bis, guests):
    """Добавить даты/гостей к ссылке на отель (H8b) — глубокая ссылка в прямое
    бронирование с предзаполненным диапазоном."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}von={von.isoformat()}&bis={bis.isoformat()}&erw={guests}"


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
    # H8a: вертикальный hotel-портал — карточка на отель (а не на каждый номер).
    hotel_portal = (portal.business_type or business_type) == "hotel"
    search = None
    if hotel_portal:
        cards = _collapse_hotels(cards)
        # H8b: живой поиск по датам — оставляем только отели со свободными номерами.
        from django.utils import timezone

        from . import hotel_search

        von = hotel_search.parse_date(request.GET.get("von"))
        bis = hotel_search.parse_date(request.GET.get("bis"))
        try:
            g = max(1, min(int(request.GET.get("gaeste", "2")), 50))
        except (TypeError, ValueError):
            g = 2
        if von and bis and bis > von and von >= timezone.localdate():
            search = {"von": von, "bis": bis, "guests": g, "nights": (bis - von).days}
            kept = []
            for c in cards:
                ok, cents = hotel_search.hotel_availability(c.tenant_schema, von, bis, g)
                if ok:
                    c.range_total_eur = cents / 100
                    c.range_nights = search["nights"]
                    c.detail_url = _with_dates(c.detail_url, von, bis, g)
                    kept.append(c)
            cards = kept
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
            "hotel_portal": hotel_portal,  # H8b: показать форму поиска по датам
            "search": search,  # H8b: выбранный диапазон/гости (или None)
            "facets": facets,
            "facet": facet,
            "facet_label": facet_label,
            "business_link": True,  # G8b: на порталах звёзды ведут на страницу бизнеса
            "near_active": near_lat is not None,  # G8c
            "map_points": geo.map_points(cards),
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
