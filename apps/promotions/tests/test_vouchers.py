"""Тесты ваучеров (генерация + погашение)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions.models import Voucher
from apps.promotions.services import VoucherError, generate_vouchers, redeem_voucher


@pytest.mark.django_db
def test_generate_unique_codes():
    vouchers = generate_vouchers(label="−10 %", count=5, max_uses=1)
    codes = {v.code for v in vouchers}
    assert len(codes) == 5
    assert all(c.startswith("V-") for c in codes)


@pytest.mark.django_db
def test_redeem_single_use():
    v = generate_vouchers(label="Gratis", count=1, max_uses=1)[0]
    redeemed = redeem_voucher(v.code.lower())  # регистронезависимо
    assert redeemed.used_count == 1
    with pytest.raises(VoucherError) as exc:
        redeem_voucher(v.code)
    assert exc.value.reason == "used_up"


@pytest.mark.django_db
def test_redeem_unknown():
    with pytest.raises(VoucherError) as exc:
        redeem_voucher("V-NOPE00")
    assert exc.value.reason == "not_found"


@pytest.mark.django_db
def test_redeem_expired():
    v = Voucher.objects.create(
        code="V-EXP001", label="x", max_uses=1, expires_at=timezone.now() - timedelta(days=1)
    )
    with pytest.raises(VoucherError) as exc:
        redeem_voucher(v.code)
    assert exc.value.reason == "expired"


@pytest.mark.django_db
def test_unlimited_voucher():
    v = generate_vouchers(label="∞", count=1, max_uses=0)[0]
    for _ in range(3):
        redeem_voucher(v.code)
    v.refresh_from_db()
    assert v.used_count == 3
    assert v.is_redeemable is True
