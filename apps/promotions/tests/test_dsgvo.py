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
    from datetime import date

    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anna", email="anna@test.de", phone="0151")
    # PMS-B2: дата рождения — PII, обезличивание её тоже чистит.
    Customer.objects.filter(pk=res.customer_id).update(birthday=date(1990, 5, 1))
    cancel(res)  # терминальный статус
    _age_reservation(res, 200)

    assert purge_due_customers() == 1
    c = Customer.objects.get(pk=res.customer_id)
    assert c.email == ""
    assert c.phone == ""
    assert c.name == "—"
    assert c.birthday is None


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


@pytest.mark.django_db
def test_purge_covers_stays_only_guests():
    """PMS-аудит 2026-07-27: отельные гости (только StayBooking, без Reservation)
    раньше НЕ попадали под DSGVO-обезличивание вовсе."""
    from datetime import date, timedelta

    from django.utils import timezone

    from apps.promotions.models import Customer
    from apps.promotions.tasks import purge_due_customers
    from apps.stays import services as stay_services
    from apps.stays.models import StayBooking, StayUnit

    unit = StayUnit.objects.create(name="Zi Purge", price_cents=8000)
    old = stay_services.book_stay(
        unit,
        arrival=date(2026, 9, 1),
        departure=date(2026, 9, 3),
        name="Alt Gast",
        email="alt@test.de",
    )
    old.status = StayBooking.STATUS_FULFILLED
    old.save(update_fields=["status"])
    # давность больше retention: подвинем updated_at брони в прошлое
    StayBooking.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=4000))
    fresh = stay_services.book_stay(
        unit,
        arrival=date(2026, 10, 1),
        departure=date(2026, 10, 3),
        name="Aktiv Gast",
        email="aktiv@test.de",
    )
    assert purge_due_customers() >= 1
    old_customer = Customer.objects.get(pk=old.customer_id)
    assert old_customer.email == "" and old_customer.name != "Alt Gast"  # обезличен
    active_customer = Customer.objects.get(pk=fresh.customer_id)
    assert active_customer.email == "aktiv@test.de"  # активный гость не тронут
