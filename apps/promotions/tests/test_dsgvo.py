"""Тесты DSGVO-обезличивания контактов (purge_due_customers)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions.models import Customer, Reservation
from apps.promotions.services import cancel, reserve
from apps.promotions.tasks import purge_due_customers
from apps.promotions.tests.factories import PromotionFactory


def _age_reservation(res, days):
    Reservation.objects.filter(pk=res.pk).update(updated_at=timezone.now() - timedelta(days=days))


@pytest.mark.django_db
def test_purge_anonymizes_old_terminal_customer():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anna", email="anna@test.de", phone="0151")
    cancel(res)  # терминальный статус
    _age_reservation(res, 200)

    assert purge_due_customers() == 1
    c = Customer.objects.get(pk=res.customer_id)
    assert c.email == ""
    assert c.phone == ""
    assert c.name == "—"


@pytest.mark.django_db
def test_purge_skips_active_reservation():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Bob", email="bob@test.de")  # pending = активная
    _age_reservation(res, 200)

    assert purge_due_customers() == 0
    assert Customer.objects.get(pk=res.customer_id).email == "bob@test.de"


@pytest.mark.django_db
def test_purge_skips_recent():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Cara", email="cara@test.de")
    cancel(res)  # терминальный, но свежий

    assert purge_due_customers() == 0
    assert Customer.objects.get(pk=res.customer_id).email == "cara@test.de"


@pytest.mark.django_db
def test_purge_is_idempotent():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Dan", email="dan@test.de")
    cancel(res)
    _age_reservation(res, 200)

    assert purge_due_customers() == 1
    assert purge_due_customers() == 0  # повторно уже обезличенного не трогаем
