"""Страницы мульти-доменных порталов (P2.1b/c, config.urls_portal).

Корень портального хоста — листинги фильтра портала (city/business_type из
AggregatorPortal); /<facet>/ — уточнение по свободной оси: городской портал →
тип бизнеса, вертикальный → город, combo — без уточнения. Выборка —
listings_for() (общий пул AggregatorListing), пагинация курсорная (apps.core).
SEO (P2.1c): canonical + CollectionPage/ItemList JSON-LD + sitemap/robots по
хосту портала (домен из request, без django.contrib.sites — как в Track B5).
"""

from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.pagecache import cache_public_page
from apps.core.pagination import paginate
from apps.core.seo import collectionpage_ld
from apps.tenants.models import Tenant

from .models import AggregatorListing
from .views import SEARCH_RATE_LIMIT, listings_for

_BTYPE_LABELS = dict(Tenant.BUSINESS_TYPES)

#: Некэшируемых рендеров портала (запросы с параметрами) на IP в минуту.
FEED_RATE_LIMIT = 120


def _free_axis(portal) -> str | None:
    """Свободная ось уточнения портала: 'business_type' | 'city' | None (combo)."""
    if portal.city and not portal.business_type:
        return "business_type"
    if not portal.city:
        return "city"
    return None


def _facet_choices(portal, district=None) -> tuple[str | None, list[tuple[str, str]]]:
    """(ось, [(значение, подпись), …]) — значения свободной оси в пуле портала."""
    axis = _free_axis(portal)
    base = listings_for(
        city=portal.city or None,
        business_type=portal.business_type or None,
        district=district,
        include_demo=portal.show_demo,
    )
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


def _district_choices(portal) -> list[tuple[str, str]]:
    """T-8.17: районы города портала, в которых есть предложения (пустой район —
    мёртвый чип, его не показываем). Порядок — официальный (реестр)."""
    from apps.core import districts

    known = districts.choices_for(portal.city)
    if not known:
        return []
    used = set(
        listings_for(
            city=portal.city,
            business_type=portal.business_type or None,
            include_demo=portal.show_demo,
        )
        .exclude(district="")
        .values_list("district", flat=True)
        .distinct()
    )
    return [(slug, name) for slug, name in known if slug in used]


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
def portal_home(request, facet=None, district=None):
    portal = getattr(request, "portal", None)
    if portal is None:  # urlconf портала без резолва хоста (прямой вызов)
        raise Http404
    from . import portal_home_blocks

    # Запрос с параметрами идёт мимо кэша публичных страниц и рендерит выборки заново —
    # общий лимит частоты на IP (мусорный `?x=` не должен бесплатно грузить БД).
    if request.GET:
        from apps.core import ratelimit

        if ratelimit.hit(
            "portal-feed",
            ratelimit.client_ip(request),
            limit=FEED_RATE_LIMIT,
            window=60,
        ):
            return HttpResponse(_("Zu viele Anfragen — bitte kurz warten."), status=429)
    if portal_home_blocks.is_home_request(portal, facet, district, request):
        return _render_home(request, portal)  # T-8.19: «Entdecke <город>»
    city = portal.city or None
    business_type = portal.business_type or None
    district_label = None
    if district is not None:  # T-8.17: /stadtteil/<slug>/
        from apps.core import districts

        district_label = districts.label(portal.city, district) if portal.city else ""
        if not district_label:
            raise Http404
    axis, facets = _facet_choices(portal, district=district)
    district_chips = _district_choices(portal)

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

    # T-8.13a: категория/признак каталога города — параметрами, чипы по НЕфильтрованному пулу.
    from dataclasses import replace

    from apps.core.pagination import paginate_ranked

    from . import category_facets, geo
    from . import portal_home_blocks as home
    from . import search as search_engine
    from .views import split_featured

    # T-8.19/T-8.20: поиск и фильтры — ограничение частоты до любых выборок (как /entdecken/).
    q = home.search_query(request)
    filters = search_engine.parse_filters(request, city=city or "")
    if district:  # путь /stadtteil/<slug>/ сильнее параметра
        filters = replace(filters, district="")
    if q or filters.active:
        from apps.core import ratelimit

        if ratelimit.hit(
            "portal-search",
            ratelimit.client_ip(request),
            limit=SEARCH_RATE_LIMIT,
            window=60,
        ):
            return HttpResponse(_("Zu viele Anfragen — bitte kurz warten."), status=429)
    scope = home.parse_scope(request)
    kat, tag = scope.kat, scope.tag
    # T-8.11/T-8.19: вид — лента предложений по умолчанию (акции/номера/события/меню);
    # вкладки `?kind=` — группы (alle/angebote) или один вид. Поиск без вида — по всем
    # видам: «Brot» обязан находить товары.
    kind = scope.kind_key or ("alle" if q else "")
    kinds = home.kinds_for(kind) or AggregatorListing.OFFER_KINDS
    # T-8.20: единый поиск — режим (полнотекст/опечатки) решается ОДИН раз по пулу без
    # вида и категорий; от него же вкладки, чипы и выдача (иначе вкладка «0», а лента нашла).
    broad = search_engine.execute(
        listings_for(
            city=city,
            business_type=business_type,
            district=district,
            include_demo=portal.show_demo,
        ),
        q,
        replace(filters, kats=(), tags=()),
        surface="portal",
        track=False,
    )
    whole_pool = broad.qs
    # Параметры поиска/фильтров (кроме категорий) — в ссылках вкладок, чипов и формы.
    carry = [(k, v) for k, v in search_engine.carry(q, filters) if k not in ("kat", "merkmal")]
    city_home = home.has_home(portal)
    if city_home:  # T-8.19: вкладки главной вместо чипов видов
        kind_chips = []
        portal_tabs = home.tabs(home.presence(whole_pool), kind, request.path, carry=carry)
    else:
        kind_chips = _kind_chips(whole_pool.order_by(), request.path, kind)
        portal_tabs = []
    base_pool = home.apply_scope(
        whole_pool.filter(listing_kind__in=kinds),
        home.FeedScope(new_only=scope.new_only),
    )
    category_chips = category_facets.chips(
        base_pool.order_by(),  # без ранга: чипам нужен только состав
        request.path,
        kat,
        tag,
        extra={"kind": scope.kind_key, "neu": "1" if scope.new_only else "", **dict(carry)},
    )
    pool = search_engine.apply_filters(
        base_pool, search_engine.SearchFilters(kats=filters.kats, tags=filters.tags)
    )
    search_engine.record(
        search_engine.SearchOutcome(pool, broad.mode, q, broad.ranked, filters, lang=broad.lang),
        surface="portal",
        city=city or "",
        portal_host=portal.host,
        first_page=not request.GET.get("cursor"),  # листание выдачи — не новый поиск
    )
    near_lat, near_lng = geo.parse_latlng(request)
    if near_lat is not None:  # G8c: «рядом» — ближайшие сверху, без пагинации
        cards = geo.nearest(pool, near_lat, near_lng)
        page = None
    else:
        cursor = request.GET.get("cursor")
        featured, rest = split_featured(pool, first_page=not cursor)
        if broad.ranked:  # T-8.20: релевантность — offset-курсор того же вида
            page = paginate_ranked(
                rest, limit=24, cursor=cursor, max_results=settings.AGGREGATOR_SEARCH["max_results"]
            )
        else:
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
    heading = " · ".join(
        str(p) for p in (district_label, facet_label, category_chips["label"]) if p
    )
    page_name = f"{heading} — {portal.title_text}" if heading else portal.title_text
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
            "heading": heading,
            "district": district,
            "district_label": district_label,
            "district_chips": district_chips,
            "category_chips": category_chips,  # T-8.13a
            "kind_chips": kind_chips,  # T-8.11
            "portal_tabs": portal_tabs,  # T-8.19
            "search_q": q,
            "search_kind": scope.kind_key,
            "search_mode": broad.mode,
            # T-8.20: новый запрос не сбрасывает вкладку и фильтры.
            "search_hidden": [
                (k, v)
                for k, v in [
                    ("kind", scope.kind_key if scope.kind_key != "alle" else ""),
                    ("neu", "1" if scope.new_only else ""),
                ]
                + search_engine.carry("", filters)
                if v
            ],
            # T-8.20: блок фильтров и пилюли активных фильтров (только у городского портала).
            "filter_panel": _filter_panel(request, portal, filters, q, scope, district)
            if city_home
            else None,
            # «Weitere» несёт текущие фильтры (вид/категорию/признак), иначе вторая
            # страница показывала бы неотфильтрованную ленту.
            "page_carry": urlencode(
                [
                    (k, v)
                    for k, v in (("kind", scope.kind_key), ("neu", "1" if scope.new_only else ""))
                    if v
                ]
                + search_engine.carry(q, filters)
            ),
            # T-8.15: портал показывает демо-бизнесы — честная полоса «Vorschau».
            "shows_demo": portal.show_demo and any(getattr(c, "is_demo", False) for c in cards),
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


def _filter_panel(request, portal, filters, q: str, scope, district) -> dict:
    """T-8.20: блок фильтров ленты (без JS) и пилюли активных фильтров с ✕."""
    from . import search as search_engine

    keep = [("kind", scope.kind_key)] if scope.kind_key else []
    if scope.new_only:
        keep.append(("neu", "1"))
    params = keep + search_engine.carry(q, filters)

    def without(*names: str, value: str = "") -> str:
        rest = [(k, v) for k, v in params if not (k in names and (not value or v == value))]
        return f"{request.path}?{urlencode(rest)}" if rest else request.path

    from apps.core import city_categories as cc

    labels = {
        "heute": _("Heute"),
        "wochenende": _("Am Wochenende"),
    }
    pills = []
    for kat in filters.kats if len(filters.kats) > 1 else ():
        pills.append({"label": cc.label(kat), "url": without("kat", value=kat)})
    if filters.district:
        from apps.core import districts

        pills.append(
            {
                "label": districts.label(portal.city, filters.district) or filters.district,
                "url": without("stadtteil"),
            }
        )
    from django.utils.formats import number_format

    if filters.price_from is not None:
        price = number_format(filters.price_from, 2)
        pills.append({"label": _("ab %(p)s €") % {"p": price}, "url": without("preis_von")})
    if filters.price_to is not None:
        price = number_format(filters.price_to, 2)
        pills.append({"label": _("bis %(p)s €") % {"p": price}, "url": without("preis_bis")})
    if filters.date:
        pills.append({"label": labels.get(filters.date, filters.date), "url": without("datum")})
    if filters.available:
        pills.append({"label": _("Nur verfügbar"), "url": without("verfuegbar")})
    if filters.open_now:
        pills.append({"label": _("Jetzt geöffnet"), "url": without("offen")})
    hidden = [
        (k, v)
        for k, v in keep + search_engine.carry(q, filters)
        if k in ("kind", "neu", "q", "kat", "merkmal")
    ]
    return {
        "filters": filters,
        "districts": [] if district else _district_choices(portal),
        "hidden": hidden,
        "pills": pills,
        "reset_url": without(*search_engine.FILTER_PARAMS),
        "open": filters.active or bool(filters.sort),
    }


def _other_portals(request, portal) -> list[tuple[str, str]]:
    from .models import AggregatorPortal

    return [
        (f"{request.scheme}://{p.host}/", p.title_text)
        for p in AggregatorPortal.objects.filter(is_active=True).exclude(pk=portal.pk)[:12]
    ]


def _fav_ids(request) -> set:
    from . import auth
    from .models import FavoriteListing

    user = auth.current_portal_user(request)
    if not user:
        return set()
    return set(FavoriteListing.objects.filter(user=user).values_list("listing_id", flat=True))


def _render_home(request, portal):
    """T-8.19: «Entdecke <город>» — поиск, вкладки, плитки разделов, «Anzeigen», блоки.

    Число запросов не зависит от объёма данных: presence (1), featured (≤2), блоки (по 1),
    рейтинги (1), районы, «Branche», другие порталы. Корень без query кэшируется.
    """
    from . import portal_home_blocks as home
    from . import reviews

    base = listings_for(city=portal.city, include_demo=portal.show_demo)
    present = home.presence(base)
    # Показы платных позиций считаем только на «чистом» корне (кэшируемый рендер):
    # иначе боты с `?x=<мусор>` накручивали бы метрику, которую видят владельцы.
    featured = home.featured(base, count_impressions=not request.GET) if present["total"] else []
    blocks = (
        home.home_blocks(
            base,
            city=portal.city,
            path=request.path,
            exclude_pks={item.pk for item in featured},
        )
        if present["total"]
        else []
    )
    cards = featured + [item for b in blocks for item in b["items"]]
    reviews.attach_ratings(cards)
    _axis, facets = _facet_choices(portal)
    canonical = request.build_absolute_uri(request.path)
    return render(
        request,
        "aggregator/portal_discover.html",
        {
            "portal": portal,
            "portal_tabs": home.tabs(present, "alle", request.path),
            "pool_empty": not present["total"],
            "tiles": home.section_tiles(present, request.path),
            "featured": featured,
            "blocks": blocks,
            "facets": facets,
            "district_chips": _district_choices(portal),
            "shows_demo": portal.show_demo and any(getattr(c, "is_demo", False) for c in cards),
            "business_link": True,
            "canonical": canonical,
            "other_portals": _other_portals(request, portal),
            "fav_ids": _fav_ids(request),
            "ld_collection": collectionpage_ld(
                name=portal.title_text,
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
    urls += [
        request.build_absolute_uri(reverse("portal-district", args=[slug]))
        for slug, _name in _district_choices(portal)
    ]
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


def _kind_chips(pool, path: str, active: str) -> list[dict]:
    """T-8.11: «Angebote · Produkte · Dienstleistungen · Unternehmen» — только непустые."""
    from urllib.parse import urlencode

    from .views import _KIND_LABELS

    present = set(pool.values_list("listing_kind", flat=True).distinct())
    offers = present & set(AggregatorListing.OFFER_KINDS)
    groups = [("", _("Angebote"), bool(offers))]
    for value, label in _KIND_LABELS:
        if value in (
            AggregatorListing.KIND_PRODUCT,
            AggregatorListing.KIND_SERVICE,
            AggregatorListing.KIND_BUSINESS,
        ):
            groups.append((value, _(label), value in present))
    shown = [(v, label) for v, label, has in groups if has]
    if len(shown) < 2:  # одна группа — переключать нечего
        return []
    return [
        {
            "key": v or "offers",
            "label": label,
            "url": f"{path}?{urlencode({'kind': v})}" if v else path,
            "active": v == active,
        }
        for v, label in shown
    ]
