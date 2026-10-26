"""KA-12 WR-8 (E1.5): поштучный возврат выданного/отправленного заказа.

Товар фиксируется сразу (он физически вернулся): `OrderItem.returned_qty` растёт условным
UPDATE (ожидаемое значение из формы — двойной клик и гонка не засчитают дважды), годное —
снова на склад тем же путём, что отмена (F() + леджер + FEFO). Деньги — ТЕМ ЖЕ путём, что
«Preisminderung» на карточке (`refunds.refund_partial`, reason=minderung): часть платежа,
скидка сделки, сторно выручки, Rechnungskorrektur при выставленном счёте.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F

from .models import Order, OrderItem

RETURNABLE_STATUSES = (Order.STATUS_PICKED_UP, Order.STATUS_SHIPPED)
REFUND_METHODS = ("card", "offline", "none")


class GoodsResult(enum.Enum):
    RETURNED = "returned"
    NOTHING = "nothing"  # пустая форма / ничего не выбрано
    NOT_RETURNABLE = "not_returnable"  # статус не тот
    STALE = "stale"  # форма устарела: позицию уже вернули (двойной клик / второй сотрудник)


@dataclass(frozen=True)
class Line:
    item_pk: str
    qty: int
    restock: bool
    expected_returned: int


@dataclass
class ReturnOutcome:
    goods: GoodsResult
    cents: int = 0
    pieces: int = 0
    refund: object = None  # refunds.RefundResult | None (без денег / без права)


def returnable_items(order):
    """Позиции, по которым ещё можно оформить возврат (для формы)."""
    return [item for item in order.items.all() if item.returnable_qty > 0]


def _restock(item, qty: int, cumulative: int, reference: str) -> bool:
    from apps.catalog.models import Product, ProductVariant
    from apps.inventory.services import record_movement, restore_fefo

    if item.combo_id and not item.product_id:
        return False  # набор: состав — снимок, на склад не кладём
    if item.variant_id:
        n = ProductVariant.objects.filter(pk=item.variant_id, stock_quantity__isnull=False).update(
            stock_quantity=F("stock_quantity") + qty
        )
    else:
        n = Product.objects.filter(pk=item.product_id, stock_quantity__isnull=False).update(
            stock_quantity=F("stock_quantity") + qty
        )
    if not n:
        return False  # товар без складского учёта — считать нечего
    record_movement(
        product=item.product,
        variant=item.variant,
        kind="return",
        delta=qty,
        source="order",
        # Своя ссылка на каждую порцию: полный `returned` позже пишет `<item>` без суффикса.
        source_ref=f"{item.pk}:ret:{cumulative}",
        note=reference,
    )
    restore_fefo(item.product, item.variant, qty=qty)
    return True


def return_goods(order, lines: list[Line]) -> tuple[GoodsResult, int, int]:
    """Зафиксировать вернувшийся товар. → (результат, сумма в центах, штук)."""
    lines = [ln for ln in lines if ln.qty > 0]
    if not lines:
        return GoodsResult.NOTHING, 0, 0
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status not in RETURNABLE_STATUSES:
            return GoodsResult.NOT_RETURNABLE, 0, 0
        items = {str(i.pk): i for i in OrderItem.objects.filter(order=locked)}
        factor = _paid_factor(locked, items.values())
        nominal = Decimal("0")
        pieces = 0
        for ln in lines:
            item = items.get(ln.item_pk)
            if item is None or ln.qty > item.returnable_qty:
                transaction.set_rollback(True)
                return GoodsResult.STALE, 0, 0
            new = item.returned_qty + ln.qty
            updated = OrderItem.objects.filter(
                pk=item.pk, returned_qty=ln.expected_returned
            ).update(returned_qty=new)
            if not updated:
                transaction.set_rollback(True)
                return GoodsResult.STALE, 0, 0
            if ln.restock and _restock(item, ln.qty, new, locked.reference_code):
                OrderItem.objects.filter(pk=item.pk).update(
                    restocked_qty=F("restocked_qty") + ln.qty
                )
            nominal += Decimal(str(item.unit_price or 0)) * ln.qty
            pieces += ln.qty
    cents = int((nominal * factor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return GoodsResult.RETURNED, cents, pieces


def _paid_factor(order, items) -> Decimal:
    """Доля цены, реально уплаченная за товар (ревью WR-8): скидка заказа делится на
    позиции пропорционально, доставка не возвращается. Инвариант: каждая Minderung
    снимает «номинал × доля», поэтому «оплачено за товар / номинал ещё не возвращённого»
    остаётся той же долей и при втором, третьем частичном возврате."""
    remaining = sum(
        (Decimal(str(i.unit_price or 0)) * i.returnable_qty for i in items), Decimal("0")
    )
    if remaining <= 0:
        return Decimal("0")
    paid_goods = Decimal(str(order.total or 0)) - Decimal(order.shipping_cents or 0) / 100
    return max(min(paid_goods / remaining, Decimal("1")), Decimal("0"))


def refundable_cents(order) -> int:
    """Сколько можно вернуть уступкой в цене (как форма «Preisminderung»): не больше
    полученного и итога; 0 — если Minderung заблокирована (сертификат, Stornorechnung…)."""
    from apps.core import folio, money_contract, refunds

    rows = folio.rows("order", order)
    net = sum(r.amount_cents - r.refunded_cents for r in rows)
    total = int((money_contract._total("order", order) * 100).to_integral_value())
    if net <= 0 or refunds._minderung_blocked("order", order, 1):
        return 0
    return min(net, total)


def return_items(order, lines: list[Line], *, method: str, tenant=None, user=None):
    """Возврат товара + (по выбору) денег. Деньги — только с правом `geld.korrektur`
    (проверяет вызывающий) и не больше `refundable_cents`; иначе товар фиксируется,
    а деньги владелец возвращает вручную позже (честное сообщение во вьюхе)."""
    from django.core.cache import cache

    # Ревью WR-8: товар и деньги — две транзакции (Stripe нельзя звать под блокировкой
    # строки). Замок на заказ на всё действие: второй параллельный возврат ждёт отказом,
    # а не проходит проверку суммы до того, как первый вернул деньги.
    lock = f"order-return:{order.pk}"
    if not cache.add(lock, 1, 120):
        return ReturnOutcome(goods=GoodsResult.STALE)
    try:
        return _return_items(order, lines, method=method, tenant=tenant, user=user)
    finally:
        cache.delete(lock)


def _return_items(order, lines, *, method, tenant, user):
    from apps.core import refunds

    goods, cents, pieces = return_goods(order, lines)
    outcome = ReturnOutcome(goods=goods, cents=cents, pieces=pieces)
    if goods != GoodsResult.RETURNED or method not in ("card", "offline") or cents <= 0:
        return outcome
    order.refresh_from_db()
    if cents > refundable_cents(order):
        outcome.refund = refunds.RefundResult.REFUSED
        return outcome
    outcome.refund = refunds.refund_partial(
        "order", order, cents=cents, method=method, tenant=tenant, user=user, reason="minderung"
    )
    return outcome
