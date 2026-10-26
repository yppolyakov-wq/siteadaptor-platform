"""KA-12 GA-6: слой чтения экрана «Tischplan» — плитки столов по зонам на момент времени.

Записи здесь нет: walk-in и «Tisch zuweisen» идут штатными путями (`create_manual`,
`services.move`). Занятость считается так же, как в `occupancy.scope_ids` (стол ∪ его
части ∪ комбинации с ним или с его частью), но В ПАМЯТИ по предзагруженным `parts` —
экран рисует все столы сразу, N запросов области здесь были бы N+1.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

SOON_MINUTES = 30  # «reserviert ab …» — бронь области начнётся в ближайшие полчаса


@dataclass
class Tile:
    table: object
    state: str = "free"  # free | soon | busy | full (пул без мест)
    current: object = None  # бронь, которая занимает стол сейчас
    via: object = None  # стол/комбинация, через которую занят (не сам стол)
    next_booking: object = None  # ближайшая будущая бронь области
    free_until: object = None
    seats_taken: int = 0  # пул: занято мест сейчас
    more_now: int = 0  # пул: ещё броней сейчас кроме показанной
    bookings: list = field(default_factory=list)  # свои брони дня (для «zuweisen»)


def _until(b):
    return b.occupied_until or b.end


def _scopes(tables, links=None) -> dict:
    """pk стола → pk столов, чьи брони его занимают (та же семантика, что scope_ids).

    `links` — пары (combo_pk, part_pk) ВСЕХ комбинаций, включая выключенные: выключенная
    комбинация с бронью по-прежнему держит свои столы (scope_ids тоже не фильтрует)."""
    if links is None:
        links = [(t.pk, p.pk) for t in tables for p in t.parts.all()]
    parts: dict = {}
    combos_of: dict = {}
    for combo, part in links:
        parts.setdefault(combo, set()).add(part)
        combos_of.setdefault(part, set()).add(combo)
    out = {}
    for t in tables:
        own = parts.get(t.pk, set())
        scope = {t.pk} | own | combos_of.get(t.pk, set())
        for p in own:  # комбинации, делящие со мной стол-часть
            scope |= combos_of.get(p, set())
        out[t.pk] = scope
    return out


def scope_union(tables, links) -> set:
    """pk всех ресурсов, чьи брони нужны экрану (столы + их комбинации/части)."""
    return set().union(*_scopes(tables, links).values()) if tables else set()


def build(tables, bookings, at, links=None) -> list:
    """Зоны `[(zone, [Tile…])]` в порядке столов. `bookings` — действующие брони дня
    на этих столах (вызывающий фильтрует статусы)."""
    tables = list(tables)
    by_pk = {t.pk: t for t in tables}
    by_resource: dict = {}
    for b in sorted(bookings, key=lambda x: x.start):
        by_resource.setdefault(b.resource_id, []).append(b)
    scopes = _scopes(tables, links)
    soon_edge = at + timedelta(minutes=SOON_MINUTES)
    zones: dict = {}
    for t in tables:
        tile = Tile(table=t, bookings=by_resource.get(t.pk, []))
        area = [b for pk in scopes[t.pk] for b in by_resource.get(pk, [])]
        now = [b for b in area if b.start <= at < _until(b)]
        later = sorted((b for b in area if b.start > at), key=lambda b: b.start)
        if t.counts_party_size:  # пул (кафе): занятость по местам
            tile.seats_taken = sum(b.party_size or 1 for b in now)
            cap = int(t.capacity or 1)
            tile.state = "full" if tile.seats_taken >= cap else "free"
            tile.current = min(now, key=lambda b: b.start) if now else None
            tile.more_now = max(0, len(now) - 1)
        elif now:
            tile.state = "busy"
            tile.current = min(now, key=lambda b: b.start)
            if tile.current.resource_id != t.pk:
                tile.via = by_pk.get(tile.current.resource_id) or tile.current.resource
        if later:
            tile.next_booking = later[0]
            if tile.state == "free":
                tile.free_until = later[0].start
                if later[0].start <= soon_edge:
                    tile.state = "soon"
                    if later[0].resource_id != t.pk:
                        tile.via = by_pk.get(later[0].resource_id) or later[0].resource
        zones.setdefault(t.zone or "", []).append(tile)
    return list(zones.items())


def default_moment(day, raw_time=""):
    """Момент экрана: `?zeit=HH:MM` выбранного дня; иначе «сейчас» (сегодня) или 18:00,
    округление вниз до 15 минут. Мусор — дефолт."""
    from datetime import datetime, time

    tz = timezone.get_current_timezone()
    try:
        hh, mm = (raw_time or "").split(":")
        moment = time(int(hh), int(mm))
    except ValueError:
        if day == timezone.localdate():
            local = timezone.localtime()
            moment = time(local.hour, local.minute)
        else:
            moment = time(18, 0)
    moment = moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)
    return datetime.combine(day, moment, tzinfo=tz)
