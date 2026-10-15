"""T-8.20: единый поиск каталога города — портал и /entdecken/.

План — docs/t8-20-unified-search-plan-2026-10-15.md. Полнотекст Postgres по хранимому
вектору (``search_index``) с весами A–D из ``settings.AGGREGATOR_SEARCH``; если он ничего
не нашёл — поиск опечаток по похожему написанию (pg_trgm). Синонимы — ``search_synonyms``.
Платное размещение на ранг НЕ влияет (UWG §5a): полоса «Anzeigen» строится отдельно.

Безопасность: в tsquery попадают только буквы/цифры (``tokenize``), без операторов.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramWordSimilarity
from django.db.models import F, Q
from django.utils import timezone, translation

from . import search_synonyms
from .models import AggregatorListing as L
from .models import apply_city_filters
from .search_index import fold, ts_config

_TOKEN = re.compile(r"[^\W_]+")
DATED_KINDS = (L.KIND_PROMOTION, L.KIND_EVENT)  # Р-О1: фильтр даты — только виды с датами


def _cfg(key: str):
    return settings.AGGREGATOR_SEARCH[key]


def tokenize(q: str) -> list[str]:
    """Слова запроса: только буквы и цифры, нижний регистр, не больше max_tokens."""
    q = (q or "").replace("-", "")  # «E-Bike» → «ebike» (как в словаре синонимов)
    return _TOKEN.findall(q.lower())[: _cfg("max_tokens")]


def build_query(q: str, *, lang: str = "de") -> SearchQuery | None:
    """И между словами; ИЛИ по синонимам × конфигурациям (german, simple, язык посетителя)."""
    tokens = tokenize(q)
    if not tokens:
        return None
    configs = list(dict.fromkeys(("german", "simple", ts_config(lang))))
    query = None
    for i, token in enumerate(tokens):
        prefix = i == len(tokens) - 1 and len(token) >= _cfg("prefix_min_len")
        variants = dict.fromkeys([*search_synonyms.expand(token), fold(token)])
        word = None
        for variant in variants:
            raw = f"{variant}:*" if prefix else variant
            for cfg in configs:
                part = SearchQuery(raw, search_type="raw", config=cfg)
                word = part if word is None else word | part
        query = word if query is None else query & word
    return query


def match(qs, q: str, *, lang: str | None = None):
    """Только полнотекстовое сопоставление, без ранга — для ``listings_for(q=)``."""
    query = build_query(q, lang=lang or translation.get_language() or "de")
    if query is None:
        return qs
    return qs.filter(search_vector=query)


def _weights() -> list[float]:
    w = _cfg("weights")
    return [w["D"], w["C"], w["B"], w["A"]]  # порядок SearchRank: D, C, B, A


# --- фильтры ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchFilters:
    kats: tuple[str, ...] = ()  # ?kat=a&kat=b — ИЛИ
    tags: tuple[str, ...] = ()  # ?merkmal=a&merkmal=b — И (Р-О2)
    district: str = ""  # ?stadtteil=<slug>
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    date: str = ""  # heute | wochenende | YYYY-MM-DD (Р-О1: только события и акции)
    available: bool = False  # ?verfuegbar=1
    open_now: bool = False  # ?offen=1
    sort: str = ""  # "" (релевантность) | "neu"

    @property
    def active(self) -> bool:
        return bool(
            self.kats
            or self.tags
            or self.district
            or self.price_from is not None
            or self.price_to is not None
            or self.date
            or self.available
            or self.open_now
        )


FILTER_PARAMS = ("stadtteil", "preis_von", "preis_bis", "datum", "verfuegbar", "offen", "sort")


def parse_filters(request, *, city: str = "") -> SearchFilters:
    from apps.core import city_categories as cc
    from apps.core import districts

    from .views import _money

    get = request.GET
    kats = tuple(dict.fromkeys(k for k in get.getlist("kat") if cc.keys_for_filter(k)))
    tags = tuple(dict.fromkeys(t for t in get.getlist("merkmal") if cc.normalize_tags([t])))
    raw_district = (get.get("stadtteil") or "").strip()
    if city:
        district = districts.normalize(city, raw_district)
    else:
        known = {o["slug"] for o in districts.all_options()}
        district = raw_district if raw_district in known else ""
    date = (get.get("datum") or "").strip()
    if date not in ("heute", "wochenende") and _parse_day(date) is None:
        date = ""
    return SearchFilters(
        kats=kats,
        tags=tags,
        district=district,
        price_from=_money(get.get("preis_von")),
        price_to=_money(get.get("preis_bis")),
        date=date,
        available=get.get("verfuegbar") == "1",
        open_now=get.get("offen") == "1",
        sort="neu" if get.get("sort") == "neu" else "",
    )


def _parse_day(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def date_window(value: str, *, now=None) -> tuple[datetime, datetime] | None:
    """[start, end) окна даты в местном времени."""
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    if value == "heute":
        start = today
        days = 1
    elif value == "wochenende":
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:  # воскресенье — эти выходные ещё идут
            start = today - timedelta(days=1)
        days = 2
    else:
        start = _parse_day(value)
        if start is None:
            return None
        days = 1
    tz = timezone.get_current_timezone()
    begin = timezone.make_aware(datetime.combine(start, datetime.min.time()), tz)
    return begin, begin + timedelta(days=days)


def apply_filters(qs, f: SearchFilters, *, now=None):
    if f.kats:
        from apps.core import city_categories as cc

        keys = {key for kat in f.kats for key in cc.keys_for_filter(kat)}
        qs = qs.filter(city_category__in=keys)
    for tag in f.tags:
        qs = apply_city_filters(qs, None, tag)
    if f.district:
        qs = qs.filter(district=f.district)
    if f.price_from is not None:
        qs = qs.filter(new_price__gte=f.price_from)
    if f.price_to is not None:
        qs = qs.filter(new_price__lte=f.price_to)
    if f.date:
        window = date_window(f.date, now=now)
        if window:
            start, end = window
            qs = qs.filter(listing_kind__in=DATED_KINDS).filter(
                Q(starts_at__isnull=True) | Q(starts_at__lt=end),
                Q(ends_at__isnull=True) | Q(ends_at__gte=start),
            )
    if f.available:
        qs = qs.exclude(availability=L.AVAILABILITY_SOLD_OUT)
    if f.open_now:
        from .views import _open_now_schemas

        schemas = set(qs.order_by().values_list("tenant_schema", flat=True).distinct())
        qs = qs.filter(tenant_schema__in=_open_now_schemas(schemas))
    return qs


def carry(q: str, f: SearchFilters) -> list[tuple[str, str]]:
    """Параметры поиска и фильтров для «Weitere»/форм — тем же форматом, что parse_filters."""
    out: list[tuple[str, str]] = []
    if q:
        out.append(("q", q))
    out += [("kat", k) for k in f.kats]
    out += [("merkmal", t) for t in f.tags]
    for key, value in (
        ("stadtteil", f.district),
        ("preis_von", "" if f.price_from is None else str(f.price_from)),
        ("preis_bis", "" if f.price_to is None else str(f.price_to)),
        ("datum", f.date),
        ("verfuegbar", "1" if f.available else ""),
        ("offen", "1" if f.open_now else ""),
        ("sort", f.sort),
    ):
        if value:
            out.append((key, value))
    return out


# --- выполнение ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchOutcome:
    qs: object  # QuerySet: отфильтрованный и упорядоченный пул (featured — отдельно)
    mode: str  # none | fts | trigram | empty
    query: str
    ranked: bool  # True → paginate_ranked; False → прежний keyset по created_at
    filters: SearchFilters = field(default_factory=SearchFilters)


def execute(
    base_qs,
    q: str,
    filters: SearchFilters | None = None,
    *,
    surface: str,
    lang: str = "",
    track: bool = True,
) -> SearchOutcome:
    """Единственная точка поиска обеих поверхностей (портал, /entdecken/)."""
    filters = filters or SearchFilters()
    lang = lang or translation.get_language() or "de"
    q = (q or "").strip()
    qs = apply_filters(base_qs, filters)
    query = build_query(q, lang=lang) if q else None
    if query is None:
        mode = "empty" if q else "none"
        if q:  # одни спецсимволы — честно ничего, а не вся лента
            qs = qs.none()
        outcome = SearchOutcome(qs, mode, q, ranked=False, filters=filters)
    else:
        fts = qs.filter(search_vector=query)
        if fts.exists():
            qs = fts.annotate(rank=SearchRank(F("search_vector"), query, weights=_weights()))
            mode = "fts"
        else:
            folded = fold(" ".join(tokenize(q)))
            qs = qs.annotate(similarity=TrigramWordSimilarity(folded, "search_text")).filter(
                similarity__gte=_cfg("trigram_threshold")
            )
            mode = "trigram"
        if filters.sort == "neu":
            qs = qs.order_by("-created_at", "-pk")
        elif mode == "fts":
            qs = qs.order_by("-rank", "-created_at", "-pk")
        else:
            qs = qs.order_by("-similarity", "-created_at", "-pk")
        outcome = SearchOutcome(qs, mode, q, ranked=True, filters=filters)
    if track:
        record(outcome, surface=surface)
    return outcome


def record(outcome: SearchOutcome, *, surface: str) -> None:
    """Шов T-8.21: журнал запросов и «ничего не найдено» (только для платформы).

    Вызывается ровно один раз на запрос с поиском или фильтром (поверхность, которая
    сужает выдачу после `execute(record=False)`, зовёт его сама). Пока ничего не пишет.
    """
    if not (outcome.query or outcome.filters.active):
        return
    return None
