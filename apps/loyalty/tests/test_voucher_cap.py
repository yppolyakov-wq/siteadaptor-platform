"""B1.7 (владелец «в») — потолок промокода % от чека: капается ТОЛЬКО
промокод/раздаточный купон; проданный Wertgutschein — никогда."""

import pytest

from apps.loyalty.models import Voucher
from apps.promotions.services import preview_discount, spend_voucher
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _cap(pct):
    return TenantFactory(schema_name="public", slug=f"cap-{pct}", voucher_max_percent=pct)


def test_cap_limits_promo_code():
    _cap(20)
    Voucher.objects.create(code="P50", label="−50 €", discount_cents=5000)
    discount, _v = spend_voucher("P50", 10000)  # чек 100 € → потолок 20 %
    assert discount == 2000


def test_cap_never_touches_gift_balance():
    _cap(10)
    Voucher.objects.create(
        code="GS-C", label="G", discount_cents=5000, balance_cents=5000, max_uses=0
    )
    discount, v = spend_voucher("GS-C", 10000)  # сертификат — без потолка
    assert discount == 5000 and v.balance_cents == 0


def test_cap_zero_means_no_limit_and_preview_matches():
    Voucher.objects.create(code="P99", label="−99 €", discount_cents=9900, max_uses=0)
    voucher = Voucher.objects.get(code="P99")
    assert preview_discount(voucher, 10000) == 9900  # капа нет (настройка 0)
    _cap(25)
    assert preview_discount(voucher, 10000) == 2500  # превью = будущему списанию
    discount, _v = spend_voucher("P99", 10000)
    assert discount == 2500
