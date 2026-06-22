"""A4: промокод на онлайн-заказе — структурная скидка на Voucher."""

import pytest

from apps.loyalty.models import Voucher
from apps.promotions import services
from apps.promotions.forms import VoucherCreateForm

pytestmark = pytest.mark.django_db


def test_discount_for_percent():
    v = Voucher.objects.create(code="P10", label="−10 %", discount_percent=10)
    assert v.discount_for(2000) == 200  # 10 % от 20,00 €


def test_discount_for_fixed_capped_at_subtotal():
    v = Voucher.objects.create(code="E5", label="−5 €", discount_cents=500)
    assert v.discount_for(2000) == 500
    assert v.discount_for(300) == 300  # не уходит ниже нуля (капается суммой)


def test_discount_respects_min_order():
    v = Voucher.objects.create(code="MIN", label="x", discount_percent=10, min_order_cents=1500)
    assert v.discount_for(1000) == 0  # ниже минимума
    assert v.discount_for(2000) == 200


def test_no_discount_when_not_redeemable_or_no_discount():
    plain = Voucher.objects.create(code="PLAIN", label="Gratis Kaffee")  # без скидки
    assert plain.has_order_discount is False
    assert plain.discount_for(5000) == 0
    inactive = Voucher.objects.create(code="OFF", label="x", discount_percent=10, is_active=False)
    assert inactive.discount_for(5000) == 0


def test_generate_vouchers_with_discount():
    [v] = services.generate_vouchers(label="−15 %", discount_percent=15, min_order_cents=1000)
    assert v.discount_percent == 15 and v.min_order_cents == 1000


def test_form_rejects_both_percent_and_euro():
    form = VoucherCreateForm(
        {"label": "x", "count": 1, "max_uses": 1, "discount_percent": 10, "discount_eur": "5"}
    )
    assert not form.is_valid()
