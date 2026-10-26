"""KA-12 WR-7 (E3.10): производственный список дня — Σ штук по товару/варианту/набору."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q, Sum

from .models import Order, OrderItem

OPEN_STATUSES = (Order.STATUS_NEW, Order.STATUS_CONFIRMED)
DONE_STATUSES = (Order.STATUS_READY,)


@dataclass
class Row:
    name: str
    variant_label: str
    sku: str
    todo: int
    done: int
    orders: int

    @property
    def total(self) -> int:
        return self.todo + self.done


def _name(obj) -> str:
    """Имя на языке кабинета: товар — `name_text` (JSON по локалям), набор — оверлей."""
    if obj is None:
        return "—"
    if hasattr(obj, "name_text"):
        return obj.name_text or "—"
    return obj.name_localized() or "—"


def production_list(day) -> list[Row]:
    """Позиции заказов с выдачей в `day` (локальная дата), по убыванию «zu produzieren»."""
    from apps.catalog.models import Combo, Product

    agg = (
        OrderItem.objects.filter(
            order__pickup_slot__date=day,
            order__status__in=OPEN_STATUSES + DONE_STATUSES,
        )
        .values("product_id", "combo_id", "variant_label", "sku")
        .annotate(
            todo=Sum("qty", filter=Q(order__status__in=OPEN_STATUSES), default=0),
            done=Sum("qty", filter=Q(order__status__in=DONE_STATUSES), default=0),
            orders=Count("order_id", distinct=True),
        )
        .order_by()
    )
    agg = list(agg)
    products = Product.objects.in_bulk({a["product_id"] for a in agg if a["product_id"]})
    combos = Combo.objects.in_bulk({a["combo_id"] for a in agg if a["combo_id"]})
    rows = [
        Row(
            name=_name(
                combos.get(a["combo_id"]) if a["combo_id"] else products.get(a["product_id"])
            ),
            variant_label=a["variant_label"],
            sku=a["sku"],
            todo=a["todo"],
            done=a["done"],
            orders=a["orders"],
        )
        for a in agg
    ]
    rows.sort(key=lambda r: (-r.todo, r.name.lower(), r.variant_label))
    return rows


def unscheduled_open_orders() -> int:
    """Открытые заказы без времени выдачи — в список дня не попали (подсказка владельцу)."""
    return Order.objects.filter(status__in=OPEN_STATUSES, pickup_slot__isnull=True).count()
