"""AIS A-6b: отчёт качества помощника — только для команды `assistant_report` (суперпользователь
платформы на сервере). План — docs/ais-a6-quality-plan-2026-11-06.md §4.

`summarize(schema, since)` — только КОДЫ и числа: доли исходов по обработчику, средний `dropped`,
раунды уточнений, пакеты предложено/применено/откачено, отказы до истории (`assistant_stats`).
`samples(schema, since, n)` — вопросы, которые помощник НЕ понял (без `kind=answer`): повторный
`pii.scrub`, ≤ 120 символов, без автора. Вызывать внутри `schema_context(schema)`.
"""

from __future__ import annotations

from collections import Counter

SAMPLE_MAX = 120
#: исходы «не понял» — источник samples
_MISS_CODES = ("unknown", "unclear", "check_failed")


def _turns(since):
    from apps.core.models import AssistantTurn

    return AssistantTurn.objects.filter(created_at__gte=since)


def summarize(schema: str, since, days: int = 30) -> dict:
    from apps.core import assistant_stats
    from apps.core.models import AssistantChange

    routes: dict[str, Counter] = {}
    kinds: Counter = Counter()
    dropped = rounds = actions = 0
    jobs = []
    for kind, entry, job in _turns(since).values_list("kind", "entry", "job").iterator():
        entry = entry or {}
        kinds[kind] += 1
        route = str(entry.get("route") or "?")
        routes.setdefault(route, Counter())[str(entry.get("code") or kind)] += 1
        dropped += int(entry.get("dropped") or 0)
        rounds += int(entry.get("clarify_rounds") or 0)
        if kind == "actions":
            actions += 1
            jobs.append(job)
    changes = AssistantChange.objects.filter(job__in=jobs)
    applied = changes.count()
    undone = changes.filter(undone_at__isnull=False).count()
    total = sum(kinds.values())
    return {
        "schema": schema,
        "turns": total,
        "kinds": dict(kinds),
        "routes": {r: dict(c) for r, c in sorted(routes.items())},
        "misses": sum(c[m] for c in routes.values() for m in _MISS_CODES),
        "avg_dropped": round(dropped / actions, 2) if actions else 0,
        "clarify_rounds": rounds,
        "actions": {"proposed": actions, "applied": applied, "undone": undone},
        "counters": {
            f"{r}:{c}": n for (r, c), n in sorted(assistant_stats.read(schema, days).items())
        },
    }


def samples(schema: str, since, n: int = 20) -> list[str]:
    from apps.core.pii import scrub

    out = []
    qs = _turns(since).exclude(kind="answer").order_by("-created_at")
    for question, entry in qs.values_list("question", "entry")[: max(n, 0) * 5]:
        code = (entry or {}).get("code") or ""
        if code not in _MISS_CODES and (entry or {}).get("outcome") != "fallback":
            continue
        text = " ".join(scrub(question or "").split())[:SAMPLE_MAX]
        if text and text not in out:
            out.append(text)
        if len(out) >= n:
            break
    return out
