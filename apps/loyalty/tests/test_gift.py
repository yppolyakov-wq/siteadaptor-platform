"""G1: подарочные сертификаты — покупка, выпуск Voucher после оплаты, погашение."""

import pytest

from apps.loyalty import gift
from apps.loyalty.models import GiftVoucher, Voucher

pytestmark = pytest.mark.django_db


def test_create_validates_amount_and_contacts():
    with pytest.raises(ValueError):
        gift.create_gift_voucher(buyer_name="", buyer_email="a@b.de", amount_cents=10000)
    with pytest.raises(ValueError):
        gift.create_gift_voucher(buyer_name="A", buyer_email="a@b.de", amount_cents=500)  # < 10 €
    with pytest.raises(ValueError):
        gift.create_gift_voucher(
            buyer_name="A", buyer_email="a@b.de", amount_cents=300000
        )  # > 2000
    gv = gift.create_gift_voucher(buyer_name="A", buyer_email="a@b.de", amount_cents=10000)
    assert gv.payment_state == GiftVoucher.PAYMENT_PENDING and gv.voucher_id is None


def test_paid_issues_voucher_and_is_idempotent():
    gv = gift.create_gift_voucher(buyer_name="A", buyer_email="a@b.de", amount_cents=10000)
    assert gift.mark_gift_voucher_paid(tenant_schema="public", gift_id=gv.id, payment_intent="pi_1")
    gv.refresh_from_db()
    assert gv.payment_state == "paid"
    assert gv.voucher is not None
    code = gv.voucher.code
    v = gv.voucher
    # B1.5 (владелец «а»): Wertgutschein с остатком — многораз до исчерпания.
    assert v.discount_cents == 10000 and v.max_uses == 0 and v.code.startswith("GS-")
    assert v.balance_cents == 10000
    # повторный вызог вебхука — не выпускает второй код
    gift.mark_gift_voucher_paid(tenant_schema="public", gift_id=gv.id, payment_intent="pi_1")
    gv.refresh_from_db()
    assert gv.voucher.code == code
    assert Voucher.objects.filter(code__startswith="GS-").count() == 1


def test_issued_voucher_redeems_like_promo():
    # выпущенный гутшайн гасится механикой H4a (discount_for на сумму брони)
    gv = gift.create_gift_voucher(buyer_name="A", buyer_email="a@b.de", amount_cents=5000)
    gift.mark_gift_voucher_paid(tenant_schema="public", gift_id=gv.id)
    gv.refresh_from_db()
    v = gv.voucher
    assert v.is_redeemable
    assert v.discount_for(20000) == 5000  # фикс-скидка 50 € на бронь 200 €


def test_paid_unknown_record_returns_false():
    import uuid

    assert gift.mark_gift_voucher_paid(tenant_schema="public", gift_id=uuid.uuid4()) is False
