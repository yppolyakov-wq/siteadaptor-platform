"""U-D3: сервис склад-леджера — идемпотентная запись + реконсиляция со счётчиком."""

from django.db import transaction
from django.db.models import Sum

from .models import StockMovement


def record_movement(
    *, product, kind, delta, variant=None, source="", source_ref="", note="", actor=""
):
    """Записать движение остатка (append-only; НЕ трогает счётчик — D1).

    Идемпотентно по (source, source_ref, kind) для событийных движений (дубль →
    no-op, вернёт None); ручные (source_ref="") пишутся всегда. delta=0 → no-op.
    Вызывать в ТОЙ ЖЕ atomic-транзакции, что и декремент счётчика (UD3-2), но
    движение его не заменяет. Возвращает StockMovement или None (дубль/ноль).
    """
    if not delta:
        return None
    defaults = {
        "product": product,
        "variant": variant,
        "delta": int(delta),
        "note": (note or "")[:200],
        "actor": (actor or "")[:150],
    }
    if not source_ref:  # ручное движение — без дедупа
        return StockMovement.objects.create(kind=kind, source=source, source_ref="", **defaults)
    obj, created = StockMovement.objects.get_or_create(
        source=source, source_ref=source_ref, kind=kind, defaults=defaults
    )
    return obj if created else None


def ledger_balance(product) -> int:
    """Сумма всех дельт леджера по товару (0, если движений нет)."""
    return StockMovement.objects.filter(product=product).aggregate(s=Sum("delta"))["s"] or 0


def reconciliation(product) -> dict:
    """Сверка счётчика и леджера товара: ``{tracked, counter, ledger, diff, ok}``.

    `ok` — счётчик == сумма дельт леджера. Расхождение обычно значит «стартовый
    остаток до леджера не проведён» (см. record_opening_balance) или счётчик
    правили в обход леджера. Неучитываемый (stock_quantity None) — всегда ok."""
    counter = product.stock_quantity
    if counter is None:
        return {"tracked": False, "counter": None, "ledger": 0, "diff": 0, "ok": True}
    ledger = ledger_balance(product)
    return {
        "tracked": True,
        "counter": counter,
        "ledger": ledger,
        "diff": counter - ledger,
        "ok": counter == ledger,
    }


def apply_manual_movement(*, product, kind, delta=0, set_absolute=None, actor="", note=""):
    """Ручное движение: двигает СЧЁТЧИК и пишет леджер в одной atomic.

    Единственный путь, где движение меняет счётчик (D1: событийные движки уже
    двигают его сами). `set_absolute` (инвентаризация) → счётчик = значение,
    delta = разница; иначе счётчик += delta (клампим в ≥0, delta = факт). None
    stock_quantity трактуем как 0. Нулевая дельта → None. Возвращает StockMovement.
    """
    from apps.catalog.models import Product

    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)
        current = locked.stock_quantity or 0
        if set_absolute is not None:
            new = max(0, int(set_absolute))
        else:
            new = max(0, current + int(delta))
        change = new - current
        if change == 0:
            return None
        locked.stock_quantity = new
        locked.save(update_fields=["stock_quantity", "updated_at"])
        return record_movement(
            product=locked, kind=kind, delta=change, source="manual", actor=actor, note=note
        )


def record_opening_balance(*, product, actor=""):
    """Провести стартовый остаток: выровнять леджер под текущий счётчик БЕЗ его
    изменения (движение на разницу counter−ledger). После — реконсиляция сходится."""
    counter = product.stock_quantity
    if counter is None:
        return None
    diff = counter - ledger_balance(product)
    if diff == 0:
        return None
    return record_movement(
        product=product,
        kind=StockMovement.KIND_ADJUSTMENT,
        delta=diff,
        source="manual",
        actor=actor,
        note="Startbestand (Abgleich)",
    )
