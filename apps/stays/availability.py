"""Доступность юнитов по датам (Track E / E1).

``range_available`` — пер-ночная проверка занятости (активные брони + блоки <
quantity). Источник истины при создании — services.book_stay (вызывает эту
функцию под блокировкой строки юнита); здесь же — UI-подсказка для витрины/
кабинета (E2/E3). ``free_units`` — подбор свободных юнитов на диапазон.
"""

import calendar
from datetime import date, timedelta

from apps.core import status_registry

from .models import StayBooking, StayUnit, UnitBlock


def nights_between(arrival, departure) -> list:
    """Список дат-ночей ``[arrival, departure)`` (день выезда не входит)."""
    out, day = [], arrival
    while day < departure:
        out.append(day)
        day += timedelta(days=1)
    return out


def range_available(unit, arrival, departure, *, exclude_pk=None, needed=1) -> bool:
    """Есть ли на КАЖДУЮ ночь ``[arrival, departure)`` место для ``needed`` номеров.

    Считает занятость по ночам в памяти (как booking.free_slots): активные брони
    юнита (каждая занимает свои ``rooms`` номеров, G5), пересекающие диапазон, +
    блоки. Под блокировкой строки юнита (её ставит services.book_stay) это и есть
    атомарная anti-overbook-гарантия. ``needed`` — сколько номеров нужно (мульти-
    бронь): свободно, если quantity − занятость ≥ needed на каждую ночь.
    """
    nights = nights_between(arrival, departure)
    if not nights:
        return False
    last_night = nights[-1]

    stays = StayBooking.objects.filter(
        unit=unit,
        status__in=status_registry.active_statuses_for("stay"),
        arrival__lt=departure,
        departure__gt=arrival,
    )
    if exclude_pk is not None:
        stays = stays.exclude(pk=exclude_pk)
    stays = list(stays.values_list("arrival", "departure", "rooms"))

    blocks = list(
        UnitBlock.objects.filter(
            unit=unit, start_date__lte=last_night, end_date__gte=arrival
        ).values_list("start_date", "end_date")
    )

    for night in nights:
        occupied = sum(rooms for s_arr, s_dep, rooms in stays if s_arr <= night < s_dep)
        occupied += sum(1 for b_start, b_end in blocks if b_start <= night <= b_end)
        if occupied + needed > unit.quantity:
            return False
    return True


def free_units(arrival, departure, *, guests=1) -> list:
    """Активные юниты, свободные на весь диапазон и вмещающие ``guests`` гостей."""
    nights = (departure - arrival).days
    return [
        unit
        for unit in StayUnit.objects.filter(is_active=True, max_guests__gte=guests)
        if nights >= unit.min_nights and range_available(unit, arrival, departure)
    ]


def booking_bars(units, start_day, num_days, bookings, blocks):
    """Батч C (Belegungsplan, концепт 2026-07-27): render-ready плашки броней и
    блокировок по юнитам для tape-chart-сетки кабинета.

    Возвращает {unit_id: [lane, …]}, lane = список элементов слева направо:
      {"gap": N}                      — N пустых ячеек;
      {"seg": {...}, "span": N, ...}  — плашка на N ячеек:
         kind booking|block · obj · clip_left/clip_right (диапазон выходит за
         окно — на плашке рисуем ‹/›).

    Брони одного юнита могут пересекаться (quantity>1) → раскладываем жадно по
    «дорожкам» (первая, чей последний сегмент кончился к началу нового). Ночь
    выезда свободна (departure эксклюзивен); у UnitBlock end_date ВКЛЮЧИТЕЛЕН —
    конвертируем в эксклюзивный конец здесь, чтобы шаблон жил в одной системе.
    """
    window_end = start_day + timedelta(days=num_days)
    segs_by_unit = {u.id: [] for u in units}

    def _add(unit_id, kind, obj, seg_start, seg_end_excl):
        if unit_id not in segs_by_unit:
            return
        clip_start = max(seg_start, start_day)
        clip_end = min(seg_end_excl, window_end)
        if clip_end <= clip_start:
            return
        segs_by_unit[unit_id].append(
            {
                "kind": kind,
                "obj": obj,
                "offset": (clip_start - start_day).days,
                "span": (clip_end - clip_start).days,
                "clip_left": seg_start < start_day,
                "clip_right": seg_end_excl > window_end,
            }
        )

    for b in bookings:
        _add(b.unit_id, "booking", b, b.arrival, b.departure)
    for blk in blocks:
        _add(blk.unit_id, "block", blk, blk.start_date, blk.end_date + timedelta(days=1))

    bars = {}
    for unit_id, segs in segs_by_unit.items():
        bars[unit_id] = _pack_lanes(segs, num_days)
    return bars


def _pack_lanes(segs, num_days):
    """Жадная укладка сегментов по «дорожкам» + заполнение gap'ов (общая часть
    booking_bars и room_lane_rows)."""
    segs = sorted(segs, key=lambda s: (s["offset"], -s["span"]))
    lanes = []  # [(next_free_offset, [seg, …]), …]
    for seg in segs:
        for lane in lanes:
            if lane[0] <= seg["offset"]:
                lane[1].append(seg)
                lane[0] = seg["offset"] + seg["span"]
                break
        else:
            lanes.append([seg["offset"] + seg["span"], [seg]])
    rows = []
    for _end, lane_segs in lanes:
        cells, cursor = [], 0
        for seg in lane_segs:
            if seg["offset"] > cursor:
                cells.append({"gap": seg["offset"] - cursor})
            cells.append(seg)
            cursor = seg["offset"] + seg["span"]
        if cursor < num_days:
            cells.append({"gap": num_days - cursor})
        rows.append(cells)
    return rows


def _clipped_seg(kind, obj, seg_start, seg_end_excl, start_day, window_end):
    """Сегмент, обрезанный окном (None — целиком вне окна)."""
    clip_start = max(seg_start, start_day)
    clip_end = min(seg_end_excl, window_end)
    if clip_end <= clip_start:
        return None
    return {
        "kind": kind,
        "obj": obj,
        "offset": (clip_start - start_day).days,
        "span": (clip_end - clip_start).days,
        "clip_left": seg_start < start_day,
        "clip_right": seg_end_excl > window_end,
    }


def room_lane_rows(unit, rooms, start_day, num_days, bookings, blocks):
    """PMS-R3: render-ready строки дорожек юнита С КОМНАТАМИ — по строке на
    каждую комнату (назначенные брони; пустая комната = пустая строка) +
    безымянные дорожки «ohne Zimmer» (неназначенные брони + блокировки юнита).

    Возвращает [{"label": "101"|"", "room_id": pk|None, "cells": [...]}] —
    ячейки в той же системе, что booking_bars (gap/seg)."""
    window_end = start_day + timedelta(days=num_days)
    room_ids = {r.id for r in rooms}
    out = []
    for room in rooms:
        segs = [
            s
            for b in bookings
            if b.unit_id == unit.id and b.room_id == room.id
            if (s := _clipped_seg("booking", b, b.arrival, b.departure, start_day, window_end))
        ]
        packed = _pack_lanes(segs, num_days) or [[{"gap": num_days}]]
        for cells in packed:
            out.append(
                {
                    "label": room.number,
                    "room_id": room.id,
                    "hk": room.housekeeping,  # PMS-R4: 🧹-бейдж на строке
                    "cells": cells,
                }
            )
    free_segs = [
        s
        for b in bookings
        if b.unit_id == unit.id and b.room_id not in room_ids
        if (s := _clipped_seg("booking", b, b.arrival, b.departure, start_day, window_end))
    ]
    free_segs += [
        s
        for blk in blocks
        if blk.unit_id == unit.id
        if (
            s := _clipped_seg(
                "block",
                blk,
                blk.start_date,
                blk.end_date + timedelta(days=1),
                start_day,
                window_end,
            )
        )
    ]
    for cells in _pack_lanes(free_segs, num_days):
        out.append({"label": "", "room_id": None, "cells": cells})
    return out


def next_free_range(nights, *, guests=1, from_day=None, max_days=60):
    """R3 «Nächste freie Nacht»: ближайший диапазон из ``nights`` ночей (начиная с
    ``from_day``, вкл.), где есть свободный юнит на ``guests`` гостей. Возвращает
    ``(arrival, departure)`` или ``None`` (нет в горизонте). Перехват уходящего
    гостя: искомые даты заняты → предлагаем ближайшие свободные."""
    from django.utils import timezone

    nights = max(1, int(nights or 1))
    start = from_day or timezone.localdate()
    for i in range(max_days + 1):
        arrival = start + timedelta(days=i)
        departure = arrival + timedelta(days=nights)
        if free_units(arrival, departure, guests=guests):
            return (arrival, departure)
    return None


def occupancy_grid(units, start_day, num_days):
    """Календарь загрузки для кабинета (E2): ``(days, rows)``.

    ``days`` — список дат окна; ``rows`` — список ``(unit, cells)``, где cell =
    ``{day, free, blocked}`` (free = quantity − занятость ночи, blocked — есть
    блокировка). Один запрос броней + блоков на юнит, занятость считаем в памяти.
    """
    end_day = start_day + timedelta(days=num_days)
    days = [start_day + timedelta(days=i) for i in range(num_days)]
    rows = []
    for unit in units:
        stays = list(
            StayBooking.objects.filter(
                unit=unit,
                status__in=status_registry.active_statuses_for("stay"),
                arrival__lt=end_day,
                departure__gt=start_day,
            ).values_list("arrival", "departure", "rooms")
        )
        blocks = list(
            UnitBlock.objects.filter(
                unit=unit, start_date__lt=end_day, end_date__gte=start_day
            ).values_list("start_date", "end_date")
        )
        cells = []
        for day in days:
            occupied = sum(rooms for s_arr, s_dep, rooms in stays if s_arr <= day < s_dep)
            blocked = any(b_start <= day <= b_end for b_start, b_end in blocks)
            occupied += sum(1 for b_start, b_end in blocks if b_start <= day <= b_end)
            cells.append({"day": day, "free": max(0, unit.quantity - occupied), "blocked": blocked})
        rows.append((unit, cells))
    return days, rows


def month_availability(unit, year, month, *, today=None) -> list[dict]:
    """Доступность номера на КАЛЕНДАРНЫЙ месяц для витрины (визуальный календарь, C1).

    Список по дням месяца: ``{date, in_past, free, is_free}``. ``free`` = quantity −
    занятость ночи (активные брони × rooms + блоки), как в ``occupancy_grid`` (один
    проход по броням/блокам — переиспользуем его). ``is_free`` — свободно И не в
    прошлом (день нельзя выбрать как заезд, если он прошёл). ``today`` — «сегодня»
    (по умолчанию ``timezone.localdate()``; считаем через локаль, как RV3).
    """
    from django.utils import timezone

    if today is None:
        today = timezone.localdate()
    first = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    _days, rows = occupancy_grid([unit], first, days_in_month)
    _u, cells = rows[0]
    out = []
    for cell in cells:
        in_past = cell["day"] < today
        out.append(
            {
                "date": cell["day"],
                "in_past": in_past,
                "free": cell["free"],
                "is_free": cell["free"] > 0 and not in_past,
            }
        )
    return out
