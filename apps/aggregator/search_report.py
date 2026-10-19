"""T-8.10d D-0: отчёт по журналу поиска каталога города (только чтение агрегатов).

План — docs/t8-10d-search-subscriptions-plan-2026-10-19.md §3. Отвечает на вопрос,
нужен ли ИИ-разбор фраз (D-2): сколько поисков многословные и при этом почти ничего не
находят. Персональных данных журнал не держит (T-8.21), отчёт добавляет ещё одну
страховку: в топы попадают только запросы, которые искали хотя бы дважды, — одиночные
чаще всего содержат имя или адрес.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

MIN_SEARCHES_TOP = 2  # одиночные запросы в топы не попадают
LOW_RESULTS = 3  # «малая выдача» — не больше трёх результатов
D2_SHARE = 0.10  # Р-9: доля многословных пустых/малых выдач
D2_MIN_SEARCHES = 500  # Р-9: минимум поисков за окно

REPORT_KEYS = {
    "days",
    "surface",
    "city",
    "searches",
    "zero_share",
    "trigram_share",
    "filters_only_share",
    "auto_share",
    "auto_keys",
    "multiword_share",
    "multiword_low_share",
    "by_surface",
    "by_lang",
    "top_zero",
    "top_multiword_low",
    "follow_kinds",
    "d2_recommended",
}


def _share(part: int, total: int) -> float:
    return (part / total) if total else 0.0


def _significant_words(query: str, lang: str) -> int:
    from .search import _drop_stopwords, tokenize

    tokens = tokenize(query)
    if len(tokens) < 2:
        return len(tokens)
    return len(_drop_stopwords(tokens, lang or "de"))


def _top(rows: list[dict], *, top: int, min_searches: int) -> list[dict]:
    picked = [r for r in rows if r["searches"] >= min_searches and r["query_norm"]]
    picked.sort(key=lambda r: (-r["searches"], r["query_norm"]))
    return [
        {"query": r["query_norm"], "searches": r["searches"], "lang": r["lang"]}
        for r in picked[:top]
    ]


def _follow_kinds() -> dict:
    from .models import FollowSubscription

    rows = FollowSubscription.objects.values("target_kind").annotate(n=Count("id")).order_by()
    try:
        return {r["target_kind"]: int(r["n"]) for r in rows}
    except Exception:  # noqa: BLE001 — счётчик подписок — справка, отчёт не роняет
        return {}


def build(
    *,
    days: int = 30,
    surface: str = "",
    city: str = "",
    top: int = 20,
    min_searches: int = MIN_SEARCHES_TOP,
) -> dict:
    """Сводка журнала за `days` дней. Ничего не пишет."""
    from .models import SearchQueryLog

    since = timezone.localdate() - timedelta(days=max(1, int(days)) - 1)
    qs = SearchQueryLog.objects.filter(day__gte=since)
    if surface:
        qs = qs.filter(surface=surface)
    if city:
        qs = qs.filter(city=city)

    # Строки одного запроса за разные дни сводим вместе: топы — по сумме поисков.
    grouped: dict[tuple, dict] = {}
    by_surface: Counter = Counter()
    by_lang: Counter = Counter()
    auto_keys: Counter = Counter()
    totals = Counter()
    for row in qs.values(
        "surface",
        "lang",
        "query_norm",
        "filters",
        "searches",
        "zero_results",
        "trigram_hits",
        "last_results",
    ):
        n = int(row["searches"] or 0)
        totals["searches"] += n
        totals["zero"] += int(row["zero_results"] or 0)
        totals["trigram"] += int(row["trigram_hits"] or 0)
        by_surface[row["surface"]] += n
        by_lang[row["lang"] or "-"] += n
        query = row["query_norm"] or ""
        if not query:
            totals["filters_only"] += n
        auto = (row["filters"] or {}).get("auto") if isinstance(row["filters"], dict) else ""
        if auto:
            totals["auto"] += n
            for key in str(auto).split(","):
                if key:
                    auto_keys[key] += n
        if query:
            words = _significant_words(query, row["lang"])
            low = int(row["last_results"] or 0) <= LOW_RESULTS
            if words >= 2:
                totals["multiword"] += n
                if low:
                    totals["multiword_low"] += n
            g = grouped.setdefault(
                (query, row["lang"] or ""),
                {
                    "query_norm": query,
                    "lang": row["lang"] or "",
                    "searches": 0,
                    "zero": 0,
                    "multiword_low": 0,
                },
            )
            g["searches"] += n
            g["zero"] += int(row["zero_results"] or 0)
            if words >= 2 and low:
                g["multiword_low"] += n

    total = totals["searches"]
    groups = list(grouped.values())
    top_zero = _top([g for g in groups if g["zero"]], top=top, min_searches=min_searches)
    top_low = _top([g for g in groups if g["multiword_low"]], top=top, min_searches=min_searches)
    multiword_low_share = _share(totals["multiword_low"], total)
    return {
        "days": int(days),
        "surface": surface,
        "city": city,
        "searches": total,
        "zero_share": _share(totals["zero"], total),
        "trigram_share": _share(totals["trigram"], total),
        "filters_only_share": _share(totals["filters_only"], total),
        "auto_share": _share(totals["auto"], total),
        "auto_keys": dict(auto_keys),
        "multiword_share": _share(totals["multiword"], total),
        "multiword_low_share": multiword_low_share,
        "by_surface": dict(by_surface),
        "by_lang": dict(by_lang),
        "top_zero": top_zero,
        "top_multiword_low": top_low,
        "follow_kinds": _follow_kinds(),
        "d2_recommended": total >= D2_MIN_SEARCHES and multiword_low_share >= D2_SHARE,
    }
