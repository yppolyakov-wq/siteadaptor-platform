"""Короткие свободные промежутки между занятыми ночами (Lücken).

Один источник для автопредложения Lücken-Deal в кабинете номеров и для подсказок
«Was heute starten?» (T-8.10c): дыра — это подряд свободные ночи, с обеих сторон
ограниченные занятыми, длиной не больше `max_nights`."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from . import availability


def short_gaps(units, *, max_nights=3, horizon=60, first_only=False):
    """[(unit, первая свободная ночь, число ночей)] в окне [завтра, завтра + horizon)."""
    today = timezone.localdate()
    start, end = today + timedelta(days=1), today + timedelta(days=1 + horizon)
    found = []
    for unit in units:
        occ = availability.occupancy_by_day(unit, start, end)
        run = 0
        bounded_left = False
        day = start
        while day < end:
            if occ.get(day, 0) < 100:
                run += 1
            else:
                if bounded_left and 0 < run <= max_nights:
                    found.append((unit, day - timedelta(days=run), run))
                    if first_only:
                        return found
                bounded_left = True
                run = 0
            day += timedelta(days=1)
    return found
