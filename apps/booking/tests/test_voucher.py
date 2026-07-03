"""B1.2 — booking принимает промокод/Geschenkgutschein: скидка+снимок,
атомарное гашение (double-redeem), невалидный код, паритет «без кода»."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Resource
from apps.loyalty.models import Voucher

pytestmark = pytest.mark.django_db


def _resource(**kw):
    kw.setdefault("name", "Stuhl")
    return Resource.objects.create(**kw)


def _book(resource, code="", price_cents=5000, **kw):
    start = timezone.now() + timedelta(days=1)
    return services.book(
        resource,
        start=start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=kw.pop("h", 0)),
        end=start.replace(minute=0, second=0, microsecond=0)
        + timedelta(hours=kw.pop("h2", 0), minutes=30),
        name="Kunde",
        email="k@test.de",
        price_cents=price_cents,
        voucher_code=code,
        **kw,
    )


def test_gift_voucher_discounts_and_snapshots():
    Voucher.objects.create(code="GS-100", label="Gutschein", discount_cents=10000, max_uses=1)
    booking = _book(_resource(), code="gs-100", price_cents=4000)  # регистр нормализуется
    assert booking.voucher_code == "GS-100"
    assert booking.discount_cents == 4000  # капается суммой брони
    assert booking.total_cents == 0
    v = Voucher.objects.get(code="GS-100")
    assert v.used_count == 1


def test_voucher_double_redeem_blocked():
    Voucher.objects.create(code="EIN", label="1×", discount_cents=500, max_uses=1)
    _book(_resource(), code="EIN", h=1, h2=1)
    with pytest.raises(services.PromoInvalid):
        _book(_resource(name="Stuhl 2"), code="EIN", h=3, h2=3)


def test_invalid_or_min_order_code_rejected():
    with pytest.raises(services.PromoInvalid):
        _book(_resource(), code="GIBTSNICHT")
    Voucher.objects.create(code="MIN", label="min", discount_cents=500, min_order_cents=99900)
    with pytest.raises(services.PromoInvalid):
        _book(_resource(name="R2"), code="MIN", h=2, h2=2)


def test_no_code_keeps_legacy_totals():
    booking = _book(_resource(), price_cents=4000)
    assert booking.voucher_code == "" and booking.discount_cents == 0
    assert booking.total_cents == 4000
