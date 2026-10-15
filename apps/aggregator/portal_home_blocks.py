"""T-8.19: главная городского портала «Entdecke <город>» — вкладки, плитки разделов, блоки.

План — docs/t8-19-portal-home-plan-2026-10-15.md. Главный принцип: у каждого блока один
``FeedScope``. По нему строится и выборка блока, и ссылка «Alle →»; лента разбирает ту же
ссылку обратно в тот же ``FeedScope`` (``parse_scope``) — «Alle →» всегда ведёт на набор,
содержащий все карточки блока. Все выборки — поверх ``listings_for`` (``objects.public()``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Case, CharField, Count, F, IntegerField, Q, Value, When, Window
from django.db.models.functions import MD5, Cast, Concat, RowNumber
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core import city_categories as cc

from .models import AggregatorListing as L
from .models import apply_city_filters
from .tasks import NEW_PRODUCT_DAYS

NEW_DAYS = NEW_PRODUCT_DAYS  # «Neu» = свежий листинг или бейдж «neu» товара
BLOCK_LIMIT = 6  # полные ряды при сетке 2/3 колонки (урок DL-11)
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
        # T-8.20: фильтры единого поиска (search.FILTER_PARAMS)
        "stadtteil",
        "preis_von",
        "preis_bis",
        "datum",
        "verfuegbar",
        "offen",
        "sort",
        "umkreis",
    }
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
    ),
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
        portal.kind == portal.KIND_CITY
        and bool(portal.city)
        and not portal.business_type
        and facet is None
        and district is None
        and not any((request.GET.get(key) or "").strip() for key in FEED_PARAMS)
    )


def has_home(portal) -> bool:
    """Портал, у которого есть главная с вкладками (городской, без типа бизнеса)."""
    return portal.kind == portal.KIND_CITY and bool(portal.city) and not portal.business_type


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
    for kind, cat_key, n in rows:
        kinds[kind] = kinds.get(kind, 0) + n
        cat = cc.category(cat_key) if cat_key else None
        if cat:
            sections[cat.section] = sections.get(cat.section, 0) + n
    return {"kinds": kinds, "sections": sections, "total": sum(kinds.values())}


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


def section_tiles(present: dict, path: str) -> list[dict]:
    sections = present["sections"]
    return [
        {
            "key": s.key,
            "icon": s.icon,
            "label": s.label,
            "count": sections[s.key],
            "url": scope_url(path, FeedScope(kind_key="alle", kat=s.key)),
        }
        for s in cc.SECTIONS
        if sections.get(s.key)
    ]


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
        if not items:
            continue
        seen.update(item.pk for item in items)
        out.append(
            {
                "key": block.key,
                "title": str(block.title) % {"city": city},
                "items": items,
                "more_url": scope_url(path, block.scope),
            }
        )
    return out
