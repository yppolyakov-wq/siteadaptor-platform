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
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone, translation

from . import search_synonyms
from .models import AggregatorListing as L
from .models import apply_city_filters
from .search_index import fold, ts_config

_TOKEN = re.compile(r"[^\W_]+")
DATED_KINDS = (L.KIND_PROMOTION, L.KIND_EVENT)  # Р-О1: фильтр даты — только виды с датами


def _cfg(key: str):
    return settings.AGGREGATOR_SEARCH[key]


SEARCH_MAX = 100  # символов запроса
TOKEN_MAX = 30  # символов слова
TERMS_MAX = 40  # подзапросов tsquery на весь поиск (слова × синонимы × конфигурации)
SUBSTRING_MIN = 4  # слово от 4 букв ищется ещё и как часть слова («brot» → «Roggenbrot»)
_STOP_CACHE: dict[tuple[str, str], bool] = {}


def tokenize(q: str) -> list[str]:
    """Слова запроса: только буквы и цифры, нижний регистр, не больше max_tokens."""
    q = (q or "")[:SEARCH_MAX].replace("-", "")  # «E-Bike» → «ebike» (как в синонимах)
    return [t[:TOKEN_MAX] for t in _TOKEN.findall(q.lower())][: _cfg("max_tokens")]


def _drop_stopwords(tokens: list[str], lang: str) -> list[str]:
    """Убрать «in», «und», «der», «the»: стемминг их выбрасывает, а «simple»-часть
    требовала бы буквального слова — «Brot in Solingen» не находил бы ничего.
    Один запрос на новые слова, результат кэшируется в процессе (детерминирован)."""
    configs = list(dict.fromkeys(("german", "english", ts_config(lang))))
    key = ",".join(configs)
    unknown = [t for t in dict.fromkeys(tokens) if (key, t) not in _STOP_CACHE]
    if unknown:
        from django.db import connection

        checks = " OR ".join("numnode(to_tsquery(%s::regconfig, t)) = 0" for _c in configs)
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT t, ({checks}) FROM unnest(%s::text[]) AS t",  # noqa: S608
                [*configs, unknown],
            )
            rows = dict(cur.fetchall())
        if len(_STOP_CACHE) > 5000:
            _STOP_CACHE.clear()
        for t in unknown:
            _STOP_CACHE[(key, t)] = bool(rows.get(t))
    return [t for t in tokens if not _STOP_CACHE[(key, t)]]


def _words(q: str, lang: str) -> list[tuple[str, SearchQuery]]:
    """[(слово, tsquery слова)]: ИЛИ по синонимам × конфигурациям (german, simple, язык
    посетителя); у последнего слова — ещё и префикс. Бюджет — TERMS_MAX подзапросов."""
    tokens = _drop_stopwords(tokenize(q), lang)
    configs = list(dict.fromkeys(("german", "simple", ts_config(lang))))
    budget = TERMS_MAX
    out = []
    for i, token in enumerate(tokens):
        prefix = i == len(tokens) - 1 and len(token) >= _cfg("prefix_min_len")
        word = None
        for variant in dict.fromkeys([token, fold(token), *search_synonyms.expand(token)]):
            if word is not None and budget < len(configs):
                break  # само слово — всегда; синонимы — пока хватает бюджета
            raw = f"{variant}:*" if prefix else variant
            for cfg in configs:
                part = SearchQuery(raw, search_type="raw", config=cfg)
                word = part if word is None else word | part
                budget -= 1
        out.append((token, word))
    return out


def build_query(q: str, *, lang: str = "de") -> SearchQuery | None:
    """И между словами (для ранга)."""
    query = None
    for _token, word in _words(q, lang):
        query = word if query is None else query & word
    return query


def _match_words(qs, words):
    """Каждое слово — по индексу ИЛИ (от 4 букв) как часть слова (составные немецкие
    слова: «brot» находит «Roggenbrot»; LIKE идёт по trigram-индексу search_text)."""
    for token, word in words:
        cond = Q(search_vector=word)
        if len(token) >= SUBSTRING_MIN:
            cond |= Q(search_text__contains=fold(token))
        qs = qs.filter(cond)
    return qs


def match(qs, q: str, *, lang: str | None = None):
    """Сопоставление без ранга — для ``listings_for(q=)`` (то же правило, что execute)."""
    words = _words(q, lang or translation.get_language() or "de")
    if not words:
        return qs if not tokenize(q) else qs.none()
    return _match_words(qs, words)


def _trigram_pks(qs, q: str) -> list[int]:
    """Опечатки: похожее написание по trigram-индексу (оператор %>) — один проход,
    дальше выдача фильтруется по готовому списку. Слова короче 4 букв не участвуют
    (иначе «der» находил бы всё подряд)."""
    from django.db import connection

    folded = " ".join(fold(t) for t in tokenize(q) if len(t) >= SUBSTRING_MIN)
    if not folded:
        return []
    with connection.cursor() as cur:
        cur.execute(
            "SELECT set_config('pg_trgm.word_similarity_threshold', %s, false)",
            [str(_cfg("trigram_threshold"))],
        )
    return list(
        qs.filter(search_text__trigram_word_similar=folded)
        .annotate(similarity=TrigramWordSimilarity(folded, "search_text"))
        .order_by("-similarity", "-created_at", "-pk")
        .values_list("pk", flat=True)[: _cfg("max_results")]
    )


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
    q = (q or "").strip()[:SEARCH_MAX]
    qs = apply_filters(base_qs, filters)
    words = _words(q, lang) if q else []
    if not words:
        mode = "empty" if q else "none"
        if q:  # одни спецсимволы/стоп-слова — честно ничего, а не вся лента
            qs = qs.none()
        outcome = SearchOutcome(qs, mode, q, ranked=False, filters=filters)
    else:
        query = build_query(q, lang=lang)
        fts = _match_words(qs, words)
        if fts.exists():
            qs = fts.annotate(rank=SearchRank(F("search_vector"), query, weights=_weights()))
            mode = "fts"
            order = ["-rank", "-created_at", "-pk"]
        else:
            pks = _trigram_pks(qs, q) or [0]  # [0] — пустой список без пустого CASE
            position = Case(
                *[When(pk=pk, then=Value(i)) for i, pk in enumerate(pks)],
                default=Value(len(pks)),
                output_field=IntegerField(),
            )
            qs = qs.filter(pk__in=pks).annotate(similarity_pos=position)
            mode = "trigram"
            order = ["similarity_pos", "-created_at", "-pk"]
        qs = qs.order_by(*(["-created_at", "-pk"] if filters.sort == "neu" else order))
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
