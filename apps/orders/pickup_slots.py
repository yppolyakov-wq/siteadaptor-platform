"""KA-W1: время самовывоза — окна из часов работы, ёмкость, отсечка.

`Order.pickup_slot` существует с orders/0001 и его уже читают Auftragsbuch, карточка
сделки и «Heute», но выбрать время на витрине было нельзя. Здесь — сетка окон и
проверка выбора; запись (с блокировкой под гонкой) — в `services.create_order`.

Настройка — `site_config["pickup_slots"]` (см. `siteconfig.normalize_pickup_slots`);
нет ключа → модуль молчит, чекаут прежний.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from django.db import connection
from django.utils import timezone

from apps.tenants import openinghours


class SlotFull(Exception):
    """Окно самовывоза заполнилось, пока покупатель оформлял заказ."""


def config(tenant) -> dict | None:
    from apps.tenants import siteconfig

    return siteconfig.normalize(getattr(tenant, "site_config", None) or {}).get("pickup_slots")


def _taken(tenant, start, end) -> Counter:
    from apps.core import status_registry

    from .models import Order

    rows = (
        Order.objects.filter(
            fulfillment=Order.FULFILLMENT_PICKUP,
            pickup_slot__gte=start,
            pickup_slot__lt=end,
        )
        .exclude(status__in=status_registry.cancelled_statuses_for("order", tenant))
        .values_list("pickup_slot", flat=True)
    )
    return Counter(timezone.localtime(dt).replace(microsecond=0) for dt in rows)


def slots_for(tenant, now=None, cfg=None) -> list[tuple]:
    """[(date, [(aware_dt, remaining|None), …]), …] — только дни, где есть окна.

    Окно предлагается, если начинается не раньше now + lead и целиком лежит в часах
    работы; полностью занятые окна не показываются. remaining=None — без лимита."""
    cfg = cfg if cfg is not None else config(tenant)
    if not cfg:
        return []
    hours = openinghours.normalize(getattr(tenant, "opening_hours_structured", None))
    if not hours:
        return []
    now = timezone.localtime(now or timezone.now())
    earliest = now + timedelta(minutes=cfg["lead"])
    step = timedelta(minutes=cfg["step"])
    capacity = cfg["capacity"]
    grid = []
    for offset in range(cfg["days"]):  # календарные дни, начиная с сегодня
        day = (now + timedelta(days=offset)).date()
        rng = hours.get(str(day.weekday()))
        if not rng:
            continue
        opens = openinghours._parse_hhmm(rng[0])
        closes = openinghours._parse_hhmm(rng[1])
        start = timezone.make_aware(datetime.combine(day, opens))
        end = timezone.make_aware(datetime.combine(day, closes))
        day_slots = []
        slot = start
        while slot + step <= end:
            if slot >= earliest:
                day_slots.append(slot)
            slot += step
        if day_slots:
            grid.append((day, day_slots))
    if not grid:
        return []
    taken = _taken(tenant, grid[0][1][0], grid[-1][1][-1] + step) if capacity else Counter()
    out = []
    for day, day_slots in grid:
        row = []
        for slot in day_slots:
            if capacity:
                left = capacity - taken.get(slot, 0)
                if left <= 0:
                    continue
                row.append((slot, left))
            else:
                row.append((slot, None))
        if row:
            out.append((day, row))
    return out


def parse(raw):
    """ISO-строка из формы → aware datetime (локальная зона) или None."""
    value = (raw or "").strip()
    if not value or len(value) > 40:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return timezone.localtime(dt).replace(microsecond=0)


def validate(tenant, raw, now=None, cfg=None):
    """Выбор покупателя → aware datetime из текущей сетки, иначе None (fail-closed)."""
    chosen = parse(raw)
    if chosen is None:
        return None
    for _day, row in slots_for(tenant, now=now, cfg=cfg):
        for slot, _left in row:
            if slot == chosen:
                return slot
    return None


def claim(slot, capacity, tenant=None) -> None:
    """Под гонкой: внутри транзакции create_order. Блокировка на окно (схема в ключе —
    advisory-блокировки общие на всю БД), пересчёт, SlotFull при заполненном окне."""
    if not slot or not capacity:
        return
    tenant = tenant or getattr(connection, "tenant", None)
    key = f"pickup:{connection.schema_name}:{slot.isoformat()}"
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])
    if (
        _taken(tenant, slot, slot + timedelta(seconds=1)).get(
            timezone.localtime(slot).replace(microsecond=0), 0
        )
        >= capacity
    ):
        raise SlotFull()
