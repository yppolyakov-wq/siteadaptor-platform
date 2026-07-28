"""PMS-B (остаток): авто-тег «stammkunde» по ≥3 покупкам (RevenueEntry)."""

from decimal import Decimal

import pytest

from apps.finance.models import RevenueEntry
from apps.promotions.models import Customer
from apps.promotions.tasks import tag_regular_customers

pytestmark = pytest.mark.django_db


def _entries(customer, n):
    for _ in range(n):
        RevenueEntry.objects.create(amount=Decimal("10.00"), customer=customer)


def test_tags_regulars_and_keeps_manual_tags():
    stamm = Customer.objects.create(name="Anna Stamm", tags=["vip"])
    selten = Customer.objects.create(name="Berta Selten")
    _entries(stamm, 3)
    _entries(selten, 2)

    assert tag_regular_customers() == 1
    stamm.refresh_from_db()
    selten.refresh_from_db()
    assert stamm.tags == ["vip", "stammkunde"]  # ручной тег цел, авто добавлен
    assert selten.tags == []  # ниже порога — не трогаем


def test_idempotent_no_duplicates():
    customer = Customer.objects.create(name="Carla Treu")
    _entries(customer, 4)
    assert tag_regular_customers() == 1
    assert tag_regular_customers() == 0  # второй прогон ничего не меняет
    customer.refresh_from_db()
    assert customer.tags.count("stammkunde") == 1
