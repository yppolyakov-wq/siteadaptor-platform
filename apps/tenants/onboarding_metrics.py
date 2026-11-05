"""AIS-0: замер «время до живого сайта» по меткам мастера — только чтение.

План docs/ais-0-onboarding-metric-plan-2026-11-05.md. Старт — `Tenant.created_at`
(тенант создаётся после подтверждения почты, AB5.1); финиш — метка `completed` мастера.
В замер идут только тенанты, прошедшие мастер САМИ (`source == "wizard"`) или не
прошедшие его вовсе; демо, внутренние, быстрый старт и импорт исключаются.

Метки появились с AIS-0: у старых тенантов их нет — они в отчёт не попадают («нет
данных»), а не считаются «быстрыми» или «медленными».
"""

from __future__ import annotations

import statistics
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.tenants import onboarding

#: Окно «дошёл до публикации за сутки» (порог AIS-0: ≥ 70 %).
DAY_MINUTES = 24 * 60


def _at(value: str) -> datetime | None:
    return parse_datetime(value) if isinstance(value, str) else None


def _minutes(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds() / 60
    return delta if delta >= 0 else None


def tenant_row(tenant) -> dict | None:
    """Строка замера одного тенанта или None, если он в замер не входит."""
    if tenant.is_demo or tenant.is_internal or tenant.schema_name == "public":
        return None
    state = onboarding.get_state(tenant)
    source = state.get("source")
    if source and source != "wizard":
        return None
    times = state.get("times") or {}
    if "start" not in times:
        return None  # мастер не открывали после AIS-0 — данных нет
    created = tenant.created_at
    completed_at = _at(times.get("completed"))
    if state["completed"] and completed_at is None:
        return None  # завершён до AIS-0 — когда именно, неизвестно
    # Время на шаге = от предыдущей метки до метки шага (порядок — по времени).
    marks = sorted(
        ((key, _at(value)) for key, value in times.items() if key != "completed"),
        key=lambda pair: pair[1],
    )
    dwell = {}
    previous = _at(times["start"])
    for key, at in marks:
        if key == "start":
            continue
        minutes = _minutes(previous, at)
        if minutes is not None:
            dwell[key] = minutes
        previous = at
    return {
        "schema": tenant.schema_name,
        "business_type": tenant.business_type or "",
        "completed": bool(state["completed"] and completed_at),
        "minutes_to_complete": _minutes(created, completed_at),
        "minutes_to_start": _minutes(created, _at(times["start"])),
        "age_minutes": _minutes(created, timezone.now()),
        "skipped": list(state["skipped"]),
        "dwell": dwell,
    }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def summarize(rows: list[dict]) -> dict:
    """Сводка: медиана/p75 времени до завершения, доля за сутки, узкие шаги."""
    done = [r["minutes_to_complete"] for r in rows if r["minutes_to_complete"] is not None]
    # Доля «за сутки» — только среди тех, у кого сутки уже прошли: свежие ещё не успели.
    aged = [r for r in rows if (r.get("age_minutes") or 0) >= DAY_MINUTES]
    within_day = [
        r
        for r in aged
        if r["minutes_to_complete"] is not None and r["minutes_to_complete"] <= DAY_MINUTES
    ]
    steps: dict[str, dict] = {}
    for row in rows:
        for key, minutes in row["dwell"].items():
            steps.setdefault(key, {"minutes": [], "skipped": 0, "seen": 0})["minutes"].append(
                minutes
            )
        for key in row["skipped"]:
            steps.setdefault(key, {"minutes": [], "skipped": 0, "seen": 0})["skipped"] += 1
    for data in steps.values():
        data["seen"] = len(data["minutes"])
        data["median"] = statistics.median(data["minutes"]) if data["minutes"] else None
        del data["minutes"]
    return {
        "tenants": len(rows),
        "completed": len(done),
        "median_minutes": statistics.median(done) if done else None,
        "p75_minutes": _percentile(done, 75),
        "share_within_day": (len(within_day) / len(aged)) if aged else None,
        "steps": steps,
    }
