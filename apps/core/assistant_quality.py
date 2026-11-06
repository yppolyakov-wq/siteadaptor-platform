"""AIS A-6b: отчёт качества помощника — только для команды `assistant_report` (оператор платформы
на сервере). План — docs/ais-a6-quality-plan-2026-11-06.md §4.

`summarize(schema, since)` — только КОДЫ и числа (агрегаты в базе): доли исходов по обработчику,
средний `dropped`, раунды уточнений, пакеты предложено/применено/откачено, счётчики
`assistant_stats`. `samples(schema, since, n)` — вопросы, которые помощник НЕ понял (те же коды,
что `misses`; без `kind=answer`): повторный `pii.scrub`, ≤ 120 символов, без автора. Вызывать
внутри `schema_context(schema)`.
"""

from __future__ import annotations

from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce

SAMPLE_MAX = 120
#: «не понял» — одно определение для `misses` и `samples`
MISS_CODES = ("unknown", "unclear", "check_failed")


def _turns(since):
    from apps.core.models import AssistantTurn

    return AssistantTurn.objects.filter(created_at__gte=since)


def _int(key: str):
    return Coalesce(Cast(KeyTextTransform(key, "entry"), IntegerField()), 0)


def has_turns(since) -> bool:
    return _turns(since).exists()


def summarize(schema: str, since, days: int = 30, counters: bool = True) -> dict:
    from apps.core import assistant_stats
    from apps.core.models import AssistantChange

    rows = (
        _turns(since)
        .annotate(r=KeyTextTransform("route", "entry"), c=KeyTextTransform("code", "entry"))
        .values("kind", "r", "c")
        .annotate(n=Count("id"))
        .order_by()
    )
    routes: dict[str, dict[str, int]] = {}
    kinds: dict[str, int] = {}
    misses = 0
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + row["n"]
        code = row["c"] or row["kind"]
        bucket = routes.setdefault(row["r"] or "?", {})
        bucket[code] = bucket.get(code, 0) + row["n"]
        misses += row["n"] if row["c"] in MISS_CODES else 0
    acts = _turns(since).filter(kind="actions")
    agg = acts.aggregate(n=Count("id"), dropped=Sum(_int("dropped")))
    changes = AssistantChange.objects.filter(job__in=acts.values("job")).aggregate(
        applied=Count("id"), undone=Count("id", filter=Q(undone_at__isnull=False))
    )
    rounds = _turns(since).aggregate(s=Sum(_int("clarify_rounds")))["s"] or 0
    proposed = agg["n"] or 0
    return {
        "schema": schema,
        "turns": sum(kinds.values()),
        "kinds": kinds,
        "routes": dict(sorted(routes.items())),
        "misses": misses,
        "avg_dropped": round((agg["dropped"] or 0) / proposed, 2) if proposed else 0,
        "clarify_rounds": rounds,
        "actions": {"proposed": proposed, **changes},
        "counters": {
            f"{r}:{c}": n for (r, c), n in sorted(assistant_stats.read(schema, days).items())
        }
        if counters
        else {},
    }


def samples(schema: str, since, n: int = 20) -> list[str]:
    from apps.core.pii import scrub

    out: list[str] = []
    qs = (
        _turns(since)
        .exclude(kind="answer")
        .annotate(c=KeyTextTransform("code", "entry"))
        .filter(c__in=MISS_CODES)
        .order_by("-created_at")
        .values_list("question", flat=True)
    )
    for question in qs[: max(n, 0) * 3]:
        text = " ".join(scrub(question or "").split())[:SAMPLE_MAX]
        if text and text not in out:
            out.append(text)
        if len(out) >= n:
            break
    return out
