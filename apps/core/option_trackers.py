"""MX-2e: enforcement трекеров опций — пул и склад (план mx-followups-plan-2026-08-21.md).

§5b стратегии: опция = цена + трекер. MX-2 завёл виды трекеров информативно;
этот слайс делает их ЧЕСТНЫМИ:

- `pool` — у опции собственный пул (`Extra.pool_size`, «8 прокатных мотоциклов»):
  продажа проверяет занятость пула в окне ИСПОЛНЕНИЯ сделки и отказывает при
  переполнении (PoolFull). Сериализация — `select_for_update` строки Extra
  (тот же приём, что anti-oversell ресурса/юнита). Занятость считается сканом
  активных сделок ТРЁХ kind (stay/ticket/booking) со строкой этой опции в
  снимке — SME-объёмы, JSON-поля; отменённые отфильтрованы реестром статусов
  (кастом-cancel тоже).
- `stock` — опция расходует Вещь (`Extra.product`): движение
  `source="option", source_ref="<kind>:<deal_pk>:<extra_pk>"` пишется ПЕРВЫМ
  (идемпотентность (source, source_ref, kind) — даром), счётчик двигается
  только если движение реально создано; нехватка → OptionOutOfStock (общий
  принцип anti-oversell: продажа при нехватке отказывает). Возврат при отмене
  зеркален и переживает двойной вызов (builtin-хук FSM + зеркало кастом-статусов).

v2 (вторая отмашка «Делай»): qty = consume_qty × ночи (stay+per_night — как
деньги снимка); партии FEFO гасятся/доливаются при включённых партиях (зеркало
orders); возврат читает |delta| sale-движения — точный qty, переживает смену
конфига опции после продажи. Изменение ДАТ брони расход не пере-списывает
(продано — учтено; объявленное ограничение плана).
"""

from datetime import timedelta

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import F


class PoolFull(Exception):
    """Пул опции исчерпан в окне исполнения сделки."""

    def __init__(self, label, available=0):
        self.label = label
        self.available = max(0, available)
        super().__init__(label)


class OptionOutOfStock(Exception):
    """Складская Вещь опции закончилась."""

    def __init__(self, label):
        self.label = label
        super().__init__(label)


def _snap_option_ids(snap):
    return {str(e.get("id")) for e in (snap or []) if isinstance(e, dict) and e.get("id")}


def window_for(kind: str, deal) -> tuple:
    """Окно ИСПОЛНЕНИЯ сделки (date_from, date_to), обе даты включительно.

    stay — ночи (departure сам по себе не занимает: выезд утром);
    ticket — дни события; booking — день слота."""
    if kind == "stay":
        return deal.arrival, deal.departure - timedelta(days=1)
    if kind == "ticket":
        start = deal.event.starts_at.date()
        end = deal.event.ends_at.date() if deal.event.ends_at else start
        return start, end
    if kind == "booking":
        day = deal.start.date()
        return day, day
    raise ValueError(f"no execution window for kind {kind!r}")


def _cancelled(kind):
    from django.db import connection

    from apps.core import status_registry

    tenant = getattr(connection, "tenant", None)
    return status_registry.cancelled_statuses_for(kind, tenant)


def pool_usage(extra, date_from, date_to, *, exclude=None) -> int:
    """Сколько единиц пула опции занято активными сделками, чьё окно исполнения
    пересекает [date_from, date_to]. exclude=(kind, pk) — не считать саму сделку
    (правка состава). Одна сделка = одна единица пула (v1)."""
    eid = str(extra.pk)
    used = 0

    def _overlaps(a_from, a_to):
        return a_from <= date_to and a_to >= date_from

    StayBooking = django_apps.get_model("stays", "StayBooking")
    for b in (
        StayBooking.objects.filter(arrival__lte=date_to, departure__gt=date_from)
        .exclude(status__in=_cancelled("stay"))
        .exclude(extras=[])
        .only("id", "arrival", "departure", "extras")
    ):
        if exclude == ("stay", str(b.pk)):
            continue
        if eid in _snap_option_ids(b.extras):
            used += 1

    Ticket = django_apps.get_model("events", "Ticket")
    for t in (
        Ticket.objects.select_related("event")
        .exclude(status__in=_cancelled("ticket"))
        .exclude(extras=[])
        .filter(event__starts_at__date__lte=date_to)
        .only("id", "extras", "event__starts_at", "event__ends_at")
    ):
        if exclude == ("ticket", str(t.pk)):
            continue
        t_from, t_to = window_for("ticket", t)
        if _overlaps(t_from, t_to) and eid in _snap_option_ids(t.extras):
            used += 1

    Booking = django_apps.get_model("booking", "Booking")
    for b in (
        Booking.objects.filter(start__date__gte=date_from, start__date__lte=date_to)
        .exclude(status__in=_cancelled("booking"))
        .exclude(extras=[])
        .only("id", "start", "extras")
    ):
        if exclude == ("booking", str(b.pk)):
            continue
        if eid in _snap_option_ids(b.extras):
            used += 1

    return used


def _movement_ref(kind, deal, extra_id) -> str:
    """Ключ идемпотентности движения опции. Составной "<kind>:<deal>:<extra>" из
    двух UUID не влезает в varchar(64) source_ref → детерминированный md5 (32)."""
    import hashlib

    return hashlib.md5(f"option:{kind}:{deal.pk}:{extra_id}".encode()).hexdigest()


def _stock_qty(extra, kind, deal) -> int:
    """v2-рецепт: расход = consume_qty × ночи (stay+per_night — ровно как
    множатся ДЕНЬГИ снимка), иначе × 1. Минимум 1."""
    per_unit = max(1, int(getattr(extra, "consume_qty", 1) or 1))
    if kind == "stay" and extra.per_night:
        nights = (deal.departure - deal.arrival).days
        return per_unit * max(1, nights)
    return per_unit


def _commit_stock_option(extra, kind, deal):
    """Списать Вещь stock-опции: движение ПЕРВЫМ (идемпотентно), счётчик — только
    если движение создано. Нехватка учитываемого остатка → OptionOutOfStock.
    v2: qty по рецепту (consume_qty × ночи); партии FEFO гасятся в той же atomic
    (зеркало orders._reserve_stock)."""
    from apps.catalog.models import Product
    from apps.inventory.services import consume_fefo, has_lots, record_movement

    if extra.product_id is None:
        return
    qty = _stock_qty(extra, kind, deal)
    product = Product.objects.select_for_update().get(pk=extra.product_id)
    if product.stock_quantity is not None and product.stock_quantity < qty:
        raise OptionOutOfStock(extra.label)
    movement = record_movement(
        product=product,
        kind="sale",
        delta=-qty,
        source="option",
        source_ref=_movement_ref(kind, deal, extra.pk),
        note=getattr(deal, "reference_code", "") or "",
    )
    if movement is not None and product.stock_quantity is not None:
        Product.objects.filter(pk=product.pk, stock_quantity__isnull=False).update(
            stock_quantity=F("stock_quantity") - qty
        )
        if has_lots(product, None):
            consume_fefo(product, None, qty=qty)


def _release_stock_option(extra_id, product_id, kind, deal, label=""):
    """Вернуть Вещь stock-опции. Идемпотентно: restore-движение по тому же
    source_ref; дубль (None) счётчик не двигает. Возврат ТОЛЬКО при
    существующем sale-движении — иначе смена трекера опции после продажи
    несправедливо доливала бы склад."""
    from apps.catalog.models import Product
    from apps.inventory.models import StockMovement
    from apps.inventory.services import record_movement

    ref = _movement_ref(kind, deal, extra_id)
    # v2: возврат читает |delta| SALE-движения — точный qty, переживает смену
    # consume_qty/дат после продажи (возвращаем ровно списанное).
    sold = (
        StockMovement.objects.filter(source="option", source_ref=ref, kind="sale")
        .values_list("delta", flat=True)
        .first()
    )
    if sold is None:
        return
    qty = abs(int(sold))
    if qty <= 0:
        return
    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        return
    movement = record_movement(
        product=product,
        kind="return",
        delta=qty,
        source="option",
        source_ref=ref,
        note=getattr(deal, "reference_code", "") or "",
    )
    if movement is not None and product.stock_quantity is not None:
        from apps.inventory.services import has_lots, restore_fefo

        Product.objects.filter(pk=product.pk, stock_quantity__isnull=False).update(
            stock_quantity=F("stock_quantity") + qty
        )
        if has_lots(product, None):
            restore_fefo(product, None, qty=qty)


def _tracked_extras(option_ids):
    """Живые Extra выбранных id с непустым трекером (pool/stock). Порядок по pk —
    стабильный порядок блокировок (меньше шанс дедлока)."""
    from apps.core.models import Extra

    if not option_ids:
        return []
    return list(
        Extra.objects.filter(pk__in=list(option_ids))
        .exclude(tracker="")
        .order_by("pk")
        .select_for_update()
    )


def commit_options(snap, *, kind, deal):
    """Обработать трекеры опций снимка ПРИ ПРОДАЖЕ. Вызывать в той же atomic,
    что создание сделки (откат исключения откатывает всё — паттерн OutOfStock).

    pool → проверка занятости окна исполнения (PoolFull); stock → списание
    (OptionOutOfStock). Опции-надбавки и легаси-строки без id — no-op.
    Сделка к этому моменту УЖЕ создана и исключается из подсчёта сама —
    иначе off-by-one: первая же продажа считала бы себя занятостью."""
    ids = _snap_option_ids(snap)
    if not ids:
        return
    with transaction.atomic():
        tracked = _tracked_extras(ids)
        if not tracked:
            return
        date_from, date_to = window_for(kind, deal)
        exclude = (kind, str(deal.pk))
        for extra in tracked:
            if extra.tracker == "pool" and extra.pool_size:
                used = pool_usage(extra, date_from, date_to, exclude=exclude)
                if used >= extra.pool_size:
                    raise PoolFull(extra.label, available=extra.pool_size - used)
            elif extra.tracker == "stock":
                _commit_stock_option(extra, kind, deal)


def release_options(kind, deal, snap=None):
    """Вернуть stock-опции при отмене сделки. Идемпотентно (двойной вызов из
    builtin-хука и зеркала кастом-статусов безопасен). Пул отдельного возврата
    не требует — занятость считается по НЕотменённым сделкам."""
    from apps.core.models import Extra

    rows = snap if snap is not None else getattr(deal, "extras", None)
    ids = _snap_option_ids(rows)
    if not ids:
        return
    with transaction.atomic():
        for extra in Extra.objects.filter(pk__in=list(ids), tracker="stock").order_by("pk"):
            _release_stock_option(str(extra.pk), extra.product_id, kind, deal, extra.label)


def sync_options(old_snap, new_snap, *, kind, deal):
    """MX-3-правка состава: убранные опции вернуть, добавленные — провести
    (с enforcement'ом). Пересечение не трогаем."""
    old_ids = _snap_option_ids(old_snap)
    new_ids = _snap_option_ids(new_snap)
    removed = [e for e in (old_snap or []) if str(e.get("id")) in (old_ids - new_ids)]
    added = [e for e in (new_snap or []) if str(e.get("id")) in (new_ids - old_ids)]
    if removed:
        release_options(kind, deal, snap=removed)
    if added:
        commit_options(added, kind=kind, deal=deal)
