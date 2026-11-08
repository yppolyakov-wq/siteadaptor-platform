"""T-8.19: главная городского портала «Entdecke <город>» — вкладки, плитки разделов, блоки.

План — docs/t8-19-portal-home-plan-2026-10-15.md. Главный принцип: у каждого блока один
``FeedScope``. По нему строится и выборка блока, и ссылка «Alle →»; лента разбирает ту же
ссылку обратно в тот же ``FeedScope`` (``parse_scope``) — «Alle →» всегда ведёт на набор,
содержащий все карточки блока. Все выборки — поверх ``listings_for`` (``objects.public()``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Case, CharField, Count, F, IntegerField, Max, Q, Value, When, Window
from django.db.models.functions import MD5, Cast, Concat, RowNumber
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import city_categories as cc

from .models import AggregatorListing as L
from .models import apply_city_filters
from .search import FILTER_PARAMS
from .tasks import NEW_PRODUCT_DAYS

logger = logging.getLogger(__name__)

NEW_DAYS = NEW_PRODUCT_DAYS  # «Neu» = свежий листинг или бейдж «neu» товара
# Решение владельца 2026-11-05: ряд главной — 4 карточки; 8 (два полных ряда) — только
# если набралось 8, иначе не больше 4 (6 давало неполный второй ряд на сетке из 4).
BLOCK_LIMIT = 8
BLOCK_ROW = 4
FEATURED_LIMIT = 3
# Параметры, превращающие корень портала в ленту. Посторонние (?ch=, ?utm_*) — нет:
# ссылка из соцсети обязана открыть главную.
FEED_PARAMS = frozenset(
    {
        "kind",
        "kat",
        "merkmal",
        "q",
        "neu",
        "cursor",
        "lat",
        "lng",
    }
    # T-8.20: фильтры единого поиска — ИЗ реестра, не копией (T-8.26 п.5c: `groesse`
    # в копию не попал → `?groesse=M` открывал главную блоками и молча терял фильтр).
    | frozenset(FILTER_PARAMS)
)
SEARCH_MAX = 100

ALL_KINDS = tuple(k for k, _label in L.KINDS)
GROUPS = {
    "alle": ALL_KINDS,
    # Номера — в «Angebote»: отдельной вкладки по ТЗ нет, но вид обязан быть достижим.
    "angebote": (L.KIND_PROMOTION, L.KIND_MENU, L.KIND_STAY),
}


@dataclass(frozen=True)
class FeedScope:
    kind_key: str = ""  # "alle" | "angebote" | <вид> | "" (лента по умолчанию)
    kat: str = ""
    tag: str = ""
    new_only: bool = False


@dataclass(frozen=True)
class Tab:
    key: str
    label: object
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class Block:
    key: str
    title: object  # может содержать %(city)s
    scope: FeedScope
    order: str
    per_business: int = 2
    exclude_kinds: tuple[str, ...] = ()
    exclude_sold_out: bool = False


TABS: tuple[Tab, ...] = (
    Tab("alle", _("Alle"), ALL_KINDS),
    Tab(L.KIND_PRODUCT, _("Produkte"), (L.KIND_PRODUCT,)),
    Tab("angebote", _("Angebote"), GROUPS["angebote"]),
    Tab(L.KIND_SERVICE, _("Dienstleistungen"), (L.KIND_SERVICE,)),
    Tab(L.KIND_BUSINESS, _("Unternehmen"), (L.KIND_BUSINESS,)),
    Tab(L.KIND_EVENT, _("Events"), (L.KIND_EVENT,)),
)

BLOCKS: tuple[Block, ...] = (
    Block(
        "angebote",
        _("Aktuelle Angebote"),
        FeedScope(kind_key="angebote"),
        "urgent",
    ),  # PH-6: заголовок «Endet bald», если есть срочные (home_blocks)
    Block(
        "produkte",
        _("Produkte aus %(city)s"),
        FeedScope(kind_key=L.KIND_PRODUCT),
        "regional_first",
        exclude_sold_out=True,
    ),
    Block(
        "essen",
        _("Essen & Trinken"),
        FeedScope(kind_key="alle", kat="essen-gastronomie"),
        "newest",
        exclude_kinds=(L.KIND_BUSINESS,),
    ),
    Block(
        "freizeit",
        _("Freizeit"),
        FeedScope(kind_key="alle", kat="freizeit-erlebnisse"),
        "upcoming",
        exclude_kinds=(L.KIND_BUSINESS,),
    ),
    Block(
        "unternehmen",
        _("Lokale Unternehmen"),
        FeedScope(kind_key=L.KIND_BUSINESS),
        "daily_rotation",
        per_business=1,
    ),
    Block(
        "neu",
        _("Neu"),
        FeedScope(kind_key="alle", new_only=True),
        "newest",
        per_business=1,
        exclude_sold_out=True,
    ),
)


def kinds_for(kind_key: str) -> tuple[str, ...] | None:
    """Виды листинга группы/вида; None — пусто или мусор."""
    if kind_key in GROUPS:
        return GROUPS[kind_key]
    if kind_key in ALL_KINDS:
        return (kind_key,)
    return None


def default_kind(scope_kind: str, q: str, filters) -> str:
    """Вид выдачи по умолчанию — ОДНО правило для портала и подписок (T-8.10d).

    Без явного ``?kind=`` лента — предложения (акции/номера/события/меню). Поиск,
    раздел/признак, размер и марка ищут по всем видам: «Brot», «Größe M», «Bosch»
    обязаны находить товары, иначе выдача пустая (T-8.26 п.4/п.5c, T-8.10d)."""
    if scope_kind:
        return scope_kind
    if (
        q
        or filters.kats
        or filters.tags
        or filters.size
        or getattr(filters, "brand", "")
        or getattr(filters, "business", "")
    ):
        return "alle"
    return ""


def search_query(request) -> str:
    return (request.GET.get("q") or "").strip()[:SEARCH_MAX]


def parse_scope(request) -> FeedScope:
    """Разбор ссылки ленты (``?kind=&kat=&merkmal=&neu=``) — обратная к ``scope_url``."""
    from . import category_facets

    kind_key = (request.GET.get("kind") or "").strip()
    if kinds_for(kind_key) is None:
        kind_key = ""
    kat, tag = category_facets.selected(request)
    if len(request.GET.getlist("kat")) > 1:  # T-8.20: несколько разделов — не чип-область
        kat = ""
    if len(request.GET.getlist("merkmal")) > 1:
        tag = ""
    return FeedScope(kind_key=kind_key, kat=kat, tag=tag, new_only=request.GET.get("neu") == "1")


def scope_url(path: str, scope: FeedScope) -> str:
    params = [
        (k, v)
        for k, v in (
            ("kind", scope.kind_key),
            ("kat", scope.kat),
            ("merkmal", scope.tag),
            ("neu", "1" if scope.new_only else ""),
        )
        if v
    ]
    return f"{path}?{urlencode(params)}" if params else path


def apply_scope(qs, scope: FeedScope, *, now=None):
    """Фильтры области поверх готового пула ``listings_for`` (вид, категория, признак, новизна)."""
    kinds = kinds_for(scope.kind_key)
    if kinds is not None:
        qs = qs.filter(listing_kind__in=kinds)
    qs = apply_city_filters(qs, scope.kat, scope.tag)
    if scope.new_only:
        since = (now or timezone.now()) - timedelta(days=NEW_DAYS)
        qs = qs.filter(Q(is_new=True) | Q(created_at__gte=since))
    return qs


def is_home_request(portal, facet, district, request) -> bool:
    """Корень городского портала без параметров ленты → главная (Р-1 плана)."""
    return (
        portal.kind in (portal.KIND_CITY, portal.KIND_THEME)
        and bool(portal.city)
        and not portal.business_type
        and facet is None
        and district is None
        and not any((request.GET.get(key) or "").strip() for key in FEED_PARAMS)
    )


def has_home(portal) -> bool:
    """Портал, у которого есть главная с вкладками (городской, без типа бизнеса)."""
    return (
        portal.kind in (portal.KIND_CITY, portal.KIND_THEME)
        and bool(portal.city)
        and not portal.business_type
    )


def presence(base_qs) -> dict:
    """ОДИН запрос: число карточек по видам и разделам справочника."""
    rows = (
        base_qs.order_by()
        .values("listing_kind", "city_category")
        .annotate(n=Count("id"))
        .values_list("listing_kind", "city_category", "n")
    )
    kinds: dict[str, int] = {}
    sections: dict[str, int] = {}
    categories: dict[str, int] = {}
    for kind, cat_key, n in rows:
        kinds[kind] = kinds.get(kind, 0) + n
        cat = cc.category(cat_key) if cat_key else None
        if cat:
            sections[cat.section] = sections.get(cat.section, 0) + n
            categories[cat.key] = categories.get(cat.key, 0) + n
    return {
        "kinds": kinds,
        "sections": sections,
        "categories": categories,
        "total": sum(kinds.values()),
    }


def tabs(present: dict, active_key: str, path: str, *, carry=()) -> list[dict]:
    """Вкладки — только с данными; «Alle» = главная (при поиске/фильтрах — лента по всем
    видам). ``carry`` — параметры поиска и фильтров, которые вкладка не сбрасывает."""
    kinds = present["kinds"]
    shown = [t for t in TABS if any(kinds.get(k) for k in t.kinds)]
    if len([t for t in shown if t.key != "alle"]) < 2:  # «Alle» = единственная группа
        return []
    out = []
    for t in shown:
        if t.key == "alle" and not carry:
            url = path
        else:
            url = f"{path}?{urlencode([('kind', t.key), *carry])}"
        active = t.key == active_key or (
            t.key == "angebote" and active_key in (L.KIND_PROMOTION, L.KIND_MENU, L.KIND_STAY)
        )
        out.append({"key": t.key, "label": t.label, "url": url, "active": active})
    return out


MENU_POPULAR = 3  # бейдж «Beliebt» — топ-N разделов по числу предложений (факт, не реклама)
MENU_CACHE_TTL = 300


def menu_sections(present: dict, path: str) -> list[dict]:
    """PH-2: разделы мега-меню «Kategorien» — только непустые; подкатегории со счётчиком;
    описание в одну строку = первые подписи подкатегорий (новых текстов не нужно)."""
    from . import portal_icons

    sections = present["sections"]
    categories = present.get("categories", {})
    top = sorted(sections, key=lambda k: -sections[k])[:MENU_POPULAR]
    out = []
    for s in cc.SECTIONS:
        if not sections.get(s.key):
            continue
        subs = [
            {
                "key": c.key,
                "label": str(c.label),
                "count": categories[c.key],
                "url": scope_url(path, FeedScope(kind_key="alle", kat=c.key)),
            }
            for c in cc.CATEGORIES
            if c.section == s.key and categories.get(c.key)
        ]
        labels = [str(c.label) for c in cc.CATEGORIES if c.section == s.key][:3]
        out.append(
            {
                "key": s.key,
                "label": str(s.label),
                "icon": portal_icons.icon_for(s.key),
                "count": sections[s.key],
                "desc": ", ".join(labels),
                "popular": s.key in top,
                "url": scope_url(path, FeedScope(kind_key="alle", kat=s.key)),
                "subs": subs,
            }
        )
    return out


def cached_menu_sections(portal, base_qs, path: str) -> list[dict]:
    """Меню для страниц, где presence не считается: Redis на 5 минут, fail-open (без меню —
    кнопка ведёт на якорь главной)."""
    from django.core.cache import cache
    from django.utils.translation import get_language

    key = f"portal_menu:{portal.pk}:{get_language() or ''}:{path}"
    try:
        hit = cache.get(key)
        if hit is not None:
            return hit
        value = menu_sections(presence(base_qs), path)
        cache.set(key, value, MENU_CACHE_TTL)
        return value
    except Exception:  # noqa: BLE001 — меню не обязательно, страница не падает
        logger.warning("portal menu failed", exc_info=True)
        return []


def _order(key: str, now=None) -> list:
    if key == "urgent":  # срочное первым (О-4) — тот же порядок, что сорт «Endet bald»
        from .search import ORDERINGS

        return list(ORDERINGS["endet"])
    if key == "regional_first":
        return [
            Case(
                When(city_tags__contains=["regional"], then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "-created_at",
            "-pk",
        ]
    if key == "upcoming":
        return [
            Case(
                When(starts_at__gte=now or timezone.now(), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            F("starts_at").asc(nulls_last=True),
            "-created_at",
            "-pk",
        ]
    if key == "daily_rotation":  # честно ко всем бизнесам, стабильно в пределах дня/кэша
        salt = Value(timezone.localdate().isoformat(), output_field=CharField())
        return [MD5(Concat(Cast("id", CharField()), salt, output_field=CharField())), "pk"]
    from .search import ORDERINGS

    return list(ORDERINGS["neu"])


def featured(base_qs, *, count_impressions: bool = True) -> list:
    """Полоса «Anzeigen» (UWG §5a): платные позиции отдельно от органических блоков."""
    from .views import split_featured

    pool = base_qs.filter(listing_kind__in=(*GROUPS["angebote"], L.KIND_PRODUCT, L.KIND_SERVICE))
    items, _rest = split_featured(
        pool, first_page=True, limit=FEATURED_LIMIT, count_impressions=count_impressions
    )
    return items


def _as_expressions(order: list) -> list:
    """Строки order_by → выражения (Window.order_by не принимает «-поле»)."""
    out = []
    for term in order:
        if isinstance(term, str):
            out.append(F(term[1:]).desc() if term.startswith("-") else F(term).asc())
        else:
            out.append(term)
    return out


def home_blocks(base_qs, *, city: str, path: str, exclude_pks=(), now=None) -> list[dict]:
    """Непустые блоки главной: один запрос на блок, лимит на бизнес, без дублей между блоками."""
    seen = set(exclude_pks)
    out = []
    for block in BLOCKS:
        qs = apply_scope(base_qs, block.scope, now=now)
        if block.exclude_kinds:
            qs = qs.exclude(listing_kind__in=block.exclude_kinds)
        if block.exclude_sold_out:
            qs = qs.exclude(availability=L.AVAILABILITY_SOLD_OUT)
        if seen:
            qs = qs.exclude(pk__in=seen)
        order = _order(block.order, now)
        ranked = qs.annotate(
            business_rank=Window(
                RowNumber(),
                partition_by=[F("tenant_schema")],
                order_by=_as_expressions(order),
            )
        ).filter(business_rank__lte=block.per_business)
        items = list(ranked.order_by(*order)[:BLOCK_LIMIT])
        if len(items) < BLOCK_LIMIT:
            items = items[:BLOCK_ROW]
        if not items:
            continue
        seen.update(item.pk for item in items)
        title = str(block.title) % {"city": city}
        more_url = scope_url(path, block.scope)
        if block.order == "urgent":
            # PH-6: срочное первым — честный заголовок «Endet bald», если что-то кончается
            # в ближайшие сутки; «Alle anzeigen» — та же область, отсортированная по сроку.
            soon = (now or timezone.now()) + timedelta(days=1)
            if any(i.ends_at and i.ends_at <= soon for i in items):
                title = str(_("Endet bald"))
            more_url = f"{more_url}&sort=endet" if "?" in more_url else f"{more_url}?sort=endet"
        out.append(
            {
                "key": block.key,
                "title": title,
                "items": items,
                "more_url": more_url,
            }
        )
    return out


# --- PH-4: первый экран «Was gibt's heute in <город>?» -----------------------------------


def home_stats(base_qs, now=None) -> dict:
    """Цифры первого экрана — ОДИН aggregate по пулу портала (пул = «действует сейчас»)."""
    from .search import date_window

    now = now or timezone.now()
    # PH-11d1: слайды «Wochenende» и «Aus der Region» — те же условия, что лента по ссылке
    # слайда (?kind=event&datum=wochenende / ?merkmal=regional): число ⊆ ленты.
    start, end = date_window("wochenende", now=now)
    weekend = (
        Q(listing_kind=L.KIND_EVENT)
        & (Q(starts_at__isnull=True) | Q(starts_at__lt=end))
        & (Q(ends_at__isnull=True) | Q(ends_at__gte=start))
    )
    return base_qs.order_by().aggregate(
        businesses=Count("tenant_schema", distinct=True),
        offers=Count("id", filter=Q(listing_kind__in=L.OFFER_KINDS)),
        new_week=Count("id", filter=Q(created_at__gte=now - timedelta(days=7))),
        cheap=Count("id", filter=Q(new_price__lte=10)),
        weekend=Count("id", filter=weekend),
        regional=Count("id", filter=Q(city_tags__contains=["regional"])),
    )


def open_snapshot_for(base_qs) -> dict:
    """Снимок часов по всем схемам пула (2 запроса: схемы + Tenant) — им же карточки."""
    from .views import open_snapshot

    schemas = set(base_qs.order_by().values_list("tenant_schema", flat=True).distinct())
    return open_snapshot(schemas) if schemas else {}


def open_schemas(snapshot: dict) -> set:
    """Схемы, открытые сейчас (из готового снимка — 0 запросов)."""
    from .views import _open_now_schemas

    return _open_now_schemas(set(), snapshot=snapshot)


def deal_of_day(base_qs, *, exclude_pks=(), now=None):
    """«Deal des Tages» — ОРГАНИЧЕСКОЕ правило (UWG §5a: платное сюда не попадает никогда).

    Акция с фото и известной ценой (не mystery, без «2 für 1»-условия): сначала те, что
    заканчиваются сегодня, затем больший процент, затем дневная ротация (стабильно в
    пределах дня и кэша)."""
    now = now or timezone.now()
    end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    qs = (
        base_qs.filter(
            listing_kind=L.KIND_PROMOTION,
            discount_percent__isnull=False,
            new_price__isnull=False,
            price_condition={},
            is_surprise=False,
        )
        .exclude(image={})
        .exclude(featured_until__gt=now)
    )
    if exclude_pks:
        qs = qs.exclude(pk__in=exclude_pks)
    salt = Value(timezone.localdate().isoformat(), output_field=CharField())
    qs = qs.annotate(
        ends_today=Case(
            When(ends_at__lte=end_of_day, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        rotation=MD5(Concat(Cast("id", CharField()), salt, output_field=CharField())),
    )
    deal = qs.order_by("ends_today", "-discount_percent", "rotation").first()
    if deal is not None:
        deal.deal_reason = (
            _("Größter Rabatt, endet heute") if deal.ends_today == 0 else _("Größter Rabatt")
        )
    return deal


# --- PH-5: строка быстрых фильтров на главной (только ссылки — страница кэшируется) ----

PRICE_STEPS = (10, 20, 50)


# --- PH-6: блоки «Jetzt geöffnet» и районы со счётчиками --------------------------------


def open_block(base_qs, open_set: set, *, path: str, exclude_pks=()) -> dict | None:
    """«Jetzt geöffnet» — предложения открытых сейчас бизнесов, по одному на бизнес,
    дневная ротация. «Alle anzeigen» → лента с `offen=1` (её надмножество)."""
    if not open_set:
        return None
    qs = base_qs.filter(tenant_schema__in=open_set).exclude(listing_kind=L.KIND_BUSINESS)
    if exclude_pks:
        qs = qs.exclude(pk__in=exclude_pks)
    order = _order("daily_rotation")
    ranked = qs.annotate(
        business_rank=Window(
            RowNumber(), partition_by=[F("tenant_schema")], order_by=_as_expressions(order)
        )
    ).filter(business_rank__lte=1)
    items = list(ranked.order_by(*order)[:BLOCK_LIMIT])
    if len(items) < BLOCK_LIMIT:
        items = items[:BLOCK_ROW]
    if not items:
        return None
    return {
        "key": "offen",
        "title": _("Jetzt geöffnet"),
        "subtitle": _("Gerade geöffnet · täglich neu gemischt"),
        "items": items,
        "more_url": f"{path}?kind=alle&offen=1",
    }


NEW_BUSINESS_DAYS = 30
NEW_BUSINESS_MIN = 3  # меньше — блок не показываем («Neu» было бы неправдой)
NEW_BUSINESS_LIMIT = 6


def new_businesses(base_qs, *, path: str, now=None) -> dict | None:
    """«Neu in <город>» — карточки бизнесов, появившихся за 30 дней (по одной на бизнес).

    «Alle anzeigen» → лента бизнесов с `neu=1`. Меньше трёх — None (остаётся прежний блок
    «Lokale Unternehmen»)."""
    now = now or timezone.now()
    qs = (
        base_qs.filter(
            listing_kind=L.KIND_BUSINESS, created_at__gte=now - timedelta(days=NEW_BUSINESS_DAYS)
        )
        .order_by("tenant_schema", "-created_at")
        .distinct("tenant_schema")
    )
    items = sorted(qs[: NEW_BUSINESS_LIMIT * 2], key=lambda i: i.created_at, reverse=True)
    items = items[:NEW_BUSINESS_LIMIT]
    if len(items) < NEW_BUSINESS_MIN:
        return None
    return {"items": items, "more_url": f"{path}?kind=business&neu=1"}


# --- PH-11d1b: quad-карточки главной (макет K1) ------------------------------------------

QUAD_ITEMS = 4
POPULAR_DAYS = 7
POPULAR_MIN_VIEWS = 3  # порог честности: «beliebt» — не по одному случайному просмотру
POPULAR_MIN_ITEMS = 4  # меньше — карточка «Jetzt geöffnet» вместо «Beliebt»
POPULAR_CACHE = 15 * 60


def _popular_ids(base_qs, portal_pk, now) -> list[int]:
    """pk листингов с ≥ POPULAR_MIN_VIEWS просмотрами за неделю — по убыванию. ОДИН запрос
    по индексу дня (`agg_pstat_day_idx`), кэш 15 минут; fail-open (нет кэша — запрос).
    У PortalStat нет поля портала: рейтинг сужен до бизнесов пула (иначе чужие порталы и
    демо вытесняли бы свои позиции из топа), считаются только визиты людей с портала."""
    from django.core.cache import cache
    from django.db.models import Sum

    from .models import PortalStat

    key = f"portal_popular:{portal_pk}:{timezone.localdate(now).isoformat()}"
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001 — кэш недоступен: считаем напрямую
        cached = None
    if cached is not None:
        return cached
    since = timezone.localdate(now) - timedelta(days=POPULAR_DAYS - 1)
    ids = list(
        PortalStat.objects.filter(
            day__gte=since,
            action="view",
            channel__in=("portal", "entdecken"),
            listing_id__isnull=False,
            tenant_schema__in=base_qs.order_by().values("tenant_schema"),
        )
        .values("listing_id")
        .annotate(n=Sum("count"))
        .filter(n__gte=POPULAR_MIN_VIEWS)
        .order_by("-n", "listing_id")
        .values_list("listing_id", flat=True)[:24]
    )
    try:
        cache.set(key, ids, POPULAR_CACHE)
    except Exception:  # noqa: BLE001
        logger.warning("portal_popular: cache.set failed", exc_info=True)
    return ids


def quad_cards(base_qs, blocks, open_set, *, portal_pk, path: str, now=None) -> list[dict]:
    """Четыре карточки под баннером: Endet heute · Beliebt (или Jetzt geöffnet) · Neu ·
    Am Wochenende. Инвариант «карточка ⊆ ленты по ссылке»: показанное берётся из той же
    области, что открывает «Alle»; платное (featured) сюда не попадает (UWG §5a). Пустая
    карточка не рендерится. Запросы: 0 из блоков + ≤2 на «Beliebt»."""
    from .search import DATED_KINDS, date_window

    now = now or timezone.now()
    by_key = {b["key"]: b for b in blocks}
    used: set[int] = set()
    cards: list[dict] = []

    def add(key, title, items, url):
        # UWG §5a: блоки отсекают только показанные в «Anzeigen» featured (≤3, не все виды) —
        # оплаченное без пометки сюда не попадает ни из одного источника.
        picked = [
            i
            for i in items
            if i.pk not in used and not (i.featured_until and i.featured_until > now)
        ][:QUAD_ITEMS]
        if picked:
            used.update(i.pk for i in picked)
            cards.append({"key": key, "title": title, "items": picked, "more_url": url})

    # 1. Endet heute — из блока «angebote» (порядок «Endet bald»): что кончается до полуночи.
    end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    offers = by_key.get("angebote", {}).get("items", [])
    add(
        "endet",
        _("Endet heute"),
        [i for i in offers if i.ends_at and i.ends_at <= end_of_day],
        f"{path}?{urlencode({'kind': 'angebote', 'sort': 'endet'})}",
    )

    # 2. Am Wochenende — датированное из «Freizeit», пересекающее окно выходных. Выбирает ДО
    # «Jetzt geöffnet» (фидбэк 2026-11-08: события уходили туда, и карточка выходных пустела).
    # Окно пусто (воскресный вечер, выходные позади) — «Demnächst»: ближайшие события.
    start, end = date_window("wochenende", now=now)
    freizeit = by_key.get("freizeit", {}).get("items", [])
    weekend = [
        i
        for i in freizeit
        if i.listing_kind in DATED_KINDS
        and (i.starts_at is None or i.starts_at < end)
        and (i.ends_at is None or i.ends_at >= start)
    ]
    if weekend:
        add(
            "wochenende",
            _("Am Wochenende"),
            weekend,
            f"{path}?{urlencode({'kind': 'alle', 'kat': 'freizeit-erlebnisse', 'datum': 'wochenende'})}",
        )
    else:
        upcoming = sorted(
            {
                i.pk: i for b in blocks for i in b["items"] if i.listing_kind == L.KIND_EVENT
            }.values(),
            key=lambda i: (i.starts_at is None, i.starts_at or now),
        )
        add("demnaechst", _("Demnächst"), upcoming, f"{path}?kind={L.KIND_EVENT}")

    # 3. Neu — блок «neu».
    neu = by_key.get("neu")
    if neu:
        add("neu", _("Neu hinzugekommen"), neu["items"], neu["more_url"])

    # 4. Beliebt diese Woche — просмотры за 7 дней; иначе «Jetzt geöffnet» (магазины, а не
    # события: у события нет «открыто сейчас»).
    popular = []
    ids = _popular_ids(base_qs, portal_pk, now)
    if ids:
        rows = {
            i.pk: i
            for i in base_qs.filter(pk__in=ids)
            .exclude(featured_until__gt=now)
            .exclude(listing_kind=L.KIND_BUSINESS)
        }
        popular = [rows[pk] for pk in ids if pk in rows and pk not in used]
    if len(popular) >= POPULAR_MIN_ITEMS:
        add("beliebt", _("Beliebt diese Woche"), popular, f"{path}?kind=alle")
    elif open_set:
        pool = [
            i
            for b in blocks
            for i in b["items"]
            if i.tenant_schema in open_set and i.listing_kind not in (L.KIND_BUSINESS, L.KIND_EVENT)
        ]
        add(
            "offen",
            _("Jetzt geöffnet"),
            pool,
            f"{path}?{urlencode({'kind': 'alle', 'offen': '1'})}",
        )

    # Порядок показа — по макету K1 (выбор шёл в порядке «кому нужнее»).
    order = ("endet", "beliebt", "offen", "neu", "wochenende", "demnaechst")
    cards.sort(key=lambda c: order.index(c["key"]))
    return cards


# --- PH-11d2: «Das Beste aus jedem Bereich», «Geschäfte», «Top-Aktionen» (макет K1) ------

BEST_SECTIONS = 6
BEST_ROWS = 3
LOW_STOCK = 3  # «wenige übrig» — тот же порог, что честная плашка остатка (PH-9)
BUSY_LIMIT = 6
BUSY_MIN = 3  # меньше трёх бизнесов с предложениями — блока нет
TOP_LIMIT = 2
TOP_MIN_SAVES = 2  # порог честности: «meistgemerkt» — не по одному сохранению
TOP_DAYS = 7


def _dot(item, snapshot, end_of_day) -> str:
    """Статус строки: open · soon (endet heute / wenige übrig) · closed · "" (часов нет)."""
    row = snapshot.get(item.tenant_schema) or {}
    status = row.get("status") or {}
    if row.get("holiday") or (status and not status.get("open")):
        return "closed"
    if (item.ends_at and item.ends_at <= end_of_day) or (
        item.remaining is not None and item.remaining <= LOW_STOCK
    ):
        return "soon"
    return "open" if status.get("open") else ""


def best_by_section(
    base_qs, present, open_set, snapshot, *, path: str, exclude_pks=(), now=None
) -> list[dict]:
    """Топ-разделы пула по числу предложений и по 3 строки в каждом — ОДИН запрос (Window
    RowNumber по разделу). «Zuerst, was heute nutzbar ist»: открытые сейчас выше, затем
    срочное, затем новое. Строки ⊆ ленты раздела (?kind=alle&kat=<раздел>); платное не
    попадает (UWG §5a), бизнес-карточки не строки."""
    now = now or timezone.now()
    sections = present.get("sections", {})
    top = sorted(sections, key=lambda k: (-sections[k], k))[:BEST_SECTIONS]
    if not top:
        return []
    cats = {s: [c.key for c in cc.CATEGORIES if c.section == s] for s in top}
    section_of = Case(
        *[When(city_category__in=keys, then=Value(s)) for s, keys in cats.items() if keys],
        default=Value(""),
        output_field=CharField(),
    )
    open_first = Case(
        When(tenant_schema__in=sorted(open_set), then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    ends_today = Case(
        When(ends_at__lte=end_of_day, then=Value(0)), default=Value(1), output_field=IntegerField()
    )
    # «Zuerst, was heute nutzbar ist»: открытое сейчас → кончается сегодня → новое (а не
    # «любая дата выше» — событие через месяц не обгоняет открытую лавку; ревью 2026-11-08).
    order = [open_first, ends_today, "-created_at", "-pk"]
    rows = (
        base_qs.exclude(listing_kind=L.KIND_BUSINESS)
        .exclude(featured_until__gt=now)
        .exclude(pk__in=list(exclude_pks))
        .annotate(best_section=section_of)
        .exclude(best_section="")
        .annotate(best_rank=Window(RowNumber(), partition_by=[F("best_section")], order_by=order))
        .filter(best_rank__lte=BEST_ROWS)
        .order_by("best_section", "best_rank")
    )
    by_section: dict[str, list] = {}
    for item in rows:
        by_section.setdefault(item.best_section, []).append(item)
    out = []
    for key in top:
        items = by_section.get(key)
        if not items:
            continue
        sec = cc.section(key)
        for item in items:
            item.best_dot = _dot(item, snapshot, end_of_day)
        out.append(
            {
                "key": key,
                "label": str(sec.label) if sec else key,
                "count": sections[key],
                "image": next(
                    (i.image.get("url") for i in items if (i.image or {}).get("url")), ""
                ),
                "items": items,
                "url": scope_url(path, FeedScope(kind_key="alle", kat=key)),
            }
        )
    # Ряды по 3 на десктопе: 4 или 5 разделов дали бы одинокую карточку во втором ряду.
    if len(out) > 3:
        out = out[: len(out) // 3 * 3]
    return out


def busy_businesses(base_qs, *, path: str, now=None) -> dict | None:
    """«Geschäfte, die gerade viel anbieten» — бизнесы пула по числу предложений: ОДИН
    агрегат + ОДИН запрос фото бизнес-карточек. Меньше BUSY_MIN — None."""
    now = now or timezone.now()
    rows = list(
        base_qs.exclude(listing_kind=L.KIND_BUSINESS)
        .exclude(featured_until__gt=now)  # оплата не поднимает бизнес в «органическом» блоке
        .order_by()
        .values("tenant_schema")
        # группа — бизнес (схема); имя и slug — из его строк (у одного бизнеса они одни)
        .annotate(n=Count("id"), tenant_slug=Max("tenant_slug"), business_name=Max("business_name"))
        .order_by("-n", "business_name")[:BUSY_LIMIT]
    )
    if len(rows) < BUSY_MIN:
        return None
    photos = {
        schema: image
        for schema, image in base_qs.filter(
            listing_kind=L.KIND_BUSINESS, tenant_schema__in=[r["tenant_schema"] for r in rows]
        )
        .order_by()
        .values_list("tenant_schema", "image")
    }
    for r in rows:
        r["image"] = (photos.get(r["tenant_schema"]) or {}).get("url", "")
    return {"items": rows, "more_url": f"{path}?kind={L.KIND_BUSINESS}"}


def top_actions(base_qs, *, path: str, exclude_pks=(), now=None) -> list:
    """«Top-Aktionen dieser Woche» — самые сохраняемые акции за неделю (FavoriteListing),
    ОДИН запрос. Порог: ≥2 акции с ≥2 сохранениями — иначе блока нет. Платное — нет."""
    now = now or timezone.now()
    since = now - timedelta(days=TOP_DAYS)
    items = list(
        base_qs.filter(listing_kind=L.KIND_PROMOTION, favorited_by__created_at__gte=since)
        .exclude(featured_until__gt=now)
        .exclude(pk__in=list(exclude_pks))
        .annotate(saves=Count("favorited_by", filter=Q(favorited_by__created_at__gte=since)))
        .filter(saves__gte=TOP_MIN_SAVES)
        .order_by("-saves", "-pk")[:TOP_LIMIT]
    )
    return items if len(items) >= TOP_LIMIT else []
