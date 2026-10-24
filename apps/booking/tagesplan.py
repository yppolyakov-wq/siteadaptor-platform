"""KA-12 E4.2b: раскладка Tagesplan «ресурс × время» (чистые функции, без вьюх).

Колонка = активный ресурс (мастер/стол), ряд = шаг расписания дня. Блок записи
ставится в ряд начала и охватывает ряды до конца; хвост буфера (`occupied_until`)
рисуется отдельной полосой. Границы дня — рабочие окна ресурсов, расширенные до
записей вне часов (запись не должна пропасть из сетки), иначе 08–20.
"""

from dataclasses import dataclass, field
from datetime import time

from django.utils import timezone

MIN_STEP, MAX_STEP, DEFAULT_STEP = 15, 60, 30
MAX_LANES = 4


@dataclass
class Block:
    booking: object
    row: int  # 1 = первый ряд времени (шапку шаблон учитывает сам)
    span: int
    buffer_span: int
    lane: int
    movable: bool


@dataclass
class Column:
    resource: object
    closed: bool
    off_rows: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    lanes: int = 1


@dataclass
class Grid:
    rows: list  # [(номер ряда, «HH:MM», полный час?)]
    step: int
    columns: list
    day: object


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _local_minutes(dt, day) -> int:
    local = timezone.localtime(dt)
    if local.date() < day:
        return 0
    if local.date() > day:
        return 24 * 60
    return local.hour * 60 + local.minute


def build(resources, day, bookings, *, active_statuses=(), tenant=None) -> Grid:
    from . import availability

    resources = list(resources)
    windows = {r.pk: availability.day_windows(r, day, tenant) for r in resources}
    steps = [w[2] for ws in windows.values() for w in ws if w[2]]
    step = max(MIN_STEP, min(MAX_STEP, min(steps))) if steps else DEFAULT_STEP
    starts = [_minutes(w[0]) for ws in windows.values() for w in ws]
    ends = [_minutes(w[1]) for ws in windows.values() for w in ws]
    bookings = [b for b in bookings if any(b.resource_id == r.pk for r in resources)]
    for b in bookings:
        starts.append(_local_minutes(b.start, day))
        ends.append(_local_minutes(b.occupied_until or b.end, day))
    first = min(starts) if starts else 8 * 60
    last = max(ends) if ends else 20 * 60
    first = (first // step) * step
    last = max(first + step, -(-last // step) * step)
    n_rows = (last - first) // step
    rows = []
    for i in range(n_rows):
        m = first + i * step
        rows.append((i + 1, f"{m // 60:02d}:{m % 60:02d}", m % 60 == 0))

    def row_of(minute):
        return max(1, min(n_rows, (minute - first) // step + 1))

    columns = []
    for r in resources:
        col = Column(resource=r, closed=availability.is_closed(r, day))
        ws = windows[r.pk]
        for idx, _label, _full in rows:
            m = first + (idx - 1) * step
            if not any(_minutes(a) <= m and m + step <= _minutes(z) for a, z, _s in ws):
                col.off_rows.append(idx)
        lane_ends = []  # конец (минуты) последнего блока в каждой дорожке
        own = sorted((b for b in bookings if b.resource_id == r.pk), key=lambda b: b.start)
        for b in own:
            s = _local_minutes(b.start, day)
            e = max(s + 1, _local_minutes(b.end, day))
            busy = _local_minutes(b.occupied_until, day) if b.occupied_until else e
            row = row_of(s)
            span = max(1, row_of(e - 1) - row + 1)
            buffer_span = max(0, -(-(busy - e) // step)) if busy > e else 0
            lane = next((i for i, end in enumerate(lane_ends) if end <= s), None)
            if lane is None:
                lane = len(lane_ends)
                lane_ends.append(busy)
            else:
                lane_ends[lane] = busy
            col.blocks.append(
                Block(
                    booking=b,
                    row=row,
                    span=span,
                    buffer_span=buffer_span,
                    lane=min(lane, MAX_LANES - 1),
                    movable=b.status in active_statuses,
                )
            )
        col.lanes = max(1, min(MAX_LANES, len(lane_ends)))
        columns.append(col)
    return Grid(rows=rows, step=step, columns=columns, day=day)
