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
from django.db.models import Case, ExpressionWrapper, F, IntegerField, Q, Value, When
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

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
FALLBACK_MAX_TERMS = (
    6  # слов в фолбэке опечаток (database-reviewer: стоимость ~ терминов × кандидатов)
)
FALLBACK_TIMEOUT_MS = 2000  # SET LOCAL statement_timeout на запрос фолбэка (security: страховка)
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
        # T-8.26 п.5b: части составного слова («winterjacke» → «winter», «jacke») и их
        # синонимы — ветки ИЛИ того же слова, ПОСЛЕ самого слова (ранг: точное первым).
        parts = search_synonyms.split_compound(token)
        variants = [token, fold(token), *search_synonyms.expand(token)]
        for part in parts:
            variants += [part, *search_synonyms.expand(part)]
        for variant in dict.fromkeys(variants):
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
        # T-8.26 п.5b: ГОЛОВА составного слова — ещё и как часть слова («Winterjacke» →
        # «Regenjacke»); модификатор только целым словом в FTS-ветке (подстрока «winter»
        # тянула бы «Winterreifen», «hand» — «Handy»).
        for part in search_synonyms.split_compound(token):
            if len(part) >= SUBSTRING_MIN and part in search_synonyms.HEADS:
                cond |= Q(search_text__contains=fold(part))
        qs = qs.filter(cond)
    return qs


def match(qs, q: str, *, lang: str | None = None):
    """Сопоставление без ранга — для ``listings_for(q=)`` (то же правило, что execute)."""
    words = _words(q, lang or translation.get_language() or "de")
    if not words:
        return qs if not tokenize(q) else qs.none()
    return _match_words(qs, words)


def _fallback_terms(q: str, lang: str, city: str) -> list[str]:
    """T-8.26 п.4 (Р-1): ЗНАЧИМЫЕ слова для фолбэка — без склейки дефиса («Solingen-Wald» →
    два слова), без стоп-слов, без топонимов города/районов (`districts.toponym_tokens`),
    только от SUBSTRING_MIN букв и не числа. Точный FTS-этап этого не касается."""
    from apps.core import districts

    raw = [t[:TOKEN_MAX] for t in _TOKEN.findall((q or "")[:SEARCH_MAX].lower())]
    raw = raw[: _cfg("max_tokens")]
    topo = districts.toponym_tokens(city)
    out = []
    for t in _drop_stopwords(raw, lang):
        ft = fold(t)
        if len(t) < SUBSTRING_MIN or t.isdigit() or t in topo or ft in topo:
            continue
        if ft not in out:
            out.append(ft)
    return out[:FALLBACK_MAX_TERMS]


def _significant(tokens: list[str]) -> set[str]:
    """Те же правила значимости, что у фолбэка (длина, не число), без топонимов —
    чтобы мягкий поиск запускался ТОЛЬКО когда состав изменил топоним/дефис, а не
    отброшенная цифра («Messer 2000») или короткое слово."""
    return {fold(t) for t in tokens if len(t) >= SUBSTRING_MIN and not t.isdigit()}


def _trigram_pks(qs, terms: list[str]) -> list[int]:
    """Опечатки по ЗНАЧИМЫМ словам (Р-3): один запрос — кандидаты по ИЛИ слов (`%>`,
    GIN BitmapOr), у каждого слова свой `word_similarity`, засчитываются слова выше
    порога; нужно `n` совпавших при n ≤ 2 и `n−1` при n ≥ 3 (одно лишнее слово допустимо).
    Раньше сравнивалась склеенная фраза целиком — длинное «solingen» вытягивало её выше
    порога без предмета поиска (аудит §7.3-1)."""
    from functools import reduce

    from django.db import connection, transaction
    from django.db.models import FloatField

    if not terms:
        return []
    n = len(terms)
    need = n if n <= 2 else n - 1
    thr = float(_cfg("trigram_threshold"))
    cond = Q()
    sims = {}
    for i, term in enumerate(terms):
        cond |= Q(search_text__trigram_word_similar=term)
        sims[f"sim{i}"] = TrigramWordSimilarity(term, "search_text")
    hits = reduce(
        lambda a, b: a + b,
        [
            Case(
                When(**{f"sim{i}__gte": thr}, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
            for i in range(n)
        ],
    )
    simsum = reduce(lambda a, b: a + b, [F(f"sim{i}") for i in range(n)])
    from django.db import OperationalError

    # Порог и таймаут — SET LOCAL внутри транзакции: иначе они остаются на соединении
    # (CONN_MAX_AGE) и достаются чужому коду (ревью database-reviewer). Таймаут —
    # страховка от дорогого фолбэка на мусорных словах: превысили → честный ноль.
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", [str(thr)]
                )
                cur.execute(
                    "SELECT set_config('statement_timeout', %s, true)", [str(FALLBACK_TIMEOUT_MS)]
                )
            return list(
                qs.filter(cond)
                .annotate(**sims)
                .annotate(
                    hits=ExpressionWrapper(hits, output_field=IntegerField()),
                    simsum=ExpressionWrapper(simsum, output_field=FloatField()),
                )
                .filter(hits__gte=need)
                .order_by("-hits", "-simsum", "-created_at", "-pk")
                .values_list("pk", flat=True)[: _cfg("max_results")]
            )
    except OperationalError:  # statement_timeout — фолбэк не нашёл за отведённое время
        return []


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
    sort: str = ""  # "" (релевантность / новые) | SORTS (T-8.7 Р-6)
    radius_km: int | None = None  # ?umkreis= (T-8.7 Р-5) — действует только при точке

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
            or self.radius_km is not None
        )


FILTER_PARAMS = (
    "stadtteil",
    "preis_von",
    "preis_bis",
    "datum",
    "verfuegbar",
    "offen",
    "sort",
    "umkreis",
)

# T-8.7 Р-6: сортировки обеих поверхностей. "" = релевантность при q, иначе новые.
SORTS = ("", "neu", "endet", "offen", "naehe")
# Без q эти сорта идут offset-курсором (paginate_ranked): keyset по nullable ends_at
# и по вычисляемому Case ломается.
OFFSET_SORTS = ("endet", "offen")
SORT_LABELS = {
    "neu": _("Neueste"),
    "endet": _("Endet bald"),
    "offen": _("Jetzt geöffnet"),
    "naehe": _("In der Nähe"),
}
# Единственный источник порядков: блоки главной (portal_home_blocks) берут отсюда же.
ORDERINGS = {
    "neu": ["-created_at", "-pk"],
    "endet": [  # срочное первым (О-4), затем сильная скидка
        F("ends_at").asc(nulls_last=True),
        F("discount_percent").desc(nulls_last=True),
        "-created_at",
        "-pk",
    ],
}


def order_for(sort: str, qs) -> list:
    """Порядок для явного сорта. `offen` — открытые сейчас первыми (закрытые остаются)."""
    if sort == "offen":
        from .views import _open_now_schemas

        schemas = set(qs.order_by().values_list("tenant_schema", flat=True).distinct())
        open_set = _open_now_schemas(schemas) if schemas else set()
        return [
            Case(
                When(tenant_schema__in=open_set, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "-created_at",
            "-pk",
        ]
    return list(ORDERINGS.get(sort) or ORDERINGS["neu"])


def parse_filters(request, *, city: str = "", point=None) -> SearchFilters:
    """``point`` — (lat, lng) посетителя: без неё сорт «Nähe» и радиус сбрасываются
    (обещание без исполнения — класс STU-9)."""
    from apps.core import city_categories as cc
    from apps.core import districts

    from . import geo
    from .views import _money

    get = request.GET
    sort = (get.get("sort") or "").strip()
    if sort not in SORTS:
        sort = ""
    if point is None and sort == "naehe":
        sort = ""
    radius_km = geo.parse_radius(get.get("umkreis")) if point is not None else None
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
        sort=sort,
        radius_km=radius_km,
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


def apply_filters(qs, f: SearchFilters, *, now=None, point=None):
    if f.radius_km and point is not None:  # T-8.7 Р-5: радиус — только при точке
        from . import geo

        qs = geo.within_radius(qs, point[0], point[1], f.radius_km)
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


def resolve_intent(
    q: str, explicit: SearchFilters, *, city: str, roh=(), path_district: bool = False
):
    """T-8.26 п.5a: текст → фильтры (ДО поиска). → (q_eff, filters_eff, chips, hints).

    `explicit` — фильтры из GET (сильнее вывода); `path_district` — район задан путём
    `/stadtteil/<slug>/` (вывод района блокируется); `roh` — `?roh=ort` и т.п."""
    from . import query_intent

    roh = set(roh or ())
    if path_district:  # район уже задан путём — слово района остаётся текстом
        roh.add(query_intent.ROH_ORT)
    intent = query_intent.parse(q, city=city or "", roh=frozenset(roh))
    q_eff, eff, chips = query_intent.apply(intent, explicit)
    return q_eff, eff, chips, intent.hints


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
        ("umkreis", str(f.radius_km) if f.radius_km else ""),
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
    ranked: bool  # True → paginate_ranked (ранг или OFFSET_SORTS); False → keyset по created_at
    filters: SearchFilters = field(default_factory=SearchFilters)
    lang: str = ""


def execute(
    base_qs,
    q: str,
    filters: SearchFilters | None = None,
    *,
    surface: str,
    lang: str = "",
    track: bool = True,
    city: str = "",
    portal_host: str = "",
    extra: dict | None = None,
    point=None,
    log_query: str | None = None,
) -> SearchOutcome:
    """Единственная точка поиска обеих поверхностей (портал, /entdecken/).

    ``city``/``portal_host`` — только для журнала T-8.21 (примитивы, не request).
    ``point`` — (lat, lng) для радиуса; сорт «naehe» порядок не задаёт (geo.nearest)."""
    filters = filters or SearchFilters()
    lang = lang or translation.get_language() or "de"
    q = (q or "").strip()[:SEARCH_MAX]
    qs = apply_filters(base_qs, filters, point=point)
    words = _words(q, lang) if q else []
    if not words:
        mode = "empty" if q else "none"
        if q:  # одни спецсимволы/стоп-слова — честно ничего, а не вся лента
            qs = qs.none()
        ranked = False
        if filters.sort in OFFSET_SORTS:  # T-8.7: «Endet bald»/«Jetzt geöffnet» — offset-курсор
            qs = qs.order_by(*order_for(filters.sort, qs))
            ranked = True
        outcome = SearchOutcome(qs, mode, q, ranked=ranked, filters=filters, lang=lang)
    else:
        query = build_query(q, lang=lang)
        fts = _match_words(qs, words)
        if fts.exists():
            qs = fts.annotate(rank=SearchRank(F("search_vector"), query, weights=_weights()))
            mode = "fts"
            order = ["-rank", "-created_at", "-pk"]
        else:
            # T-8.26 п.4: фолбэк по ЗНАЧИМЫМ словам. Если состав слов изменился (снят
            # топоним, разрезан дефис) — сначала мягкий точный поиск по ним (Р-2):
            # «Friseur in Solingen-Wald» → все Friseur; режим остаётся «неточно».
            terms = _fallback_terms(q, lang, city)
            exact = _significant(_drop_stopwords(tokenize(q), lang))
            soft = None
            if terms and set(terms) != exact:
                soft = _match_words(qs, _words(" ".join(terms), lang))
                if not soft.exists():
                    soft = None
            if soft is not None:
                qs = soft
                order = ["-created_at", "-pk"]
            else:
                pks = _trigram_pks(qs, terms) or [0]  # [0] — пустой список без пустого CASE
                position = Case(
                    *[When(pk=pk, then=Value(i)) for i, pk in enumerate(pks)],
                    default=Value(len(pks)),
                    output_field=IntegerField(),
                )
                qs = qs.filter(pk__in=pks).annotate(similarity_pos=position)
                order = ["similarity_pos", "-created_at", "-pk"]
            mode = "trigram"
        # T-8.7: явный сорт (кроме «Nähe») перекрывает ранг релевантности.
        if filters.sort in ("neu", "endet", "offen"):
            order = order_for(filters.sort, qs)
        qs = qs.order_by(*order)
        outcome = SearchOutcome(qs, mode, q, ranked=True, filters=filters, lang=lang)
    if track:
        logged = outcome
        if log_query is not None and log_query != q:  # T-8.26 п.5a: в журнал — сырой запрос
            from dataclasses import replace as _replace

            logged = _replace(outcome, query=log_query)
        record(logged, surface=surface, city=city, portal_host=portal_host, extra=extra)
    return outcome


def record(
    outcome: SearchOutcome,
    *,
    surface: str,
    city: str = "",
    portal_host: str = "",
    first_page: bool = True,
    extra: dict | None = None,
) -> None:
    """Шов T-8.21: журнал запросов и «ничего не найдено» (только для платформы).

    Вызывается ровно один раз на запрос с поиском или фильтром (поверхность, которая
    сужает выдачу после `execute(track=False)`, зовёт его сама). Параметра ``request``
    здесь нет намеренно — журнал не получает ничего персонального (замок в тестах).
    """
    if not (outcome.query or outcome.filters.active):
        return
    from . import search_log

    search_log.log(
        outcome,
        surface=surface,
        city=city,
        portal_host=portal_host,
        lang=outcome.lang,
        first_page=first_page,
        extra=extra,
    )
