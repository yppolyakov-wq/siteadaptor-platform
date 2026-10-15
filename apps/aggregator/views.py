"""Публичные страницы локального агрегатора (основной домен, public-схема).

Это «портал по умолчанию» над пулом AggregatorListing. Выборка — listings_for()
(seam для мульти-доменных порталов Phase 2 P2.1). Курсорная пагинация (apps.core).
"""

import logging

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.machine_http import static_resource
from apps.core.pagecache import cache_public_page
from apps.core.pagination import paginate
from apps.core.seo import itemlist_ld
from apps.tenants.models import Tenant

from .models import AggregatorListing

logger = logging.getLogger(__name__)

_BTYPE_LABELS = dict(Tenant.BUSINESS_TYPES)

# Подписи видов листинга для чипов фильтра (A5/A6). DE — рынок DACH.
_KIND_LABELS = [
    (AggregatorListing.KIND_PROMOTION, "Angebote"),
    (AggregatorListing.KIND_STAY, "Übernachten"),
    (AggregatorListing.KIND_EVENT, "Events"),
    (AggregatorListing.KIND_MENU, "Menüs & Pakete"),  # MEN-5
    # T-8.11: каталог города = все предложения бизнеса.
    (AggregatorListing.KIND_PRODUCT, "Produkte"),
    (AggregatorListing.KIND_SERVICE, "Dienstleistungen"),
    (AggregatorListing.KIND_BUSINESS, "Unternehmen"),
]


def _money(raw):
    """MEN-5: «45» / «45,50» → Decimal (мусор → None). Образец — CatalogFacets."""
    from decimal import Decimal, InvalidOperation

    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    # T-8.20: NaN/Infinity/1e999 из URL → не цена (иначе 500 на сравнении/в БД).
    if not value.is_finite() or value < 0 or value >= 10**8:
        return None
    return value


def listings_for(
    *,
    city=None,
    business_type=None,
    q=None,
    kind=None,
    kinds=None,
    category=None,
    month=None,
    guests=None,
    diet=None,
    event_type=None,
    price_from=None,
    price_to=None,
    district=None,
    city_category=None,
    city_tag=None,
    include_demo=True,
):
    """Активные листинги по фильтру. Переиспользуется порталами Phase 2.

    q — текстовый поиск (P2.7) по названию бизнеса, заголовку акции и городу;
    icontains по JSON-полю title матчит сериализованный текст (для v1 достаточно).
    kind — вид листинга (promotion/stay/event, A5/A6); пусто = все.
    category (R2b) — направление/тема event-листинга (yoga/meditation/…).
    month (R2b) — «YYYY-MM»: листинги, стартующие в этом месяце (для ретритов).

    Прошедшие события (event со starts_at в прошлом) скрываем всегда — sync
    удаляет их по правке, но дата может «истечь» без события-триггера.
    """
    from django.utils import timezone

    qs = AggregatorListing.objects.public()
    if not include_demo:  # T-8.15: настоящий портал — без демо-бизнесов
        qs = qs.filter(is_demo=False)
    if city:
        qs = qs.filter(city__iexact=city)
    if district:  # T-8.17: slug района (apps.core.districts)
        qs = qs.filter(district=district)
    if business_type:
        qs = qs.filter(business_type=business_type)
    if kind:
        qs = qs.filter(listing_kind=kind)
    elif kinds:
        qs = qs.filter(listing_kind__in=kinds)
    if category:
        qs = qs.filter(category__iexact=category)
    # T-8.13a: единая категория каталога города — раздел (все его категории) или
    # категория; признак (vegan/regional/…). Неизвестное значение фильтр не включает.
    from .models import apply_city_filters

    qs = apply_city_filters(qs, city_category, city_tag)
    if month and "-" in month:
        year, mon = month.split("-", 1)
        if year.isdigit() and mon.isdigit():
            qs = qs.filter(starts_at__year=int(year), starts_at__month=int(mon))
    # MEN-5: фильтры наборов меню (решения владельца: гости/цена-с-человека/
    # диеты/повод). Радиус выезда — v2 (у тенантов нет надёжных координат).
    if guests:
        try:
            qs = qs.filter(min_persons__lte=int(guests))
        except (TypeError, ValueError):
            pass
    if diet:
        qs = qs.filter(diets__contains=[diet])
    if event_type:
        qs = qs.filter(event_types__contains=[event_type])
    lo, hi = _money(price_from), _money(price_to)
    if lo is not None:
        qs = qs.filter(new_price__gte=lo)
    if hi is not None:
        qs = qs.filter(new_price__lte=hi)
    if q:
        # T-8.20: полнотекст по индексу (заголовки всех языков, бизнес, блюда — MEN-5
        # «блюда наружу», категории, район, город) — то же правило, что у search.execute.
        from . import search

        qs = search.match(qs, q)
    # Истёкшие события вон (у прочих видов starts_at либо null, либо окно акции).
    qs = qs.exclude(listing_kind=AggregatorListing.KIND_EVENT, starts_at__lt=timezone.now())
    return qs


def _distinct_event_categories():
    """Присутствующие направления event-листингов → [(key, label)] (R2b)."""
    from apps.events import taxonomy

    present = set(
        AggregatorListing.objects.public()
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


def split_featured(qs, *, first_page: bool, limit: int = 6, count_impressions: bool = True):
    """(featured, остальная лента) — платное продвижение (P2.4a).

    Featured закреплены сверху ПЕРВОЙ страницы выдачи (с бейджем) и исключены
    из обычной ленты, чтобы keyset-пагинация не давала дублей; на cursor-страницах
    блок не повторяется.
    """
    from django.utils import timezone

    featured_qs = qs.filter(featured_until__gt=timezone.now()).order_by("featured_until", "pk")
    featured = list(featured_qs[:limit]) if first_page else []
    rest = qs.exclude(pk__in=featured_qs.values_list("pk", flat=True))
    if featured and count_impressions:
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

    listing = AggregatorListing.objects.public().filter(pk=pk).first()
    if listing is None:
        return redirect("/")  # корень валиден и на /entdecken-домене, и на портале
    if listing.is_featured_now:
        AggregatorListing.objects.filter(pk=pk).update(featured_clicks=F("featured_clicks") + 1)
    url = listing.portal_url or ""
    if not url.startswith(("http://", "https://", "/")):
        return redirect("/")
    return redirect(url)


def _distinct_cities():
    return (
        AggregatorListing.objects.public()
        .exclude(city="")
        .values_list("city", flat=True)
        .distinct()
        .order_by("city")
    )


def _distinct_types():
    types = (
        AggregatorListing.objects.public()
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


def _city_category_choices():
    """T-8.13a: селект «Kategorie» на /entdecken/ — разделы и категории справочника."""
    from apps.core import city_categories as cc

    return [
        (
            s.key,
            f"{s.icon} {s.label}",
            [(c.key, str(c.label)) for c in cc.CATEGORIES if c.section == s.key],
        )
        for s in cc.SECTIONS
    ]


#: Поисковых запросов /entdecken/ на IP в минуту.
SEARCH_RATE_LIMIT = 60


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
    # MEN-5: фильтры наборов меню (гости/повод/диета/цена с человека).
    guests = (request.GET.get("gaeste") or "").strip()
    anlass = (request.GET.get("anlass") or "").strip()
    diet = (request.GET.get("diet") or "").strip()
    preis_von = (request.GET.get("preis_von") or "").strip()
    preis_bis = (request.GET.get("preis_bis") or "").strip()
    if kind not in dict(AggregatorListing.KINDS):
        kind = ""
    from . import category_facets  # T-8.13a: единые категории и признаки

    kat, tag = category_facets.selected(request)
    # T-8.20: фильтры единого поиска (общие с порталом).
    from dataclasses import replace

    from . import search

    filters = search.parse_filters(request, city=city)
    if (
        filters.active
        or filters.sort
        or kat
        or tag
        or q
        or city
        or btype
        or kind
        or cat
        or month
        or guests
        or anlass
        or diet
        or preis_von
        or preis_bis
    ):
        from urllib.parse import urlencode

        from apps.core import ratelimit

        from . import reviews

        # Поиск не кэшируется (страница с параметрами) — ограничиваем частоту на IP,
        # чтобы перебор запросов не нагружал БД (ТЗ 2.0 §12). Обычный посетитель
        # до лимита не доходит.
        if ratelimit.hit(
            "entdecken-search",
            ratelimit.client_ip(request),
            limit=SEARCH_RATE_LIMIT,
            window=60,
        ):
            return HttpResponse(_("Zu viele Anfragen — bitte kurz warten."), status=429)

        # T-8.20: единый поиск — тот же движок и те же фильтры, что на портале города.
        pool_base = listings_for(
            city=city or None,
            business_type=btype or None,
            kind=kind or None,
            category=cat or None,
            month=month or None,
            guests=guests or None,
            event_type=anlass or None,
            diet=diet or None,
        )
        cursor = request.GET.get("cursor")
        outcome = search.execute(
            pool_base,
            q,
            filters,
            surface="entdecken",
            city=city,
            track=not cursor,
            # Параметры, сужающие пул ДО поиска, — в ключ журнала (иначе счётчики врут).
            extra={
                "type": btype,
                "kind": kind,
                "cat": cat,
                "month": month,
                "gaeste": guests,
                "anlass": anlass,
                "diet": diet,
            },
        )
        pool = outcome.qs
        keep = {
            "q": q,
            "city": city,
            "type": btype,
            "kind": kind,
            "cat": cat,
            "month": month,
            "gaeste": guests,
            "anlass": anlass,
            "diet": diet,
            "preis_von": preis_von,
            "preis_bis": preis_bis,
        }
        chips_base = search.execute(
            pool_base, q, replace(filters, kats=(), tags=()), surface="entdecken", track=False
        ).qs
        # T-8.20: фильтры единого поиска не теряются при клике по чипу категории.
        keep.update({k: v for k, v in search.carry("", filters) if k not in ("kat", "merkmal")})
        category_chips = category_facets.chips(
            chips_base.order_by(), request.path, kat, tag, extra=keep
        )
        featured, rest = split_featured(pool, first_page=not cursor)
        if outcome.ranked:  # T-8.20: релевантность — offset-курсор того же вида
            from django.conf import settings

            from apps.core.pagination import paginate_ranked

            page = paginate_ranked(
                rest, limit=24, cursor=cursor, max_results=settings.AGGREGATOR_SEARCH["max_results"]
            )
        else:
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
                    ("gaeste", guests),
                    ("anlass", anlass),
                    ("diet", diet),
                )
                if v
            ]
            + search.carry("", filters)
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
                "gaeste": guests,
                "anlass": anlass,
                "diet": diet,
                "preis_von": preis_von,
                "preis_bis": preis_bis,
                "kinds": _KIND_LABELS,
                "cities": _distinct_cities(),
                "types": _distinct_types(),
                "categories": _distinct_event_categories(),
                "category_chips": category_chips,  # T-8.13a
                "kat": kat,
                "city_category_choices": _city_category_choices(),
                "cards": cards,
                "page": page,
                "base_qs": base_qs,
                # T-8.20: форма поиска переносит фильтры единого поиска (hidden).
                "search_hidden": [
                    (k, v)
                    for k, v in search.carry("", filters)
                    if k != "kat"  # у категории своё поле формы
                ],
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
            "city_category_choices": _city_category_choices(),
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
        AggregatorListing.objects.public()
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
    response = render(
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
    if not cards:
        # Роут принимает ЛЮБУЮ строку и на выдуманном городе отдаёт пустую
        # страницу с кодом 200 — значит аноним минтил бы по записи кэша на
        # каждый придуманный адрес, в том же Redis, где сессии. Судим по
        # фактическим карточкам: это верно и при любых параметрах, и не стоит
        # лишнего запроса (в отличие от отдельного EXISTS).
        response.no_store = True
    return response


@static_resource
def sitemap_xml(request):
    """Sitemap основного домена (Track B5): платформа + /entdecken + города + город/тип.

    Карточки ведут на витрины тенантов (у каждой свой sitemap) — здесь только
    публичные посадочные страницы основного домена. T-8.8: `<lastmod>` у корня
    /entdecken/ и городов, кэш, кап (как у портала).
    """
    from django.db.models import Max

    from apps.tenants import archetype_pages

    from .portal_views import SITEMAP_MAX_URLS, render_sitemap

    # T-8.8: демо в sitemap не входят (фид того же домена их не отдаёт — согласовано).
    active = AggregatorListing.objects.public().filter(is_demo=False)
    abs_ = request.build_absolute_uri
    urls: list[tuple[str, object]] = [(abs_("/"), None)]
    urls += [(abs_(f"/branchen/{s}/"), None) for s in archetype_pages.SLUGS]
    urls += [(abs_("/ueber-uns/"), None)]
    urls += [(abs_(reverse("aggregator-index")), active.aggregate(m=Max("updated_at"))["m"])]
    cities = active.exclude(city="").values("city").annotate(m=Max("updated_at")).order_by("city")
    urls += [(abs_(reverse("aggregator-city", args=[row["city"]])), row["m"]) for row in cities]
    urls += [
        (abs_(reverse("aggregator-city-type", args=[c, bt])), None)
        for c, bt in active.exclude(city="")
        .exclude(business_type="")
        .values_list("city", "business_type")
        .distinct()
        .order_by("city", "business_type")
    ]
    if len(urls) > SITEMAP_MAX_URLS:
        logger.warning("platform sitemap truncated: %s urls", len(urls))
        urls = urls[:SITEMAP_MAX_URLS]
    return render_sitemap(urls)


#: T-8.8 (Р-6): технические GET-пути основного домена — не для индексации.
PLATFORM_DISALLOW = (
    "/entdecken/klick/",
    "/entdecken/melden/",
    "/entdecken/merkliste/",
    "/entdecken/folgen/",
)


@static_resource
def robots_txt(request):
    """robots.txt основного домена: всё открыто, кроме технических путей + sitemap."""
    sitemap = request.build_absolute_uri(reverse("aggregator-sitemap"))
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {p}" for p in PLATFORM_DISALLOW]
    lines += [f"Sitemap: {sitemap}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def _discover_feed(request, fmt: str):
    """T-8.8 (Р-5): фид основного домена — `?city=` сужает, иначе общий пул; демо никогда."""
    from . import open_feed

    city = (request.GET.get("city") or "").strip()[:100]
    # Эхо в title/meta только для ГОРОДА ИЗ КАТАЛОГА — иначе ссылка несла бы чужой
    # текст в заголовок, который читают ассистенты (prompt-injection через `?city=`).
    if city and not AggregatorListing.objects.public().filter(city__iexact=city).exists():
        city = ""
    return open_feed.render_feed(
        request,
        fmt=fmt,
        title=f"siteadaptor · {city}" if city else "siteadaptor",
        home_url=request.build_absolute_uri(reverse("aggregator-index")),
        city=city,
        business_type="",
        include_demo=False,
    )


def _machine(fn):
    from apps.core.machine_http import machine_resource

    return machine_resource(cache_public_page(fn))


@_machine
def discover_feed_json(request):
    return _discover_feed(request, "json")


@_machine
def discover_feed_atom(request):
    return _discover_feed(request, "atom")


@static_resource
def llms_txt(request):
    """T-8.8: llms.txt основного домена — платформа, /entdecken/, фид, порталы."""
    from . import llms

    return HttpResponse(llms.build_platform(request), content_type="text/plain; charset=utf-8")


@require_POST
def shortlist_toggle(request):
    """MEN-12: отложить/убрать предложение (сессия, без аккаунта). POST + next."""
    from . import shortlist

    shortlist.toggle(request, request.POST.get("listing"))
    nxt = request.POST.get("next") or ""
    ok = nxt.startswith("/") and not nxt.startswith("//")  # protocol-relative — чужой хост
    return redirect(nxt if ok else reverse("aggregator-index"))


def shortlist_compare(request):
    """MEN-12 (запрос владельца «где потом можно сравнить варианты»): страница
    сравнения отложенных предложений — таблица «характеристика × вариант»."""
    from . import reviews, shortlist

    items = shortlist.listings(request)
    reviews.attach_ratings(items)  # рейтинг бизнеса — строкой сравнения
    return render(
        request,
        "aggregator/shortlist.html",
        {
            "items": items,
            "rows": shortlist.compare_rows(items),
            "shortlist_ids": set(shortlist.ids(request)),
        },
    )


def _offer_in_scope(listing, portal) -> bool:
    """T-8.24: предложение открывается порталом только в его границах (как лента)."""
    if portal is None:
        return True
    if listing.is_demo and not portal.show_demo:
        return False
    if portal.city and (listing.city or "").lower() != portal.city.lower():
        return False
    return not (portal.business_type and listing.business_type != portal.business_type)


def _offer_pool(portal):
    return listings_for(
        city=portal.city if portal else None,
        business_type=portal.business_type if portal else None,
        include_demo=portal.show_demo if portal else True,
    )


@cache_public_page
def offer_page(request, pk):
    """T-8.24: страница одного предложения внутри портала (план t8-24-portal-offer-page-plan).

    Стратегия А: canonical — страница бизнеса (detail_url), портал входит в выдачу
    страницами-списками. Житель видит предложение, другие предложения бизнеса и похожие
    рядом, а на сайт бизнеса уходит кнопкой с атрибуцией `?ch=portal`.
    """
    from django.http import Http404

    from .reviews import attach_ratings

    portal = getattr(request, "portal", None)
    listing = AggregatorListing.objects.public().filter(pk=pk).first()
    if listing is None or not _offer_in_scope(listing, portal):
        raise Http404
    pool = _offer_pool(portal).exclude(pk=listing.pk)
    more = list(pool.filter(tenant_schema=listing.tenant_schema).order_by("-updated_at")[:4])
    similar_qs = pool.exclude(tenant_schema=listing.tenant_schema)
    if listing.district:
        near = similar_qs.filter(district=listing.district)
        if near.exists():
            similar_qs = near
    if listing.city_category:
        same = similar_qs.filter(city_category=listing.city_category)
        similar_qs = same if same.exists() else similar_qs.filter(listing_kind=listing.listing_kind)
    else:
        similar_qs = similar_qs.filter(listing_kind=listing.listing_kind)
    similar = list(similar_qs.order_by("-updated_at")[:4])
    attach_ratings([listing, *more, *similar])
    _attach_open_status([listing, *more, *similar])

    # T-8.8: тип по виду листинга, продавец — полный LocalBusiness из публичных полей
    # тенанта (+1 запрос; страница кэшируется). Сирота без тенанта → фолбэк.
    from apps.tenants.models import Tenant

    from .structured import listing_ld

    tenant = Tenant.objects.filter(schema_name=listing.tenant_schema).first()
    ld = listing_ld(listing, request=request, tenant=tenant)
    from apps.core.seo import _dumps

    return render(
        request,
        "aggregator/offer.html",
        {
            "portal": portal,
            "base_template": "aggregator/portal_base.html" if portal else "aggregator/_base.html",
            "listing": listing,
            "more": more,
            "similar": similar,
            # Стратегия А: основная страница — у бизнеса; портал — промежуточный шаг.
            "canonical": listing.detail_url,
            "offer_jsonld": _dumps(ld),
        },
    )
