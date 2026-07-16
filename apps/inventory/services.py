"""U-D3: сервис склад-леджера — идемпотентная запись + реконсиляция со счётчиком.

Склад-2 E1 (Chargen/MHD): партии `Lot` — разбивка поверх счётчика; FEFO-расход
(`consume_fefo`) гасит партии по возрастанию MHD. Партии живут только при
`lots_enabled` тенанта и реальном приходе по партиям.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum

from .models import Lot, StockMovement


def lots_enabled(tenant) -> bool:
    """Склад-2 E1: включён ли учёт партий/MHD у тенанта (тумблер site_config).
    По умолчанию выкл — не захламляем не-еду; товар без партий = чистый счётчик."""
    cfg = getattr(tenant, "site_config", None)
    return bool(isinstance(cfg, dict) and cfg.get("lots_enabled"))


def find_entity_by_code(code):
    """R1: найти сущность учёта по SKU или GTIN (штрихкод). Сначала вариант, затем
    товар. → (product, variant) или (None, None). Для scan-to-count в кабинете."""
    from apps.catalog.models import Product, ProductVariant

    code = (code or "").strip()
    if not code:
        return (None, None)
    v = ProductVariant.objects.filter(Q(sku=code) | Q(gtin=code)).select_related("product").first()
    if v is not None:
        return (v.product, v)
    p = Product.objects.filter(Q(sku=code) | Q(gtin=code)).first()
    return (p, None) if p is not None else (None, None)


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


def ledger_balance(product, variant=None) -> int:
    """Сумма дельт леджера по сущности учёта (0, если движений нет).

    T2: variant=None → движения уровня ТОВАРА (variant IS NULL); variant задан →
    движения именно этого варианта. Так товар и каждый вариант сверяются отдельно."""
    qs = StockMovement.objects.filter(product=product)
    qs = qs.filter(variant=variant) if variant is not None else qs.filter(variant__isnull=True)
    return qs.aggregate(s=Sum("delta"))["s"] or 0


def log_catalog_change(*, product, old, new, variant=None, actor=""):
    """T1: каталог правит счётчик НАПРЯМУЮ (форма товара/варианта) — залогировать
    разницу в леджер, НЕ трогая счётчик (его уже выставил каталог). Так каждое
    изменение остатка попадает в историю и реконсиляция остаётся сходящейся.

    new=None (товар стал неучитываемым) → пропуск (реконсилировать нечего).
    old=None трактуем как 0 (новый товар со стартовым остатком)."""
    if new is None:
        return None
    delta = int(new) - (int(old) if old is not None else 0)
    if delta == 0:
        return None
    return record_movement(
        product=product,
        variant=variant,
        kind=StockMovement.KIND_ADJUSTMENT,
        delta=delta,
        source="catalog",
        note="Katalog",
        actor=actor,
    )


def reconciliation(product, variant=None) -> dict:
    """Сверка счётчика и леджера сущности учёта: ``{tracked, counter, ledger,
    diff, ok}``. T2: variant задан → сверяем остаток варианта.

    `ok` — счётчик == сумма дельт леджера. Расхождение обычно значит «стартовый
    остаток до леджера не проведён» (см. record_opening_balance) или счётчик
    правили в обход леджера. Неучитываемый (stock_quantity None) — всегда ok."""
    entity = variant if variant is not None else product
    counter = entity.stock_quantity
    if counter is None:
        return {"tracked": False, "counter": None, "ledger": 0, "diff": 0, "ok": True}
    ledger = ledger_balance(product, variant)
    return {
        "tracked": True,
        "counter": counter,
        "ledger": ledger,
        "diff": counter - ledger,
        "ok": counter == ledger,
    }


def stock_entities():
    """T2: сущности учёта остатка для пикера/таблицы кабинета — варианты
    вариантных товаров + товары без вариантов. ``[{value, label, product, variant}]``.
    `value` — "v<pk>"/"p<pk>" (пикер кодирует тип сущности)."""
    from apps.catalog.models import Product

    out = []
    for p in Product.objects.prefetch_related("variants").order_by("name"):
        variants = list(p.variants.all())
        if variants:
            for v in variants:
                out.append(
                    {"value": f"v{v.pk}", "label": f"{p} · {v.label}", "product": p, "variant": v}
                )
        else:
            out.append({"value": f"p{p.pk}", "label": str(p), "product": p, "variant": None})
    return out


def reconciliation_rows():
    """Строки сверки только по учитываемым сущностям (товар/вариант со
    stock_quantity ≠ None): ``[{value, label, product, variant, counter, ledger,
    diff, ok}]``."""
    rows = []
    for e in stock_entities():
        rec = reconciliation(e["product"], e["variant"])
        if rec["tracked"]:
            rows.append({**e, **rec})
    return rows


def inventory_value():
    """T5: суммарный Warenwert (Bestandswert) по всем учитываемым сущностям +
    разбивка. ``{total: Decimal, rows: [{value,label,product,variant,qty,cost,value}]}``.

    Считается только по сущностям с заданным EK и учитываемым остатком (иначе Wert
    нельзя посчитать); ``total`` — сумма (Decimal, 0 если нечего считать)."""
    from decimal import Decimal

    total = Decimal("0")
    rows = []
    for e in stock_entities():
        entity = e["variant"] if e["variant"] is not None else e["product"]
        value = entity.stock_value
        if value is None:
            continue
        cost = getattr(entity, "cost_value", None)
        if cost is None:
            cost = entity.cost_price
        total += value
        rows.append({**e, "qty": entity.stock_quantity, "cost": cost, "value": value})
    return {"total": total, "rows": rows}


def reorder_suggestions(global_threshold):
    """T5: Bestellvorschläge — сущности учёта, где остаток ≤ Meldebestand (per-Artikel
    ``reorder_point`` или глобальный порог). ``[{value,label,product,variant,counter,
    point,target,suggest}]``.

    ``suggest`` = max(Sollbestand − остаток, 0), если задан ``reorder_target``, иначе
    None (просто «нужен дозаказ»). Сортировка: Ausverkauft (0) первыми, затем по
    возрастанию остатка (самое срочное сверху). Неучитываемые (None) — пропуск."""
    out = []
    for e in stock_entities():
        entity = e["variant"] if e["variant"] is not None else e["product"]
        counter = entity.stock_quantity
        if counter is None:
            continue
        point = entity.effective_reorder_point(global_threshold)
        if point is None or counter > point:
            continue
        target = entity.reorder_target
        suggest = max(target - counter, 0) if target is not None else None
        out.append({**e, "counter": counter, "point": point, "target": target, "suggest": suggest})
    out.sort(key=lambda r: (r["counter"] != 0, r["counter"]))
    return out


def apply_manual_movement(
    *, product, variant=None, kind, delta=0, set_absolute=None, actor="", note=""
):
    """Ручное движение: двигает СЧЁТЧИК и пишет леджер в одной atomic.

    Единственный путь, где движение меняет счётчик (D1: событийные движки уже
    двигают его сами). T2: variant задан → двигаем остаток варианта. `set_absolute`
    (инвентаризация) → счётчик = значение, delta = разница; иначе счётчик += delta
    (клампим в ≥0, delta = факт). None stock_quantity трактуем как 0. Нулевая
    дельта → None. Возвращает StockMovement."""
    from apps.catalog.models import Product, ProductVariant

    with transaction.atomic():
        if variant is not None:
            locked = ProductVariant.objects.select_for_update().get(pk=variant.pk)
            prod = locked.product
        else:
            locked = Product.objects.select_for_update().get(pk=product.pk)
            prod = locked
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
            product=prod,
            variant=locked if variant is not None else None,
            kind=kind,
            delta=change,
            source="manual",
            actor=actor,
            note=note,
        )


def record_opening_balance(*, product, variant=None, actor=""):
    """Провести стартовый остаток: выровнять леджер под текущий счётчик БЕЗ его
    изменения (движение на разницу counter−ledger). T2: variant задан → по варианту.
    После — реконсиляция сходится."""
    entity = variant if variant is not None else product
    counter = entity.stock_quantity
    if counter is None:
        return None
    diff = counter - ledger_balance(product, variant)
    if diff == 0:
        return None
    return record_movement(
        product=product,
        variant=variant,
        kind=StockMovement.KIND_ADJUSTMENT,
        delta=diff,
        source="manual",
        actor=actor,
        note="Startbestand (Abgleich)",
    )


# --- Склад-2 E1: партии (Chargen) + FEFO ------------------------------------------


def _lot_qs(product, variant=None):
    """Партии сущности (товар-без-вариантов | вариант) — как ledger_balance."""
    qs = Lot.objects.filter(product=product)
    return qs.filter(variant=variant) if variant is not None else qs.filter(variant__isnull=True)


def lot_balance(product, variant=None) -> int:
    """Σ остатков партий сущности (для реконсиляции Σlot ↔ счётчик)."""
    return _lot_qs(product, variant).aggregate(s=Sum("qty_remaining"))["s"] or 0


def has_lots(product, variant=None) -> bool:
    """Есть ли у сущности хоть одна партия с остатком (иначе FEFO не применяется —
    расход идёт как раньше, только счётчик)."""
    return _lot_qs(product, variant).filter(qty_remaining__gt=0).exists()


def receive_lot(*, product, variant=None, qty, mhd=None, lot_code="", actor="", note=""):
    """E1: оприходовать партию (Wareneingang по Charge). Двигает счётчик (+qty),
    пишет леджер (receipt) и создаёт `Lot(qty_remaining=qty)` — всё в одной atomic.
    Реюз `apply_manual_movement` для счётчика+леджера, поверх — запись партии."""
    qty = int(qty)
    if qty <= 0:
        return None
    with transaction.atomic():
        mv = apply_manual_movement(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_RECEIPT,
            delta=qty,
            actor=actor,
            note=note or (f"Charge {lot_code}" if lot_code else "Wareneingang"),
        )
        lot = Lot.objects.create(
            product=product,
            variant=variant,
            lot_code=lot_code.strip(),
            mhd=mhd,
            qty_received=qty,
            qty_remaining=qty,
            note=note,
        )
    return lot, mv


def consume_fefo(product, variant=None, *, qty):
    """E1 FEFO: погасить `qty` из партий сущности по возрастанию MHD (ближайший срок
    первым; партии без даты — последними). Возвращает списанное кол-во (может быть
    меньше qty, если партий не хватило — недостачу докрывает чистый счётчик). НЕ
    трогает счётчик и леджер — вызывается ВНУТРИ существующей atomic расхода рядом с
    декрементом счётчика. Партии блокируются select_for_update (без гонок FEFO)."""
    qty = int(qty)
    if qty <= 0:
        return 0
    remaining = qty
    lots = list(
        _lot_qs(product, variant)
        .filter(qty_remaining__gt=0)
        .select_for_update()
        .order_by(F("mhd").asc(nulls_last=True), "created_at")
    )
    for lot in lots:
        if remaining <= 0:
            break
        take = min(lot.qty_remaining, remaining)
        lot.qty_remaining -= take
        lot.save(update_fields=["qty_remaining", "updated_at"])
        remaining -= take
    return qty - remaining


def writeoff_lot(lot_pk, *, actor="", note=""):
    """E1: списать остаток партии (Verderb/просрочка). Гасит `qty_remaining` партии +
    двигает счётчик и пишет леджер (adjustment −remaining) в одной atomic. Возвращает
    списанное кол-во (0 = партия уже пуста / не найдена)."""
    with transaction.atomic():
        try:
            lot = Lot.objects.select_for_update().filter(pk=lot_pk).first()
        except (ValueError, ValidationError):  # некорректный UUID из POST
            return 0
        if lot is None or lot.qty_remaining <= 0:
            return 0
        qty = lot.qty_remaining
        apply_manual_movement(
            product=lot.product,
            variant=lot.variant,
            kind=StockMovement.KIND_ADJUSTMENT,
            delta=-qty,
            actor=actor,
            note=(note or "Verderb")[:200],
        )
        lot.qty_remaining = 0
        lot.save(update_fields=["qty_remaining", "updated_at"])
        return qty


def expiring_lots(*, within_days=None, include_expired=True):
    """E1 MHD-обзор: партии с остатком и датой MHD — для алертов «скоро истекает» /
    «просрочено». within_days=N → только MHD ≤ сегодня+N (None = все с датой).
    Отсортированы FEFO (ближайший срок первым)."""
    from datetime import timedelta

    from django.utils import timezone

    qs = Lot.objects.filter(qty_remaining__gt=0, mhd__isnull=False)
    if within_days is not None:
        qs = qs.filter(mhd__lte=timezone.localdate() + timedelta(days=int(within_days)))
    if not include_expired:
        qs = qs.filter(mhd__gte=timezone.localdate())
    return qs.select_related("product", "variant").order_by("mhd", "created_at")
