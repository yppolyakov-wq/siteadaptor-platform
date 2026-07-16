"""Склад-2 E2 (Мультисклад): баланс per-Standort + Umlagerung.

Вариант A (план sklad-2-e2 §1): счётчик `stock_quantity` остаётся ИТОГО-истиной,
локации — разбивка, выведенная из леджера. Семантика v1:

- баланс НЕ-дефолтной локации = Σ дельт её движений леджера (located-приёмки+перебросы);
- баланс дефолтной («основной склад») = счётчик − Σ не-дефолтных → Σ по локациям
  сходится со счётчиком ПО ПОСТРОЕНИЮ (легаси-история с location=NULL валидна без
  бэкфилла: NULL-движения и есть основной склад);
- Umlagerung = пара движений transfer_out(−N, src)/transfer_in(+N, dst) в одной atomic,
  счётчик не двигается (Σ=0).
"""

from django.db import transaction
from django.db.models import Sum

from .models import StockLocation, StockMovement


def locations_enabled() -> bool:
    """Ленивая активация: мультисклад-UI виден только когда локаций > 1
    (одна локация эквивалентна сегодняшнему «одному складу»)."""
    return StockLocation.objects.filter(is_active=True).count() > 1


def default_location():
    """Дефолтная локация (основной склад) или None, если локации не заведены."""
    return (
        StockLocation.objects.filter(is_default=True).first()
        or StockLocation.objects.order_by("created_at").first()
    )


def _entity_movements(product, variant=None):
    qs = StockMovement.objects.filter(product=product)
    return qs.filter(variant=variant) if variant is not None else qs.filter(variant__isnull=True)


def location_balance(product, variant=None, *, location) -> int:
    """Баланс сущности на локации. НЕ-дефолтная → Σ дельт её движений; дефолтная
    (или None) → счётчик − Σ не-дефолтных (легаси NULL-история = основной склад)."""
    entity = variant if variant is not None else product
    counter = entity.stock_quantity or 0
    if location is not None and not location.is_default:
        s = _entity_movements(product, variant).filter(location=location)
        return s.aggregate(s=Sum("delta"))["s"] or 0
    nondefault = (
        _entity_movements(product, variant)
        .filter(location__isnull=False, location__is_default=False)
        .aggregate(s=Sum("delta"))["s"]
        or 0
    )
    return counter - nondefault


def location_rows(product, variant=None) -> list[dict]:
    """Разбивка остатка сущности по локациям: [{location, qty, is_default}]. Дефолт
    первым. Пусто, если локаций нет (мультисклад не активирован)."""
    locs = list(StockLocation.objects.filter(is_active=True))
    if not locs:
        return []
    default = default_location()
    rows = []
    for loc in locs:
        is_def = default is not None and loc.pk == default.pk
        qty = location_balance(product, variant, location=loc if not is_def else None)
        rows.append({"location": loc, "qty": qty, "is_default": is_def})
    rows.sort(key=lambda r: (not r["is_default"], r["location"].name))
    return rows


def transfer(*, product, variant=None, src=None, dst=None, qty, actor="", note=""):
    """Umlagerung: переместить `qty` сущности src → dst (None = дефолтная локация).
    Пара движений transfer_out/transfer_in в одной atomic; счётчик НЕ двигается.
    Клампится по балансу src (в минус не уводим). Возвращает перемещённое кол-во."""
    qty = int(qty)
    default = default_location()
    src = src if src is not None else default
    dst = dst if dst is not None else default
    if qty <= 0 or src is None or dst is None or src.pk == dst.pk:
        return 0
    with transaction.atomic():
        available = location_balance(product, variant, location=None if src.is_default else src)
        move = min(qty, max(0, available))
        if move <= 0:
            return 0
        StockMovement.objects.create(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_TRANSFER_OUT,
            delta=-move,
            location=src,
            source="transfer",
            actor=actor,
            note=(note or f"→ {dst.name}")[:200],
        )
        StockMovement.objects.create(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_TRANSFER_IN,
            delta=move,
            location=dst,
            source="transfer",
            actor=actor,
            note=(note or f"← {src.name}")[:200],
        )
    return move
