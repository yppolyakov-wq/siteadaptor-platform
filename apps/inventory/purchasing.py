"""Склад-2 E3 (Закупки/M12): сервисы закупочных заказов (Bestellwesen).

Инвариант D1: Bestellung — планирование, счётчик НЕ трогает до приёмки. Приёмка строки
(`receive_po_line`) книжит Wareneingang существующим складским путём (`receive_lot` при
`lots_enabled`, иначе `apply_manual_movement(receipt)`) → счётчик/леджер двигаются ТОЛЬКО
там. Движение тегируется `source="purchase"` (провенанс).
"""

import secrets

from django.db import transaction
from django.utils import timezone

from . import services
from .models import BestellPosition, Bestellung, Lieferant, StockMovement

_ALPHABET = "ACDEFGHJKLMNPQRSTUVWXYZ2345679"  # без похожих символов (как order-код)


def _unique_po_code() -> str:
    for _ in range(10):
        code = "BE-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Bestellung.objects.filter(reference=code).exists():
            return code
    raise RuntimeError("could not generate unique purchase-order reference code")


def create_po(*, supplier=None, actor="", note="") -> Bestellung:
    """Создать черновик закупочного заказа (Entwurf). supplier — Lieferant | None."""
    return Bestellung.objects.create(
        supplier=supplier,
        reference=_unique_po_code(),
        status=Bestellung.STATUS_DRAFT,
        actor=actor or "",
        note=(note or "")[:300],
    )


def add_po_line(bestellung, *, product, variant=None, qty=1, unit_cost=None, note=""):
    """Добавить строку в заказ. EK-снимок: `unit_cost` или `cost_price` сущности (T5)."""
    qty = max(1, int(qty))
    entity = variant if variant is not None else product
    if unit_cost is None:
        unit_cost = getattr(entity, "cost_price", None) or 0
    return BestellPosition.objects.create(
        bestellung=bestellung,
        product=product,
        variant=variant,
        qty=qty,
        unit_cost=unit_cost,
        note=(note or "")[:200],
    )


def set_po_status(bestellung, status, *, actor="") -> Bestellung:
    """Сменить статус заказа с проставлением ordered_at/received_at. Идемпотентно."""
    if status == bestellung.status:
        return bestellung
    fields = ["status", "updated_at"]
    bestellung.status = status
    if status == Bestellung.STATUS_ORDERED and bestellung.ordered_at is None:
        bestellung.ordered_at = timezone.now()
        fields.append("ordered_at")
    if status == Bestellung.STATUS_RECEIVED and bestellung.received_at is None:
        bestellung.received_at = timezone.now()
        fields.append("received_at")
    if actor:
        bestellung.actor = actor[:150]
        fields.append("actor")
    bestellung.save(update_fields=fields)
    return bestellung


def receive_po_line(
    position, *, qty=None, tenant=None, mhd=None, lot_code="", actor="", update_cost=False
):
    """Принять `qty` штук по строке (частичная приёмка). Книжит Wareneingang складским
    путём (E1 `receive_lot` при включённых партиях, иначе `apply_manual_movement`),
    двигает счётчик один раз, помечает `qty_received += qty`. `qty=None` → принять всё
    оставшееся (`qty_open`). `tenant` — для тумблера партий (иначе connection.tenant).
    `update_cost=True` → обновить `cost_price` сущности из EK строки (форк владельца, по
    умолчанию выкл). Возвращает принятое кол-во (int)."""
    open_qty = position.qty_open
    take = open_qty if qty is None else max(0, min(int(qty), open_qty))
    if take <= 0:
        return 0
    product = position.product
    variant = position.variant
    tenant_lots = _tenant_lots_enabled(tenant)
    with transaction.atomic():
        if tenant_lots:
            services.receive_lot(
                product=product,
                variant=variant,
                qty=take,
                mhd=mhd,
                lot_code=lot_code,
                actor=actor,
                note=f"{position.bestellung.reference}",
                source="purchase",
            )
        else:
            services.apply_manual_movement(
                product=product,
                variant=variant,
                kind=StockMovement.KIND_RECEIPT,
                delta=take,
                actor=actor,
                note=f"{position.bestellung.reference}",
                source="purchase",
            )
        position.qty_received += take
        position.save(update_fields=["qty_received", "updated_at"])
        if update_cost and position.unit_cost:
            entity = variant if variant is not None else product
            entity.cost_price = position.unit_cost
            entity.save(update_fields=["cost_price", "updated_at"])
        # Заказ полностью принят → статус received.
        bestellung = position.bestellung
        if bestellung.status == Bestellung.STATUS_ORDERED and bestellung.is_fully_received:
            set_po_status(bestellung, Bestellung.STATUS_RECEIVED, actor=actor)
    return take


def _tenant_lots_enabled(tenant=None) -> bool:
    """Тумблер партий тенанта. Явный `tenant` (из request.tenant во вьюхе) приоритетен;
    иначе — connection.tenant (schema-local контекст django-tenants)."""
    if tenant is None:
        from django.db import connection

        tenant = getattr(connection, "tenant", None)
    return bool(tenant is not None and services.lots_enabled(tenant))


def draft_from_suggestions(suggestions, *, supplier=None, actor="") -> Bestellung:
    """E3.3-хелпер: собрать черновик заказа из Bestellvorschläge (T5). `suggestions` —
    список строк `reorder_suggestions()` (`{product, variant, suggest, ...}`); строки с
    `suggest` (Sollbestand задан) кладём в заказ на предложенное кол-во."""
    po = create_po(supplier=supplier, actor=actor)
    for s in suggestions:
        qty = s.get("suggest") or 0
        if qty > 0:
            add_po_line(po, product=s["product"], variant=s.get("variant"), qty=qty)
    return po


def suppliers(active_only=True):
    qs = Lieferant.objects.all()
    return qs.filter(is_active=True) if active_only else qs
