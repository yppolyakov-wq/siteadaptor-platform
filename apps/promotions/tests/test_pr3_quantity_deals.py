"""KA-12 PR-3: количественные акции реально считаются в корзине и заказе одной функцией.

Цена штуки на витрине остаётся обычной (В2 — замки в test_price_condition_promo), выгода
появляется на строке корзины и в заказе (подстроки со снимком list_price/акции)."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.orders import services as order_services
from apps.promotions import quantity_deals as qd
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.mark.parametrize(
    "cond,pct,qty,expected",
    [
        # 2. Stück −50 %: 3 штуки → 2 по 9,00 + 1 по 4,50
        ({"kind": "nth", "n": 2}, 50, 3, [(2, D("9.00"), False), (1, D("4.50"), True)]),
        ({"kind": "nth", "n": 2}, 50, 1, [(1, D("9.00"), False)]),
        # 3 für 2: 7 штук → 2 бесплатно
        (
            {"kind": "x_for_y", "n": 3, "pay": 2},
            None,
            7,
            [(5, D("9.00"), False), (2, D("0.00"), True)],
        ),
        # ab 3 Stück −20 %: 3 штуки все по 7,20; 2 штуки — без скидки
        ({"kind": "min_qty", "n": 3}, 20, 3, [(3, D("7.20"), True)]),
        ({"kind": "min_qty", "n": 3}, 20, 2, [(2, D("9.00"), False)]),
        # без процента / «своё условие» — денег нет
        ({"kind": "nth", "n": 2}, None, 4, [(4, D("9.00"), False)]),
        ({"kind": "other", "note": {"de": "Happy Hour"}}, None, 4, [(4, D("9.00"), False)]),
    ],
)
def test_split_units(cond, pct, qty, expected):
    assert qd.split_units(cond, pct, D("9.00"), qty) == expected


def _product(price="9.00", **kw):
    from apps.catalog.models import Product

    return Product.objects.create(name={"de": "Pizza"}, base_price=D(price), **kw)


def _promo(product, cond, pct=None, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    return Promotion.objects.create(
        product=product,
        title={"de": "Aktion"},
        discount_percent=pct,
        metadata={"price_condition": cond},
        **kw,
    )


def test_order_charges_quantity_deal_with_snapshots():
    p = _product(stock_quantity=10)
    promo = _promo(p, {"kind": "x_for_y", "n": 3, "pay": 2}, available_quantity=5)
    order = order_services.create_order(items=[(p, 3)], name="K")
    assert order.total == D("18.00")  # 3 für 2: 2 × 9,00
    items = list(order.items.order_by("unit_price"))
    assert [(i.qty, i.unit_price) for i in items] == [(1, D("0.00")), (2, D("9.00"))]
    free = items[0]
    assert free.promotion == promo and free.list_price == D("9.00")
    assert {"promo": str(promo.pk), "label": "Aktion"} in free.modifiers
    p.refresh_from_db()
    assert p.stock_quantity == 7  # склад — по всем 3 штукам
    promo.refresh_from_db()
    assert promo.available_quantity == 4  # лимит — скидочными штуками


def test_price_promo_beats_condition_and_no_stacking():
    p = _product()
    _promo(p, {"kind": "nth", "n": 2}, pct=50)
    Promotion.objects.create(
        product=p,
        title={"de": "Preis"},
        status="active",
        starts_at=timezone.now(),
        price_override=D("8.00"),
    )
    order = order_services.create_order(items=[(p, 2)], name="K")
    assert order.total == D("16.00")  # только новая цена, без «2. Stück −50 %» сверху


def test_cart_total_equals_order_total():
    from apps.orders import public_views

    p = _product()
    _promo(p, {"kind": "nth", "n": 2}, pct=50)
    deals = public_views._cart_deals([(p, None, [], 4)])
    total, deal = public_views._line_total(p, None, [], 4, {}, deals)
    assert total == D("27.00") and deal[1] == D("9.00")
    order = order_services.create_order(items=[(p, 4)], name="K")
    assert order.total == total


def test_variant_with_own_price_gets_no_deal():
    from apps.catalog.models import ProductVariant

    p = _product()
    v = ProductVariant.objects.create(product=p, label="groß", price=D("12.00"))
    _promo(p, {"kind": "nth", "n": 2}, pct=50)
    order = order_services.create_order(items=[(p, v, 2)], name="K")
    assert order.total == D("24.00")


def test_inactive_or_mystery_condition_not_applied():
    p = _product()
    _promo(p, {"kind": "nth", "n": 2}, pct=50, status="draft")
    _promo(p, {"kind": "nth", "n": 2}, pct=50, discount_style="mystery")
    order = order_services.create_order(items=[(p, 2)], name="K")
    assert order.total == D("18.00")


def test_limit_caps_discounted_units_instead_of_failing():
    """Ревью PR-3: лимит 1, «2. Stück −50 %», 4 штуки → скидка на 1 штуку, а не отказ."""
    p = _product()
    promo = _promo(p, {"kind": "nth", "n": 2}, pct=50, available_quantity=1)
    order = order_services.create_order(items=[(p, 4)], name="K")
    assert order.total == D("31.50")  # 3 × 9,00 + 1 × 4,50
    promo.refresh_from_db()
    assert promo.available_quantity == 0
    assert qd.split_units({"kind": "min_qty", "n": 2}, 20, D("10.00"), 3, cap=2) == [
        (1, D("10.00"), False),
        (2, D("8.00"), True),
    ]


def test_staff_cannot_change_qty_of_deal_line():
    from apps.orders import editing

    p = _product()
    _promo(p, {"kind": "x_for_y", "n": 3, "pay": 2})
    order = order_services.create_order(items=[(p, 3)], name="K")
    free = order.items.get(unit_price=D("0.00"))
    with pytest.raises(editing.OrderLocked):
        editing.set_item_qty(order, free.pk, 5)
