"""Решение владельца 2026-10-30: скидки по умолчанию НЕ суммируются.

Промокод без `combinable` уменьшает только позиции без другой скидки (акция,
количественная акция, промо-цена брони, авто-скидка номера). С флагом — всю сумму.
Сертификат с остатком — оплата, на него правило не действует.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.loyalty.models import Voucher
from apps.orders import services as order_services
from apps.promotions.models import Promotion
from apps.promotions.services import (
    VoucherError,
    eligible_base,
    generate_vouchers,
    preview_discount,
    spend_voucher,
)

pytestmark = pytest.mark.django_db


def _code(code, combinable=False, **kw):
    kw.setdefault("discount_percent", 10)
    kw.setdefault("max_uses", 0)
    return Voucher.objects.create(code=code, label="−10 %", combinable=combinable, **kw)


def test_default_is_not_combinable():
    assert Voucher._meta.get_field("combinable").default is False
    assert generate_vouchers(label="x", discount_percent=10)[0].combinable is False


def test_code_only_counts_the_undiscounted_part():
    _code("NC10")
    discount, _v = spend_voucher("NC10", 10000, discounted_cents=6000)
    assert discount == 400  # 10 % от 40 €, акционные 60 € не тронуты


def test_combinable_code_counts_the_whole_sum():
    _code("C10", combinable=True)
    discount, _v = spend_voucher("C10", 10000, discounted_cents=6000)
    assert discount == 1000


def test_all_items_discounted_rejects_code_and_does_not_burn_it():
    voucher = _code("NC1", max_uses=1)
    with pytest.raises(VoucherError, match="not_combinable"):
        spend_voucher("NC1", 5000, discounted_cents=5000)
    voucher.refresh_from_db()
    assert voucher.used_count == 0


def test_gift_balance_is_payment_and_always_applies():
    gift = Voucher.objects.create(
        code="GS-1", label="G", balance_cents=3000, max_uses=0, discount_cents=3000
    )
    assert eligible_base(gift, 5000, 5000) == 5000
    discount, _v = spend_voucher("GS-1", 5000, discounted_cents=5000)
    assert discount == 3000


def test_preview_matches_spend():
    voucher = _code("PV10")
    assert preview_discount(voucher, 10000, 6000) == 400


def test_order_checkout_skips_promotion_lines():
    saft = Product.objects.create(name={"de": "Saft"}, base_price="10.00")
    brot = Product.objects.create(name={"de": "Brot"}, base_price="20.00")
    Promotion.objects.create(
        title={"de": "SaftDeal"},
        status="active",
        product=saft,
        price_override=Decimal("8.00"),
        compare_at_price=saft.base_price,
    )
    _code("SHOP10")
    order = order_services.create_order(
        items=[(saft, 1), (brot, 1)], name="K", voucher_code="SHOP10"
    )
    assert order.discount_cents == 200  # 10 % только от Brot
    assert order.total == Decimal("26.00")  # 8 + 20 − 2


def test_order_checkout_combinable_discounts_everything():
    saft = Product.objects.create(name={"de": "Saft"}, base_price="10.00")
    Promotion.objects.create(
        title={"de": "SaftDeal"},
        status="active",
        product=saft,
        price_override=Decimal("8.00"),
        compare_at_price=saft.base_price,
    )
    _code("ALL10", combinable=True)
    order = order_services.create_order(items=[(saft, 1)], name="K", voucher_code="ALL10")
    assert order.discount_cents == 80


def test_cart_preview_matches_order_on_quantity_deal():
    """Ревью: «2. Stück −50 %» — по полной цене остаётся первая штука, она база кода и
    в корзине, и в заказе (раньше корзина считала скидочной всю строку → «0», а заказ
    давал скидку)."""
    from django.utils import timezone

    from apps.orders import public_views

    pizza = Product.objects.create(name={"de": "Pizza"}, base_price=Decimal("10.00"))
    Promotion.objects.create(
        product=pizza,
        title={"de": "Aktion"},
        status="active",
        starts_at=timezone.now(),
        discount_percent=50,
        metadata={"price_condition": {"kind": "nth", "n": 2}},
    )
    voucher = _code("NTH10")
    deals = public_views._cart_deals([(pizza, None, [], 2)])
    total, deal = public_views._line_total(pizza, None, [], 2, {}, deals)
    assert total == Decimal("15.00") and deal[2] == Decimal("5.00")
    preview = preview_discount(voucher, int(total * 100), int(deal[2] * 100))
    order = order_services.create_order(items=[(pizza, 2)], name="K", voucher_code="NTH10")
    assert preview == order.discount_cents == 100  # 10 % от 10 € полной цены
