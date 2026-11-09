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

from . import portal_scope, portal_slides
from .models import AggregatorListing
from .views import SEARCH_RATE_LIMIT

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
    base = portal_scope.pool(portal, district=district)
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
        portal_scope.pool(portal).exclude(district="").values_list("district", flat=True).distinct()
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


def area_districts(path_district, filters) -> tuple[str, ...]:
    """FLT-1b: район пути ∪ районы фильтров (порядок: путь первым, без дублей)."""
    head = (path_district,) if path_district else ()
    return tuple(dict.fromkeys(head + tuple(filters.districts)))


def _district_pool(
    portal, city, business_type, district, q_eff, filters_eff, kinds, new_only, point, fuzzy=True
):
    """Цепочка выборки страницы портала: (outcome, весь пул, пул вида/«Neu», выдача).

    Одна функция для основной выдачи и групп Г5 «Auch in der Nähe» — на этом держится
    «группа ⊆ выдачи по своей ссылке»: страница соседа строит пул ровно так же.

    FLT-1b: `district` — район ПУТИ (`/stadtteil/<slug>/`, или "" ); районы из GET/текста
    едут в `filters_eff.districts`. Область выдачи — их ОБЪЕДИНЕНИЕ, и режим поиска
    (полнотекст/опечатки) решается уже на пуле этих районов: «похожие» только в районе
    находятся на его странице (план FLT §13.1)."""
    area = area_districts(district, filters_eff)
    return _pool_chain(
        portal, city, business_type, area, q_eff, filters_eff, kinds, new_only, point, fuzzy
    )


def _pool_chain(
    portal, city, business_type, area, q_eff, filters_eff, kinds, new_only, point, fuzzy=True
):
    """Тело `_district_pool` по готовой области районов (FLT-1d: им же — пул счётчиков)."""
    from dataclasses import replace

    from . import portal_home_blocks as home
    from . import search as search_engine

    # T-8.20: единый поиск — режим (полнотекст/опечатки) решается ОДИН раз по пулу без
    # вида и категорий; от него же вкладки, чипы и выдача (иначе вкладка «0», а лента нашла).
    broad = search_engine.execute(
        portal_scope.pool(portal, city=city, business_type=business_type, district=area or None),
        q_eff,
        replace(filters_eff, kats=(), tags=(), districts=()),
        surface="portal",
        track=False,
        city=city or "",  # T-8.26 п.4: топонимы города не участвуют в фолбэке опечаток
        point=point,
        fuzzy=fuzzy,
    )
    whole_pool = broad.qs
    base_pool = home.apply_scope(
        whole_pool.filter(listing_kind__in=kinds), home.FeedScope(new_only=new_only)
    )
    pool = search_engine.apply_filters(
        base_pool, search_engine.SearchFilters(kats=filters_eff.kats, tags=filters_eff.tags)
    )
    return broad, whole_pool, base_pool, pool


def _district_tail(
    portal,
    district,
    *,
    city,
    business_type,
    facet,
    q_eff,
    filters_eff,
    kinds,
    scope,
    point,
    geo_carry,
    page,
    collapse,
    dated_search,
    main_fuzzy=False,
):
    """Г5: группы «Auch in der Nähe» + подпись района, или ([], "").

    Только на последней странице выдачи района, только если район не «живой». Не для
    сорта «Nähe» (там нет страницы — близость уже задана точкой) и не для поиска отеля
    по датам (доступность соседей не проверяем)."""
    from dataclasses import replace
    from urllib.parse import quote

    from apps.core import districts

    from . import district_liveness
    from . import search as search_engine

    if (
        not district
        or not portal.city
        or page is None
        or page.has_more
        or dated_search
        or main_fuzzy
        or district_liveness.is_live(portal, district, business_type)
    ):
        return [], ""
    tail_filters = replace(filters_eff, districts=())
    # Та же область, что у страницы района: вид/«Neu», запрос (уже без фразы района),
    # фильтры и точка; курсор — позиция в чужой выдаче, его не переносим.
    carry = urlencode(
        [(k, v) for k, v in _scope_pairs(scope) + search_engine.carry(q_eff, tail_filters)]
        + list(geo_carry)
    )
    facet_part = f"{quote(facet, safe='')}/" if facet else ""

    def pool_for(slug):
        outcome, _whole, _base, pool = _district_pool(
            portal,
            city,
            business_type,
            slug,
            q_eff,
            tail_filters,
            kinds,
            scope.new_only,
            point,
            fuzzy=False,  # точный полнотекст: хвост не множит trigram-сканы
        )
        return pool, outcome

    def more_url_for(slug):
        path = f"/stadtteil/{slug}/{facet_part}"
        return f"{path}?{carry}" if carry else path

    groups = district_liveness.neighbor_tail(
        portal,
        district,
        pool_for=pool_for,
        more_url_for=more_url_for,
        collapse=collapse,
        business_type=business_type,
    )
    if not groups:
        return [], ""
    return groups, districts.label(portal.city, district)


# FLT-1b (план §12.2): страница с ЛЮБЫМ из этих параметров — вариация выдачи, а не
# лендинг: noindex,follow и canonical на себя. Курсор/номер страницы сами по себе — нет.
NOINDEX_PARAMS = frozenset(
    {"q", "kind", "neu", "sort", "lat", "lng", "roh", "ansicht", "kat", "merkmal"}
)


def _seo_canonical(request, portal, district, facet, filters) -> tuple[str, bool]:
    """(canonical, noindex) страницы портала.

    Путь (корень, `/stadtteil/<slug>/`, `/<facet>/`) без query — индексируемый лендинг,
    canonical = путь. Ровно один район параметром и больше ничего (`/?stadtteil=a`,
    `/stadtteil/a/?stadtteil=a`) — дубль путевой страницы района: canonical на неё,
    без noindex (смешивать noindex с чужим canonical поисковики не советуют).
    Прочие query-вариации — noindex,follow и canonical на себя."""
    from urllib.parse import quote

    from . import search as search_engine

    keys = {k for k, vals in request.GET.lists() if any((v or "").strip() for v in vals)}
    variation = keys & (NOINDEX_PARAMS | set(search_engine.FILTER_PARAMS))
    if not variation:
        return request.build_absolute_uri(request.path), False
    area = area_districts(district, filters)
    # Только без отрасли и у портала с городом: страница района с отраслью 404, если
    # отрасли в районе нет, а без города путевых страниц районов нет вовсе (ревью FLT-1b).
    if (
        variation == {"stadtteil"}
        and portal.city
        and not facet
        and len(area) == 1
        and filters.districts == area[:1]
    ):
        path = f"/stadtteil/{quote(area[0], safe='')}/"
        return request.build_absolute_uri(path), False
    return request.build_absolute_uri(request.get_full_path()), True


def _category_nav(filters, q) -> dict | None:
    """PH-11c: страница раздела — ровно один `?kat=` без поиска. {"current", "section"}:
    раздел, к которому принадлежит выбранная категория (или он сам), — для дерева слева
    и плиток подкатегорий над выдачей."""
    from apps.core import city_categories as cc

    if q or len(filters.kats) != 1:
        return None
    key = filters.kats[0]
    if cc.section(key):
        return {"current": key, "section": key}
    cat = cc.category(key)
    return {"current": key, "section": cat.section} if cat else None


def _category_tree(menu, carry, path) -> list[dict]:
    """PH-11c: дерево разделов страницы раздела — данные мега-меню (кэш), но ссылки несут
    текущие фильтры (район, цена, сортировка…): переход между разделами их не сбрасывает.
    Раздела нет в меню (кэш ещё не видит его) — дерева нет."""
    keep = [(k, v) for k, v in carry if k not in ("kat", "cursor", "kind")]

    def url(key):
        return f"{path}?{urlencode([('kind', 'alle'), ('kat', key), *keep])}"

    return [
        {**s, "url": url(s["key"]), "subs": [{**c, "url": url(c["key"])} for c in s["subs"]]}
        for s in menu
    ]


def _split_open_later(cards):
    """PH-11b: (сейчас доступные, позже открывающиеся) — устойчиво, порядок внутри сохранён.

    «Позже» = у бизнеса есть часы и он сейчас закрыт (или на каникулах). Без часов (онлайн-
    товары, мероприятия) — не прячем. Оплаченные позиции остаются наверху с пометкой."""
    now_, later = [], []
    for card in cards:
        closed = bool(getattr(card, "holiday_until", None)) or (
            getattr(card, "has_hours", False) and not getattr(card, "open_now", False)
        )
        (later if closed and not card.is_featured_now else now_).append(card)
    return now_, later


def _header_search(hidden, filters, district) -> dict:
    """PH-11a: поля шапки «Wo/Wann» + скрытые параметры БЕЗ того, что поля шапки задают сами.

    Шапка ВЛАДЕЕТ районом и временем: «Wo» = район пути `/stadtteil/<slug>/` или первый
    выбранный, «Wann» = heute/wochenende/дата из `datum`, иначе «jetzt» при `offen=1`.
    Поэтому `stadtteil`, `datum` и `offen` в скрытые НЕ идут: иначе дубль имени перетёр бы
    выбор (QueryDict.get берёт последнее), а «Jederzeit»/«Ganz <Stadt>» не снимали бы фильтр.
    Тонкий мультивыбор районов и «offen + heute» остаются в панели фильтров."""
    wo = district or (filters.districts[0] if filters.districts else "")
    wann = filters.date or ("jetzt" if filters.open_now else "")
    out = [(k, v) for k, v in hidden if k not in ("stadtteil", "datum", "offen")]
    custom = wann not in ("", "jetzt", "heute", "wochenende")
    return {
        "header_hidden": out,
        "header_wo": wo,
        "header_wann": wann,
        "header_wann_custom": custom,
        # PH-13a: подсказка «In <раздел> suchen» честна, только если раздел едет в форме
        "header_scoped": any(k == "kat" for k, _v in out),
    }


def _filter_ui(
    request,
    portal,
    *,
    city,
    business_type,
    district,
    facet,
    facets,
    axis,
    scope,
    q,
    q_eff,
    filters,
    filters_eff,
    kinds,
    point,
    broad,
    whole_pool,
    base_pool,
    pool,
    firm_total,
) -> dict:
    """FLT-1d: панель фильтров городского портала со счётчиками (portal_facets)."""
    from dataclasses import replace

    from apps.core import districts as district_registry

    from . import portal_facets, portal_filter_ui

    area = area_districts(district, filters_eff)
    if area:  # счётчикам соседних районов нужен пул БЕЗ района (свой фасет не учитывается)
        # Точный полнотекст: «похожие» по соседям не множат trigram-сканы (как хвост Г5);
        # при опечатке соседние районы без точных совпадений просто не показываются.
        _b, _w, wide_base, _p = _pool_chain(
            portal,
            city,
            business_type,
            (),
            q_eff,
            replace(filters_eff, districts=()),
            kinds,
            scope.new_only,
            point,
            fuzzy=False,
        )
    else:
        wide_base = base_pool
    counts = portal_facets.counts(
        wide_base,
        district_options=[slug for slug, _n in district_registry.choices_for(portal.city or "")],
        area=area,
        kats=filters_eff.kats,
        tags=filters_eff.tags,
    )
    # «N Treffer» — точное число (потолок 240 — только у пагинации, план §13.4).
    hits = pool.order_by().values("pk").count() + firm_total
    branch_facets = facets
    if not facet and axis == "business_type" and facets:
        types = set(whole_pool.order_by().values_list("business_type", flat=True).distinct())
        branch_facets = [(v, label) for v, label in facets if v in types]
    return portal_filter_ui.build(
        request,
        portal,
        facet=facet,
        facets=branch_facets,
        axis=axis,
        district=district,
        scope=scope,
        q=q,
        filters=filters,
        area=area_districts(district, filters),
        point=point,
        counts=counts,
        hits=hits,
        hits_capped=False,
    )


def _single_area(path_district, filters) -> str:
    """Г5: хвост соседей — только когда область выдачи ровно один район."""
    area = area_districts(path_district, filters)
    return area[0] if len(area) == 1 else ""


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
    # FLT-1d: на городском портале районы — в строке фильтров (считаются там же)
    district_chips = [] if portal_home_blocks.has_home(portal) else _district_choices(portal)

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
    # T-8.10d: правило вынесено в home.default_kind — им же пользуется подписка на поиск.
    kind = home.default_kind(scope.kind_key, q, filters)
    kinds = home.kinds_for(kind) or AggregatorListing.OFFER_KINDS
    broad, whole_pool, base_pool, pool = _district_pool(
        portal, city, business_type, district, q_eff, filters_eff, kinds, scope.new_only, point
    )
    # Параметры поиска/фильтров (кроме категорий) — в ссылках вкладок, чипов и формы.
    # T-8.7: координаты посетителя едут в ссылках отдельно (geo.carry), НЕ в search.carry —
    # иначе они попали бы в журнал поиска T-8.21.
    geo_carry = geo.carry(near_lat, near_lng)
    carry = [
        (k, v) for k, v in search_engine.carry(q, filters) if k not in ("kat", "merkmal")
    ] + geo_carry
    # T-8.26 п.4 (Р-5): вкладки НЕ сбрасывают раздел/признак, а их видимость считается
    # по пулу С разделом — показанная вкладка ⇒ непустая выдача.
    # PH-14: вид (Liste/Karte) тоже не сбрасывается вкладками, чипами, новым запросом и
    # подсказками намерения — иначе «Produkte» возвращал бы плитки (django-ревью PH-14).
    view_carry = [("ansicht", geo.view_mode(request))] if geo.view_mode(request) else []
    tab_carry = list(search_engine.carry(q, filters)) + geo_carry + view_carry
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
        # PH-2: мега-меню «Kategorien» — общий пул портала, кэш 5 минут (0 запросов в тепле).
        portal_menu = home.cached_menu_sections(
            portal, portal_scope.pool(portal), reverse("portal-home")
        )
    else:
        portal_menu = []
        kind_chips = _kind_chips(whole_pool.order_by(), request.path, kind)
        portal_tabs = []
    if city_home:  # FLT-1d: разделы и признаки — в строке фильтров; нужна только подпись
        from apps.core import city_categories as cc

        labels = [cc.label(k) for k in filters_eff.kats] + [
            cc.tag_label(t) for t in filters_eff.tags
        ]
        category_chips = {"label": " · ".join(x for x in labels if x)}
        district_chips = []
    else:
        category_chips = category_facets.chips(
            base_pool.order_by(),  # без ранга: чипам нужен только состав
            request.path,
            kat,
            tag,
            extra={"kind": scope.kind_key, "neu": "1" if scope.new_only else "", **dict(carry)},
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
    if searching and not city_home:  # FLT-1d: на городском портале — строка фильтров
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
    flt = None
    if city_home:  # FLT-1d: строка пилюль + шторка (вместо формы «Filter» и «Eingrenzen»)
        flt = _filter_ui(
            request,
            portal,
            city=city,
            business_type=business_type,
            district=district,
            facet=facet,
            facets=facets,
            axis=axis,
            scope=scope,
            q=q,
            q_eff=q_eff,
            filters=filters,
            filters_eff=filters_eff,
            kinds=kinds,
            point=point,
            broad=broad,
            whole_pool=whole_pool,
            base_pool=base_pool,
            pool=pool,
            firm_total=firm_total,
        )
        if searching and not (point is not None and filters.sort in ("", "naehe")):
            cap = settings.AGGREGATOR_SEARCH["max_results"]
            hits, hits_capped = min(flt["hits"], cap), flt["hits"] > cap  # ИИ-подсказка, журнал
    # T-8.10d D-2: ИИ-подсказка фильтров (за выключателем; проверяется первой — при
    # выключенном флаге путь страницы прежний байт-в-байт).
    ki_slot, ki_chips, ki_landing = None, [], False
    from . import ai_search

    if ai_search.any_enabled():
        if searching:
            ki_slot = ai_search.slot_context(
                request,
                surface="portal",
                q=q,
                q_eff=q_eff,
                city=city or "",
                lang=broad.lang,
                results=hits,
                portal_host=portal.host,
                path_district=district or "",
                business_type=business_type or "",
                fuzzy=broad.mode in ("trigram", "empty"),
            )
        ki_chips = ai_search.landing_chips(request, city=city or "")
        ki_landing = bool(ki_chips)
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
            **({"ki": "1"} if ki_landing else {}),  # T-8.10d D-2: замер принятия подсказки
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
    # Г5: район с малым числом бизнесов — под его выдачей подписанный хвост соседей.
    # Хвост необязателен: ошибка его выборки (таймаут, БД) не роняет страницу района.
    try:
        district_tail, tail_label = _district_tail(
            portal,
            _single_area(district, filters_eff),
            city=city,
            business_type=business_type,
            facet=facet,
            q_eff=q_eff,
            filters_eff=filters_eff,
            kinds=kinds,
            scope=scope,
            point=point,
            geo_carry=geo_carry,
            page=page,
            collapse=_collapse_hotels if hotel_portal else None,
            dated_search=search is not None,
            main_fuzzy=broad.mode == "trigram",  # «ähnliche» выдача района — соседей не зовём
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("g5: district tail failed", exc_info=True)
        district_tail, tail_label = [], ""
    from . import reviews

    reviews.attach_ratings(cards)  # G8b: звёзды в выдаче
    tail_items = [i for g in district_tail for i in g["items"]] if district_tail else []
    if tail_items:
        reviews.attach_ratings(tail_items)
    # PH-3: «Endet in …» и часы работы на карточках — один запрос к Tenant на всю выдачу.
    from .portal_cards import prepare_cards

    prepare_cards(list(cards) + tail_items)
    # PH-11b: при порядке по умолчанию закрытые сейчас — после разделителя «Später geöffnet»
    # (в пределах загруженной страницы; «Wie wir sortieren» говорит об этом). Явный сорт
    # посетителя (endet/neu/offen/naehe), «рядом» и поиск отелей по датам — порядок не трогаем.
    cat_nav = _category_nav(filters, q) if flt else None
    cat_tree = []
    if cat_nav and any(s["key"] == cat_nav["section"] for s in portal_menu):
        cat_tree = _category_tree(portal_menu, tab_carry, request.path)
    else:
        cat_nav = None
    cards_later = []
    if flt and page is not None and not filters.sort and not hotel_portal:
        cards, cards_later = _split_open_later(cards)
    canonical, robots_noindex = _seo_canonical(request, portal, district, facet, filters)
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

        if district and area_districts(district, filters) == (district,):
            # путь ∪ ?stadtteil=b — уже не «район a»: такой набор — кнопкой подписки на поиск
            follow_target = follow.parse_target({"stadtteil": district}, portal=portal)
        elif len(filters.kats) == 1:
            follow_target = follow.parse_target({"bereich": filters.kats[0]}, portal=portal)
    # T-8.10d: подписка на ЭТОТ набор фильтров — ссылка под выдачей (кэш P0-1).
    search_follow = None
    if searching and not facet:
        from . import follow_query

        search_follow = follow_query.follow_link(
            request.GET, portal=portal, path_district=district or ""
        )
    return render(
        request,
        "aggregator/portal_home.html",
        {
            "portal": portal,
            "portal_menu": portal_menu,
            "follow_target": follow_target,
            "ki_slot": ki_slot,
            "ki_chips": ki_chips,
            "search_follow": search_follow[0] if search_follow else None,
            "search_follow_qs": search_follow[1] if search_follow else "",
            "following": follow.is_following(user, follow_target) if follow_target else False,
            "page": page,
            "cards": cards,
            "cards_later": cards_later,
            "cat_nav": cat_nav,
            "cat_tree": cat_tree,
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
            # PH-14: «Liste» — строки на всех ширинах; поиск на телефоне — строки (PH-13d)
            "cards_layout": (
                "rows" if geo.view_mode(request) == "liste" else ("list" if q else "")
            ),
            "category_chips": category_chips,  # T-8.13a
            "kind_chips": kind_chips,  # T-8.11
            "portal_tabs": portal_tabs,  # T-8.19
            "search_q": q,
            "search_kind": scope.kind_key,
            "search_mode": broad.mode,
            # T-8.26 п.5a: пилюли «Erkannt: …» (✕ = запрос без фразы / roh=ort у района)
            "intent_chips": _intent_chip_links(
                request, intent_chips, filters, geo_carry + view_carry, scope
            ),
            "intent_hints": _intent_hint_links(
                request, intent_hints, pool, q, filters, geo_carry + view_carry, scope
            ),
            # T-8.20: новый запрос не сбрасывает вкладку и фильтры.
            "search_hidden": (
                search_hidden := [
                    (k, v)
                    for k, v in [
                        ("kind", scope.kind_key if scope.kind_key != "alle" else ""),
                        ("neu", "1" if scope.new_only else ""),
                    ]
                    + search_engine.carry("", filters)
                    + geo_carry
                    + view_carry
                    + [("roh", v) for v in request.GET.getlist("roh") if v == "ort"]
                    if v
                ]
            ),
            **_header_search(search_hidden, filters, district),
            # T-8.20: блок фильтров и пилюли активных фильтров (только у городского портала).
            "flt": flt,
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
                + ([("ansicht", geo.view_mode(request))] if geo.view_mode(request) else [])
            ),
            # T-8.15: портал показывает демо-бизнесы — честная полоса «Vorschau».
            "shows_demo": portal.show_demo
            and any(
                getattr(c, "is_demo", False)
                for c in [*cards, *(i for g in district_tail for i in g["items"])]
            ),
            "district_tail": district_tail,  # Г5
            "tail_district_label": tail_label,
            "business_link": True,  # G8b: на порталах звёзды ведут на страницу бизнеса
            "near_active": point is not None and filters.sort in ("", "naehe"),  # G8c
            "map_points": geo.map_points(cards),
            "canonical": canonical,
            "robots_noindex": robots_noindex,  # FLT-1b (план §12): query-вариации
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


def _fav_ids(request) -> set:
    from . import auth
    from .models import FavoriteListing

    user = auth.current_portal_user(request)
    if not user:
        return set()
    return set(FavoriteListing.objects.filter(user=user).values_list("listing_id", flat=True))


def _render_home(request, portal):
    """T-8.19/PH-11d: «Heute in <город>» по макету K1 — баннер, quad-карточки, «Anzeigen»,
    «Das Beste aus jedem Bereich», «Geschäfte», «Top-Aktionen».

    Число запросов не зависит от объёма данных: presence (1), featured (≤2), блоки (по 1,
    питают карточки), «Beliebt» (≤2, кэш), «Das Beste» (1), «Geschäfte» (2), «Top-Aktionen»
    (1), рейтинги (1). Корень без query кэшируется.
    """
    from . import portal_home_blocks as home
    from . import reviews

    base = portal_scope.pool(portal)
    present = home.presence(base)
    # Показы платных позиций считаем только на «чистом» корне (кэшируемый рендер):
    # иначе боты с `?x=<мусор>` накручивали бы метрику, которую видят владельцы.
    featured = home.featured(base, count_impressions=not request.GET) if present["total"] else []
    # PH-4: «Deal des Tages» — органическое правило; платные (featured) исключены.
    deal = (
        home.deal_of_day(base, exclude_pks={item.pk for item in featured})
        if present["total"]
        else None
    )
    stats = home.home_stats(base) if present["total"] else {}
    # Один снимок часов на весь пул: им же «N geöffnet» и строки часов на карточках.
    snapshot = home.open_snapshot_for(base) if present["total"] else {}
    open_set = home.open_schemas(snapshot)
    blocks = (
        home.home_blocks(
            base,
            city=portal.city,
            path=request.path,
            exclude_pks={item.pk for item in featured} | ({deal.pk} if deal else set()),
        )
        if present["total"]
        else []
    )
    # PH-6: «Jetzt geöffnet» — вторым блоком, без повторов с остальными.
    taken = {item.pk for item in featured} | ({deal.pk} if deal else set())
    taken |= {item.pk for b in blocks for item in b["items"]}
    offen = home.open_block(base, open_set, path=request.path, exclude_pks=taken)
    if offen:
        blocks.insert(min(1, len(blocks)), offen)
    newbiz = home.new_businesses(base, path=request.path) if present["total"] else None
    if newbiz:  # «Neu in <город>» заменяет блок «Lokale Unternehmen» (без двух бизнес-блоков)
        blocks = [b for b in blocks if b["key"] != "unternehmen"]
    # PH-11d2 (макет K1): ряды блоков на главной не рисуются — блоки питают quad-карточки;
    # ниже карточек — «Das Beste aus jedem Bereich», «Geschäfte», «Top-Aktionen».
    quad = (
        home.quad_cards(
            base, blocks, open_set, portal_pk=portal.pk, path=request.path, snapshot=snapshot
        )
        if present["total"]
        else []
    )
    # Deal и «Anzeigen» уже на экране — в «Das Beste» и «Top-Aktionen» не повторяем.
    shown = {item.pk for item in featured} | ({deal.pk} if deal else set())
    # Ряд карточек рисуется от двух карточек — исключаем только то, что реально на экране.
    in_quad = {item.pk for c in quad for item in c["items"]} if len(quad) > 1 else set()
    shown |= in_quad
    best = (
        home.best_by_section(
            base, present, open_set, snapshot, path=request.path, exclude_pks=shown
        )
        if present["total"]
        else []
    )
    # Страховка малого портала: без «Das Beste» (мало данных или предложения без раздела)
    # главная не пустеет — ряды блоков остаются, без того, что уже показали карточки.
    rows = []
    if not best:
        for b in blocks:
            items = [i for i in b["items"] if i.pk not in in_quad]
            if items:
                rows.append({**b, "items": items})
    busy = home.busy_businesses(base, path=request.path) if present["total"] else None
    tops = home.top_actions(base, path=request.path, exclude_pks=shown) if present["total"] else []
    cards = (
        featured
        + ([deal] if deal else [])
        + [item for c in quad for item in c["items"]]
        + [item for b in best for item in b["items"]]
        + [item for b in rows for item in b["items"]]
        + tops
    )
    reviews.attach_ratings(cards)
    # PH-3: «Endet in …» и часы работы на карточках — из общего снимка (0 запросов).
    from .portal_cards import prepare_cards

    prepare_cards(cards, snapshot=snapshot)
    canonical = request.build_absolute_uri(request.path)
    return render(
        request,
        "aggregator/portal_discover.html",
        {
            "portal": portal,
            "deal": deal,
            "quad_cards": quad,
            "best_sections": best,
            "blocks": rows,
            "busy": busy,
            "top_actions": tops,
            "slides": portal_slides.slides(
                portal, deal=deal, stats=stats, newbiz=newbiz, path=request.path
            ),
            "stats": stats,
            "open_count": len(open_set),
            "pool_empty": not present["total"],
            # PH-2: меню «Kategorien» — из уже посчитанного presence, без запросов.
            "portal_menu": home.menu_sections(present, request.path),
            "featured": featured,
            "newbiz": newbiz,
            "shows_demo": portal.show_demo and any(getattr(c, "is_demo", False) for c in cards),
            "business_link": True,
            "canonical": canonical,
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
    pool = portal_scope.pool(portal, include_demo=False)
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
PORTAL_DISALLOW = (
    "/klick/",
    "/weiter/",
    "/stat/",
    "/melden/",
    "/konto/",
    "/tg/",
    "/sprache/",
    "/folgen/",
    "/mcp/",
    "/ki-vorschlag/",
)


def portal_ki_suggest(request):
    """T-8.10d D-2: фрагмент ИИ-подсказки фильтров (подписанный токен со страницы выдачи)."""
    from . import ai_search

    return ai_search.fragment(request, portal=getattr(request, "portal", None))


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
        portal=portal,
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
