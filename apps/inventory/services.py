"""U-D3: сервис склад-леджера — идемпотентная запись + реконсиляция со счётчиком."""

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
