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

# Подписи видов листинга для чипов фильтра (A5/A6). DE — рынок DACH.
_KIND_LABELS = [
    (AggregatorListing.KIND_PROMOTION, "Angebote"),
    (AggregatorListing.KIND_STAY, "Übernachten"),
    (AggregatorListing.KIND_EVENT, "Events"),
]


def listings_for(*, city=None, business_type=None, q=None, kind=None, category=None, month=None):
    """Активные листинги по фильтру. Переиспользуется порталами Phase 2.

    q — текстовый поиск (P2.7) по названию бизнеса, заголовку акции и городу;
    icontains по JSON-полю title матчит сериализованный текст (для v1 достаточно).
    kind — вид листинга (promotion/stay/event, A5/A6); пусто = все.
    category (R2b) — направление/тема event-листинга (yoga/meditation/…).
    month (R2b) — «YYYY-MM»: листинги, стартующие в этом месяце (для ретритов).

    Прошедшие события (event со starts_at в прошлом) скрываем всегда — sync
    удаляет их по правке, но дата может «истечь» без события-триггера.
    """
    from django.db.models import Q
    from django.utils import timezone

    qs = AggregatorListing.objects.filter(is_active=True)
    if city:
        qs = qs.filter(city__iexact=city)
    if business_type:
        qs = qs.filter(business_type=business_type)
    if kind:
        qs = qs.filter(listing_kind=kind)
    if category:
        qs = qs.filter(category__iexact=category)
    if month and "-" in month:
        year, mon = month.split("-", 1)
        if year.isdigit() and mon.isdigit():
            qs = qs.filter(starts_at__year=int(year), starts_at__month=int(mon))
    if q:
        qs = qs.filter(Q(business_name__icontains=q) | Q(title__icontains=q) | Q(city__icontains=q))
    # Истёкшие события вон (у прочих видов starts_at либо null, либо окно акции).
    qs = qs.exclude(listing_kind=AggregatorListing.KIND_EVENT, starts_at__lt=timezone.now())
    return qs


def _distinct_event_categories():
    """Присутствующие направления event-листингов → [(key, label)] (R2b)."""
    from apps.events import taxonomy

    present = set(
        AggregatorListing.objects.filter(is_active=True)
        .exclude(category="")
        .values_list("category", flat=True)
        .distinct()
    )
    return [(k, v) for k, v in taxonomy.CATEGORIES if k in present]


# A8: сортировки выдачи города. Значение → (поле keyset-пагинации, по убыванию?).
# Только поля, существующие на AggregatorListing (keyset-совместимы).
_LISTING_SORTS = {
    "neueste": ("created_at", True),  # дефолт — новые сверху
    "name": ("business_name", False),  # A–Z
}

# A8: пороги фасета рейтинга (минимум звёзд). Только эти значения принимаем.
_RATING_THRESHOLDS = (3, 4, 5)


def _rating_schemas(min_rating: int) -> set:
    """A8: схемы с avg_rating ≥ min_rating (и ≥1 отзыв) — фасет «рейтинг».

    BusinessRating денормализован в public-схеме по tenant_schema, поэтому фасет
    сводится к `tenant_schema__in=<множество>` — keyset-пагинация не ломается.
    """
    from .models import BusinessRating

    return set(
        BusinessRating.objects.filter(avg_rating__gte=min_rating, review_count__gt=0).values_list(
            "tenant_schema", flat=True
        )
    )


def _open_now_schemas(schemas) -> set:
    """A8: подмножество схем, открытых прямо сейчас (Tenant.opening_hours_structured).

    Часы живут на SHARED Tenant (public-схема) — вычисляем live-статус для схем,
    присутствующих в пуле, и возвращаем открытые (тоже сводится к tenant_schema__in).
    """
    from django.utils import timezone

    from apps.tenants import openinghours

    now = timezone.localtime()
    out = set()
    rows = Tenant.objects.filter(schema_name__in=set(schemas)).values_list(
        "schema_name", "opening_hours_structured"
    )
    for schema, structured in rows:
        status = openinghours.open_status(structured, now)
        if status and status.get("open"):
            out.add(schema)
    return out


def _attach_open_status(cards):
    """A8: прикрепить к карточкам live-статус «Jetzt geöffnet» (богатая карточка бизнеса).

    Часы на SHARED Tenant (public-схема); один запрос на схемы пула. Поля карточки:
    `has_hours` (часы заданы), `open_now` (открыт сейчас), `open_until` («bis HH:MM»
    для открытых), `opens_next` («Mo 09:00» — ближайшее открытие для закрытых).
    Бизнес без часов — без бейджа (не зашумляет).
    """
    if not cards:
        return cards
    from django.utils import timezone

    from apps.tenants import openinghours

    now = timezone.localtime()
    hours = dict(
        Tenant.objects.filter(schema_name__in={c.tenant_schema for c in cards}).values_list(
            "schema_name", "opening_hours_structured"
        )
    )
    for card in cards:
        status = openinghours.open_status(hours.get(card.tenant_schema), now)
        card.has_hours = status is not None
        card.open_now = bool(status and status.get("open"))
        card.open_until = (status.get("until") or "") if status else ""
        nxt = status.get("next") if status else None
        card.opens_next = f"{nxt[0]} {nxt[1]}" if nxt else ""
    return cards


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
    if featured:
        # D2.3: показ featured-блока = импрессия (F-инкремент, без гонок).
        from django.db.models import F

        AggregatorListing.objects.filter(pk__in=[item.pk for item in featured]).update(
            featured_impressions=F("featured_impressions") + 1
        )
    return featured, rest


def featured_click(request, pk):
    """D2.3: клик по featured-позиции — счётчик + редирект на листинг.

    Инкремент только пока позиция оплачена (is_featured_now). detail_url —
    URLField из sync-задач; не-http значение (мусор) → на /entdecken.
    Роут зарегистрирован под одним именем в urls_public И urls_portal.
    """
    from django.db.models import F
    from django.shortcuts import redirect

    listing = AggregatorListing.objects.filter(pk=pk, is_active=True).first()
    if listing is None:
        return redirect("/")  # корень валиден и на /entdecken-домене, и на портале
    if listing.is_featured_now:
        AggregatorListing.objects.filter(pk=pk).update(featured_clicks=F("featured_clicks") + 1)
    url = listing.detail_url or ""
    if not url.startswith(("http://", "https://", "/")):
        return redirect("/")
    return redirect(url)


def _distinct_cities():
    return (
        AggregatorListing.objects.filter(is_active=True)
        .exclude(city="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )


def _distinct_types():
    types = (
        AggregatorListing.objects.filter(is_active=True)
        .exclude(business_type="")
        .values_list("business_type", flat=True)
        .distinct()
        .order_by("business_type")
    )
    return [(t, _BTYPE_LABELS.get(t, t)) for t in types]


@cache_public_page
def platform_finder(request):
    """FD-4: диалоговый подбор «2 вопроса → 3 Angebote» на /entdecken/finder/.

    Серверные шаги без JS (зеркало тенантского /finder/): ?typ= → ?stadt=;
    невалидное значение = возврат на шаг. cache_public_page кэширует только
    GET без query → закэширован лишь шаг 1, выдача всегда свежая. Выдача
    органическая (UWG §5a — платное не переприоритизируется, метка
    «★ Anzeige» из общего партиала карточек)."""
    from . import finder as agg_finder
    from . import reviews

    state = agg_finder.resolve_public(
        (request.GET.get("typ") or "").strip()[:40],
        (request.GET.get("stadt") or "").strip()[:80],
    )
    if state.get("results"):
        reviews.attach_ratings(state["results"])
        _attach_open_status(state["results"])
    return render(request, "aggregator/finder.html", state)


def discover_index(request):
    # P2.7: поиск/фильтры. При q/city/type — страница результатов (cache_public_page
    # кэширует только GET без query, поэтому результаты не кэшируются); иначе —
    # индекс городов.
    q = (request.GET.get("q") or "").strip()
    city = (request.GET.get("city") or "").strip()
    btype = (request.GET.get("type") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    cat = (request.GET.get("cat") or "").strip()  # R2b направление
    month = (request.GET.get("month") or "").strip()  # R2b месяц (YYYY-MM)
    if kind not in dict(AggregatorListing.KINDS):
        kind = ""
    if q or city or btype or kind or cat or month:
        from urllib.parse import urlencode

        from . import reviews

        pool = listings_for(
            city=city or None,
            business_type=btype or None,
            q=q or None,
            kind=kind or None,
            category=cat or None,
            month=month or None,
        )
        cursor = request.GET.get("cursor")
        featured, rest = split_featured(pool, first_page=not cursor)
        page = paginate(rest, order_field="created_at", limit=24, cursor=cursor)
        cards = featured + page.items
        reviews.attach_ratings(cards)  # G8b: звёзды в выдаче
        base_qs = urlencode(
            [
                (k, v)
                for k, v in (
                    ("q", q),
                    ("city", city),
                    ("type", btype),
                    ("kind", kind),
                    ("cat", cat),
                    ("month", month),
                )
                if v
            ]
        )
        return render(
            request,
            "aggregator/search.html",
            {
                "q": q,
                "city": city,
                "type": btype,
                "kind": kind,
                "cat": cat,
                "month": month,
                "kinds": _KIND_LABELS,
                "cities": _distinct_cities(),
                "types": _distinct_types(),
                "categories": _distinct_event_categories(),
                "cards": cards,
                "page": page,
                "base_qs": base_qs,
                "canonical": request.build_absolute_uri(request.path),
            },
        )
    from . import recommendations, reviews

    ending = recommendations.ending_soon(listings_for(), days=3, limit=12)
    reviews.attach_ratings(ending)
    return render(
        request,
        "aggregator/index.html",
        {
            "cities": _distinct_cities(),
            "types": _distinct_types(),
            "categories": _distinct_event_categories(),
            "kinds": _KIND_LABELS,
            "ending_soon": ending,
        },
    )


@cache_public_page
def city_listing(request, city, business_type=None):
    from . import geo

    pool = listings_for(city=city, business_type=business_type)
    # A8: сортировка выдачи (keyset-совместимая — поле есть на листинге).
    sort = request.GET.get("sort")
    if sort not in _LISTING_SORTS:
        sort = "neueste"
    order_field, descending = _LISTING_SORTS[sort]
    # A8: фасетные фильтры — рейтинг (мин. звёзд) и «Jetzt geöffnet». Оба сводятся
    # к tenant_schema__in (keyset-пагинация цела). Применяем до split_featured.
    try:
        min_rating = int(request.GET.get("rating"))
    except (TypeError, ValueError):
        min_rating = 0
    if min_rating in _RATING_THRESHOLDS:
        pool = pool.filter(tenant_schema__in=_rating_schemas(min_rating))
    else:
        min_rating = 0
    offen = request.GET.get("offen") == "1"
    if offen:
        present = pool.values_list("tenant_schema", flat=True).distinct()
        pool = pool.filter(tenant_schema__in=_open_now_schemas(present))
    near_lat, near_lng = geo.parse_latlng(request)
    if near_lat is not None:  # G8c: «рядом» — ближайшие сверху, без пагинации (sort не применим)
        cards = geo.nearest(pool, near_lat, near_lng)
        page = None
    else:
        cursor = request.GET.get("cursor")
        featured, rest = split_featured(pool, first_page=not cursor)
        page = paginate(
            rest, order_field=order_field, limit=24, cursor=cursor, descending=descending
        )
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
    from . import reviews

    reviews.attach_ratings(cards)  # G8b: звёзды в выдаче
    _attach_open_status(cards)  # A8: live-статус «Jetzt geöffnet» на карточке
    # A8: непустые фасеты/сортировка для ссылки «Show more» (cursor добавляется в шаблоне).
    from urllib.parse import urlencode

    filter_qs = urlencode(
        [
            (k, v)
            for k, v in (
                ("sort", sort if sort != "neueste" else ""),
                ("rating", str(min_rating) if min_rating else ""),
                ("offen", "1" if offen else ""),
            )
            if v
        ]
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
            "cards": cards,
            "near_active": near_lat is not None,  # G8c
            "map_points": geo.map_points(cards),
            "canonical": request.build_absolute_uri(request.path),
            "other_cities": other_cities,
            "city_portal_url": f"{request.scheme}://{city_portal.host}/" if city_portal else "",
            "city_portal_title": city_portal.title_text if city_portal else "",
            "ld_itemlist": itemlist_ld([(it.title_text, it.detail_url) for it in cards]),
            "sort": sort,  # A8: текущая сортировка (для select + show-more)
            "min_rating": min_rating,  # A8: активный порог рейтинга (0 = выкл)
            "offen": offen,  # A8: фильтр «Jetzt geöffnet»
            "rating_thresholds": _RATING_THRESHOLDS,
            "filter_qs": filter_qs,  # A8: sort+rating+offen для ссылки «Show more»
            # A8/E-2: страница бизнеса теперь есть и на главном домене —
            # звёзды на карточках ведут на неё (как на порталах).
            "business_link": True,
        },
    )


def sitemap_xml(request):
    """Sitemap агрегатора (Track B5): /entdecken + города + город/тип.

    Карточки ведут на витрины тенантов (у каждой свой sitemap) — здесь только
    публичные посадочные страницы основного домена.
    """
    from xml.sax.saxutils import escape

    active = AggregatorListing.objects.filter(is_active=True)
    # Публичные страницы платформы: главная (обзор Branchen) + отраслевые + Über uns.
    from apps.tenants import archetype_pages

    urls = [request.build_absolute_uri("/")]
    urls += [request.build_absolute_uri(f"/branchen/{s}/") for s in archetype_pages.SLUGS]
    urls += [request.build_absolute_uri("/ueber-uns/")]
    urls += [request.build_absolute_uri(reverse("aggregator-index"))]
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
