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
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.core.machine_http import static_resource
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


# Блок Б1: «N Treffer» считается до потолка выдачи (`AGGREGATOR_SEARCH.max_results` —
# столько посетитель может пролистать); больше показываем как «240+».


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
    near_lat, near_lng = geo.parse_latlng(request)
    point = (near_lat, near_lng) if near_lat is not None else None
    filters = search_engine.parse_filters(request, city=city or "", point=point)
    if point is not None and not filters.sort:  # кнопка «📍 Near me» без sort = «Nähe»
        filters = replace(filters, sort="naehe")
    if district:  # путь /stadtteil/<slug>/ сильнее параметра
        filters = replace(filters, district="")
    # T-8.26 п.5a: намерение из текста («unter 100 €», «heute geöffnet», «in Wald») → фильтры
    # поиска; `filters` (явные) остаются источником формы/carry/пилюль, `filters_eff` — выборки.
    q_eff, filters_eff, intent_chips, intent_hints = search_engine.resolve_intent(
        q, filters, city=city or "", roh=request.GET.getlist("roh"), path_district=bool(district)
    )
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
    # T-8.26 п.4 (Р-6): вход в раздел/признак без вида — все виды: ровно то, что
    # посчитала плитка раздела (иначе «10 на плитке, 1 в выдаче»).
    # T-8.26 п.5c: размер есть только у товаров — явный ?groesse= без q иначе упёрся бы
    # в ленту предложений (OFFER_KINDS без товара) и дал пустую выдачу.
    kind = scope.kind_key or ("alle" if (q or filters.kats or filters.tags or filters.size) else "")
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
        q_eff,
        replace(filters_eff, kats=(), tags=()),
        surface="portal",
        track=False,
        city=city or "",  # T-8.26 п.4: топонимы города не участвуют в фолбэке опечаток
        point=point,
    )
    whole_pool = broad.qs
    # Параметры поиска/фильтров (кроме категорий) — в ссылках вкладок, чипов и формы.
    # T-8.7: координаты посетителя едут в ссылках отдельно (geo.carry), НЕ в search.carry —
    # иначе они попали бы в журнал поиска T-8.21.
    geo_carry = geo.carry(near_lat, near_lng)
    carry = [
        (k, v) for k, v in search_engine.carry(q, filters) if k not in ("kat", "merkmal")
    ] + geo_carry
    # T-8.26 п.4 (Р-5): вкладки НЕ сбрасывают раздел/признак, а их видимость считается
    # по пулу С разделом — показанная вкладка ⇒ непустая выдача.
    tab_carry = list(search_engine.carry(q, filters)) + geo_carry
    # Блок А2: чипы района и отрасли меняют только район/отрасль — запрос, фильтры,
    # сортировка и вкладка остаются. `stadtteil` задаёт сам чип (путём), курсор —
    # позиция в старой выдаче, его не переносим.
    chip_carry = urlencode(
        [(k, v) for k, v in _scope_pairs(scope) + tab_carry if k not in ("stadtteil", "cursor")]
    )
    city_home = home.has_home(portal)
    if city_home:  # T-8.19: вкладки главной вместо чипов видов
        kind_chips = []
        tab_pool = search_engine.apply_filters(
            whole_pool, search_engine.SearchFilters(kats=filters_eff.kats, tags=filters_eff.tags)
        )
        portal_tabs = home.tabs(home.presence(tab_pool), kind, request.path, carry=tab_carry)
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
        base_pool, search_engine.SearchFilters(kats=filters_eff.kats, tags=filters_eff.tags)
    )
    # Блок Б5: группа «Von <Firma>» — только на первой странице выдачи.
    pool, firm_group, firm_total = _split_firm_matches(pool, q_eff)
    if request.GET.get("cursor"):
        firm_group = None
    from . import query_intent

    # Блок Б1: при поиске — сначала «N Treffer» и карточки, уточнение (районы/отрасли/
    # категории) свёрнуто и строится по НАЙДЕННОМУ, а не по всему порталу.
    searching = bool(q or filters.active)
    hits = hits_capped = None
    if searching:
        # один DISTINCT по паре вместо двух отдельных (database-ревью)
        pairs = set(whole_pool.order_by().values_list("district", "business_type").distinct())
        if not district:
            used = {d for d, _t in pairs if d}
            district_chips = [(slug, name) for slug, name in district_chips if slug in used]
        if not facet and axis == "business_type":
            types = {t for _d, t in pairs}
            facets = [(v, label) for v, label in facets if v in types]
        if not (point is not None and filters.sort in ("", "naehe")):
            cap = settings.AGGREGATOR_SEARCH["max_results"]
            hits = search_engine.count_capped(pool, cap) + firm_total  # группа — тоже найдено
            hits_capped = hits > cap
            hits = min(hits, cap)
    search_engine.record(
        search_engine.SearchOutcome(pool, broad.mode, q, broad.ranked, filters, lang=broad.lang),
        surface="portal",
        city=city or "",
        portal_host=portal.host,
        first_page=not request.GET.get("cursor"),  # листание выдачи — не новый поиск
        # Область выборки — в ключ журнала: вкладка/«Neu»/район из пути/тип бизнеса.
        extra={
            "kind": kind,
            "neu": "1" if scope.new_only else "",
            "stadtteil": district or "",
            "type": business_type or "",
            "auto": query_intent.auto_keys(intent_chips),  # T-8.26 п.5a: что выведено из текста
        },
    )
    # G8c/T-8.7: «рядом» — ближайшие сверху, без пагинации; точка без явного сорта =
    # «Nähe» (обратная совместимость кнопки «📍 Near me»), явный сорт с точкой — обычная лента.
    if point is not None and filters.sort in ("", "naehe"):
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
    # T-8.7: «Folgen» на странице раздела (?kat=) и района — ссылка, не форма (кэш P0-1).
    follow_target = None
    if city_home:
        from . import follow

        if district:
            follow_target = follow.parse_target({"stadtteil": district}, portal=portal)
        elif len(filters.kats) == 1:
            follow_target = follow.parse_target({"bereich": filters.kats[0]}, portal=portal)
    return render(
        request,
        "aggregator/portal_home.html",
        {
            "portal": portal,
            "follow_target": follow_target,
            "following": follow.is_following(user, follow_target) if follow_target else False,
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
            "chip_carry": chip_carry,  # блок А2
            "firm_group": firm_group,  # блок Б5
            "searching": searching,  # блок Б1
            "hits": hits,
            "hits_capped": hits_capped,
            "map_view": geo.map_view(request),  # блок Б2
            "category_chips": category_chips,  # T-8.13a
            "kind_chips": kind_chips,  # T-8.11
            "portal_tabs": portal_tabs,  # T-8.19
            "search_q": q,
            "search_kind": scope.kind_key,
            "search_mode": broad.mode,
            # T-8.26 п.5a: пилюли «Erkannt: …» (✕ = запрос без фразы / roh=ort у района)
            "intent_chips": _intent_chip_links(request, intent_chips, filters, geo_carry, scope),
            "intent_hints": _intent_hint_links(
                request, intent_hints, pool, q, filters, geo_carry, scope
            ),
            # T-8.20: новый запрос не сбрасывает вкладку и фильтры.
            "search_hidden": [
                (k, v)
                for k, v in [
                    ("kind", scope.kind_key if scope.kind_key != "alle" else ""),
                    ("neu", "1" if scope.new_only else ""),
                ]
                + search_engine.carry("", filters)
                + geo_carry
                + [("roh", v) for v in request.GET.getlist("roh") if v == "ort"]
                if v
            ],
            # T-8.20: блок фильтров и пилюли активных фильтров (только у городского портала).
            "filter_panel": _filter_panel(request, portal, filters, q, scope, district, point)
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
                + geo_carry
                + ([("ansicht", "karte")] if request.GET.get("ansicht") == "karte" else [])
            ),
            # T-8.15: портал показывает демо-бизнесы — честная полоса «Vorschau».
            "shows_demo": portal.show_demo and any(getattr(c, "is_demo", False) for c in cards),
            "business_link": True,  # G8b: на порталах звёзды ведут на страницу бизнеса
            "near_active": point is not None and filters.sort in ("", "naehe"),  # G8c
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


@cache_public_page
def for_business(request):
    """Блок А3: «Für Unternehmen» — что даёт каталог города бизнесу и вход в
    «Aktion in 3 Klicks» (T-8.5). Только реализованные возможности."""
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    from .platform_links import platform_url

    return render(
        request,
        "aggregator/for_business.html",
        {
            "portal": portal,
            "quick_start_url": platform_url("quick-start"),
            "free_promos": getattr(settings, "LITE_FREE_ACTIVE_PROMOS", 5),
        },
    )


# Блок Б5: запрос — это имя фирмы («Pizzabote»)? Её позиции, совпавшие ТОЛЬКО по имени
# (салат у пиццерии), не забивают выдачу, а уходят в группу «Von <Firma>».
_FIRM_GROUP_LIMIT = 8
_FIRM_SCAN = 50


def _split_firm_matches(pool, q: str):
    """(выдача без «совпавших по имени фирмы» позиций, группа | None, всего в группе).

    Срабатывает, только когда запрос однозначно называет ОДНУ фирму: все значимые слова
    запроса есть в её имени, и такая фирма в выдаче единственная. Общий запрос («Pizza»,
    «Bäckerei»), совпавший с именами нескольких фирм, выдачу не трогает. В группу уходят
    позиции фирмы, в заголовке которых нет ни одного слова запроса (ни в исходном, ни в
    свёрнутом виде — «Müller»/«muller»); карточка самой фирмы остаётся в выдаче."""
    from django.db.models import Q, TextField, Value
    from django.db.models.functions import Cast, Coalesce

    from .search import SEARCH_MAX, count_capped
    from .search_index import fold

    # Управляющие символы (NUL и др.) в SQL не пускаем — Postgres отвергает NUL в тексте.
    q = "".join(ch for ch in (q or "")[:SEARCH_MAX] if ch.isprintable())
    words = [w for w in q.lower().split() if len(w) >= 3]
    tokens = [t for t in fold(q).split() if len(t) >= 3]
    if not tokens or not words:
        return pool, None, 0
    # Кандидаты — в SQL по свёрнутому `search_text` (в нём есть имя фирмы; trigram-индекс),
    # точная проверка «все слова в ИМЕНИ» — по свёрнутому имени.
    name_q = Q()
    for t in tokens:
        name_q &= Q(search_text__contains=t)
    firms = [
        row
        for row in pool.order_by("business_name")
        .filter(name_q)
        .values_list("tenant_schema", "tenant_slug", "business_name")
        .distinct()[:_FIRM_SCAN]
        if all(t in fold(row[2] or "") for t in tokens)
    ]
    if len({f[0] for f in firms}) != 1:  # нет фирмы или запрос не однозначен
        return pool, None, 0
    schema, slug, name = firms[0]
    pool = pool.annotate(
        _title_txt=Coalesce(Cast("title", TextField()), Value(""), output_field=TextField())
    )
    title_hit = Q()
    for w in {*words, *tokens}:
        title_hit |= Q(_title_txt__icontains=w)
    name_only = (
        Q(tenant_schema=schema) & ~Q(listing_kind=AggregatorListing.KIND_BUSINESS) & ~title_hit
    )
    grouped = pool.filter(name_only)
    items = list(grouped.order_by("-updated_at")[:_FIRM_GROUP_LIMIT])
    if not items:
        return pool, None, 0
    total = count_capped(grouped, settings.AGGREGATOR_SEARCH["max_results"])
    group = {"name": name, "slug": slug, "items": items, "total": total}
    return pool.exclude(name_only), group, total


def _scope_pairs(scope) -> list[tuple[str, str]]:
    return [
        (k, v) for k, v in (("kind", scope.kind_key), ("neu", "1" if scope.new_only else "")) if v
    ]


def _intent_chip_links(request, chips, filters, geo_carry, scope) -> list[dict]:
    """T-8.26 п.5a: пилюля выведенного фильтра → ссылка-✕. Район: слово остаётся в тексте
    (`roh=ort`); прочие: запрос без своей фразы. Явные фильтры и область сохраняются."""
    from . import query_intent
    from . import search as search_engine

    roh = [("roh", v) for v in request.GET.getlist("roh") if v == query_intent.ROH_ORT]
    out = []
    for c in chips:
        if c.key == query_intent.KEY_DISTRICT:
            raw_q = request.GET.get("q", "")
            params = _scope_pairs(scope) + search_engine.carry(raw_q, filters)
            params.append(("roh", query_intent.ROH_ORT))
        else:  # `roh=ort` переживает ✕ других пилюль — иначе район вернулся бы сам
            params = _scope_pairs(scope) + search_engine.carry(c.q_without, filters) + roh
        params = [(k, v) for k, v in params + list(geo_carry) if v]
        out.append(
            {
                "key": c.key,
                "label": c.label,
                "url": f"{request.path}?{urlencode(params)}" if params else request.path,
            }
        )
    return out


def _intent_hint_links(request, hints, pool, q, filters, geo_carry, scope) -> list[dict]:
    """Подсказка «Nur mit Merkmal …» — только если в выдаче есть хоть один такой листинг."""
    from apps.core import city_categories as cc

    from . import query_intent
    from . import search as search_engine

    out = []
    for key in hints[: query_intent.HINTS_MAX]:
        if key in filters.tags or not pool.filter(city_tags__contains=[key]).exists():
            continue
        params = (
            _scope_pairs(scope)
            + search_engine.carry(q, filters)
            + [("merkmal", key)]
            + list(geo_carry)
        )
        out.append(
            {
                "key": key,
                "label": _("Nur mit Merkmal %(t)s") % {"t": cc.tag_label(key)},
                "url": f"{request.path}?{urlencode(params)}",
            }
        )
    return out


def _filter_panel(request, portal, filters, q: str, scope, district, point=None) -> dict:
    """T-8.20: блок фильтров ленты (без JS) и пилюли активных фильтров с ✕."""
    from . import geo
    from . import search as search_engine

    keep = [("kind", scope.kind_key)] if scope.kind_key else []
    if scope.new_only:
        keep.append(("neu", "1"))
    geo_carry = geo.carry(*point) if point is not None else []
    params = keep + search_engine.carry(q, filters) + geo_carry

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
    if filters.size:  # T-8.26 п.5c
        pills.append({"label": _("Größe %(s)s") % {"s": filters.size}, "url": without("groesse")})
    if filters.radius_km:  # T-8.7 Р-5
        pills.append(
            {"label": _("≤ %(km)s km") % {"km": filters.radius_km}, "url": without("umkreis")}
        )
    hidden = [
        (k, v)
        for k, v in keep + search_engine.carry(q, filters) + geo_carry
        if k in ("kind", "neu", "q", "kat", "merkmal", "lat", "lng", "groesse")
    ]
    # T-8.7 Р-6: «Relevanz» только при q; «In der Nähe» и радиус — только при точке.
    sorts = [("", _("Relevanz") if q else _("Standard"))] + [
        (k, label)
        for k, label in search_engine.SORT_LABELS.items()
        if k != "naehe" or point is not None
    ]
    return {
        "filters": filters,
        "districts": [] if district else _district_choices(portal),
        "hidden": hidden,
        "pills": pills,
        "sorts": sorts,
        "has_point": point is not None,
        "radius_choices": geo.RADIUS_CHOICES,
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


SITEMAP_MAX_URLS = 45_000


def _sitemap_urls(request, portal) -> list[tuple[str, object]]:
    """T-8.8: (loc, lastmod|None) портала — корень + фасеты + районы + страницы бизнесов.

    Предложения `/angebot/<pk>/` НЕ входят (Р-1 A: их canonical указывает на бизнес —
    URL в sitemap с чужим canonical даёт в Search Console «Alternate page with proper
    canonical»). Query-URL (`?kat=`) тоже не входят. Кап + warning при обрезке;
    sitemap-index — когда упрёмся (roadmap §Отложено)."""
    from django.db.models import Max

    if portal.show_demo:
        # T-8.26 (Р-1): превью целиком noindex → sitemap пустой (иначе Search Console:
        # «Submitted URL marked noindex»).
        return []
    pool = listings_for(
        city=portal.city or None,
        business_type=portal.business_type or None,
        include_demo=False,
    )
    abs_ = request.build_absolute_uri
    urls: list[tuple[str, object]] = [
        (abs_(reverse("portal-home")), pool.aggregate(m=Max("updated_at"))["m"])
    ]
    _, facets = _facet_choices(portal)
    urls += [(abs_(reverse("portal-facet", args=[v])), None) for v, _label in facets]
    urls += [
        (abs_(reverse("portal-district", args=[slug])), None)
        for slug, _name in _district_choices(portal)
    ]
    businesses = (
        pool.exclude(tenant_slug="")
        .values("tenant_slug")
        .annotate(m=Max("updated_at"))
        .order_by("tenant_slug")[:SITEMAP_MAX_URLS]
    )
    for row in businesses:
        try:  # старый слаг вне `<slug:>` не должен ронять весь sitemap
            urls.append((abs_(reverse("portal-business", args=[row["tenant_slug"]])), row["m"]))
        except NoReverseMatch:
            continue
    if len(urls) > SITEMAP_MAX_URLS:
        import logging

        logging.getLogger(__name__).warning(
            "portal sitemap truncated: %s urls on %s", len(urls), portal.host
        )
        urls = urls[:SITEMAP_MAX_URLS]
    return urls


def render_sitemap(urls) -> HttpResponse:
    from xml.sax.saxutils import escape

    parts = []
    for loc, lastmod in urls:
        tail = f"<lastmod>{lastmod.date().isoformat()}</lastmod>" if lastmod else ""
        parts.append(f"<url><loc>{escape(loc)}</loc>{tail}</url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{''.join(parts)}</urlset>"
    )
    return HttpResponse(xml, content_type="application/xml")


@static_resource
def portal_sitemap_xml(request):
    """Sitemap портала: корень + уточнения + районы + страницы бизнесов (T-8.8)."""
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return render_sitemap(_sitemap_urls(request, portal))


#: T-8.8 (Р-6): технические GET-пути портала — не для индексации. AI-краулеры открыты.
PORTAL_DISALLOW = ("/klick/", "/melden/", "/konto/", "/tg/", "/sprache/", "/folgen/")


@static_resource
def portal_robots_txt(request):
    """robots.txt портала: всё открыто, кроме технических путей + sitemap хоста."""
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {p}" for p in PORTAL_DISALLOW]
    portal = getattr(request, "portal", None)
    # T-8.26 (Р-1): превью — Allow остаётся (иначе робот не увидит noindex), но без Sitemap.
    if portal is None or not portal.show_demo:
        lines.append(f"Sitemap: {request.build_absolute_uri(reverse('portal-sitemap'))}")
    lines.append("")
    return HttpResponse("\n".join(lines), content_type="text/plain")


def _feed(request, fmt: str):
    from . import open_feed

    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return open_feed.render_feed(
        request,
        fmt=fmt,
        title=portal.title_text,
        home_url=request.build_absolute_uri(reverse("portal-home")),
        city=portal.city or "",
        business_type=portal.business_type or "",
        include_demo=False,  # T-8.26 (Р-3): демо в фид не уходит никогда
        preview=portal.show_demo,
    )


def _machine(fn):
    from apps.core.machine_http import machine_resource

    return machine_resource(cache_public_page(fn))


@_machine
def portal_feed_json(request):
    """T-8.8: открытый JSON Feed 1.1 портала (`?kind/kat/merkmal/stadtteil/limit/cursor`)."""
    return _feed(request, "json")


@_machine
def portal_feed_atom(request):
    """T-8.8: тот же набор элементов в Atom 1.0."""
    return _feed(request, "atom")


@static_resource
def portal_llms_txt(request):
    """T-8.8: llms.txt портала — карта каталога для AI-ассистентов."""
    from . import llms

    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return HttpResponse(
        llms.build_portal(request, portal), content_type="text/plain; charset=utf-8"
    )


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
