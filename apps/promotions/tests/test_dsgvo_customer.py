"""Hardening H7: команда dsgvo_customer (экспорт / удаление PII по запросу)."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.notifications.models import Notification
from apps.promotions.models import Customer, Reservation, WaitlistEntry
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

EMAIL = "kunde@test.de"


def _tenant():
    # тестовые настройки держат все приложения SHARED — данные живут в public
    return TenantFactory(schema_name="public")


def _customer_with_history(status="fulfilled"):
    promo = PromotionFactory(status="active", available_quantity=10, auto_confirm=True)
    res = reserve(promo, name="Kunde K", email=EMAIL, phone="+49 1", quantity=1)
    Reservation.objects.filter(pk=res.pk).update(status=status, note="ohne Zwiebeln")
    WaitlistEntry.objects.create(promotion=promo, email=EMAIL, name="Kunde K")
    Notification.objects.create(type="reservation", recipient=EMAIL, dedupe_key="t1")
    return Customer.objects.get(email=EMAIL)


def _run(*, delete=False, email=EMAIL, schema="public"):
    out = StringIO()
    args = ["--schema", schema, "--email", email] + (["--delete"] if delete else [])
    call_command("dsgvo_customer", *args, stdout=out)
    return out.getvalue()


def test_export_contains_all_customer_data():
    _tenant()
    _customer_with_history()
    payload = json.loads(_run())
    assert payload["email"] == EMAIL
    assert payload["customers"][0]["name"] == "Kunde K"
    assert payload["customers"][0]["phone"] == "+49 1"
    assert payload["reservations"][0]["note"] == "ohne Zwiebeln"
    assert payload["waitlist"][0]["name"] == "Kunde K"
    # точное число зависит от хуков брони — важно, что лог уведомлений попал
    assert len(payload["notifications"]) >= 1


def test_delete_erases_pii_everywhere():
    _tenant()
    customer = _customer_with_history()
    notifications_before = Notification.objects.count()
    _run(delete=True)

    customer.refresh_from_db()
    assert customer.email == ""
    assert customer.phone == ""
    assert customer.name != "Kunde K"
    assert not WaitlistEntry.objects.filter(email__iexact=EMAIL).exists()
    assert not Reservation.objects.exclude(note="").exists()
    assert not Notification.objects.filter(recipient__iexact=EMAIL).exists()
    # сами записи статистики остаются — стираем PII, не историю
    assert Reservation.objects.count() == 1
    assert Notification.objects.count() == notifications_before


def test_delete_refused_with_active_reservation():
    _tenant()
    customer = _customer_with_history(status="confirmed")
    with pytest.raises(CommandError, match="активных броней"):
        _run(delete=True)
    customer.refresh_from_db()
    assert customer.email == EMAIL  # ничего не стёрто


def test_unknown_email_rejected():
    _tenant()
    with pytest.raises(CommandError, match="не найдено"):
        _run(email="niemand@test.de")


def test_unknown_schema_rejected():
    _tenant()
    with pytest.raises(CommandError, match="не найдена"):
        _run(schema="ghost")


def test_waitlist_only_email_is_found_and_erased():
    """Email может быть только в waitlist (брони не было) — тоже подлежит удалению."""
    _tenant()
    promo = PromotionFactory(status="active", available_quantity=0)
    WaitlistEntry.objects.create(promotion=promo, email="nur-warte@test.de")
    _run(delete=True, email="nur-warte@test.de")
    assert not WaitlistEntry.objects.filter(email="nur-warte@test.de").exists()
