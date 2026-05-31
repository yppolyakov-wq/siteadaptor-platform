"""Тесты email-уведомлений по броням (через локальный mail.outbox)."""

import pytest

from apps.promotions.notifications import send_reservation_email
from apps.promotions.services import cancel, confirm, reserve
from apps.promotions.tests.factories import PromotionFactory


def _send(res, event):
    return send_reservation_email(
        dedupe_key=None, schema_name="public", reservation_id=str(res.id), event=event
    )


@pytest.mark.django_db
def test_created_email_to_customer(mailoutbox):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anna", email="anna@test.de", quantity=2)
    out = _send(res, "created")
    assert out["sent"] == 1  # клиенту (владельца-tenant в тестах нет)
    assert len(mailoutbox) == 1
    assert "anna@test.de" in mailoutbox[0].to
    assert res.reference_code in mailoutbox[0].body


@pytest.mark.django_db
def test_no_email_when_customer_has_no_email(mailoutbox):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anon", email="", quantity=1)
    out = _send(res, "created")
    assert out["sent"] == 0
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_confirmed_email(mailoutbox):
    promo = PromotionFactory(available_quantity=5, auto_confirm=False)
    res = reserve(promo, name="Bob", email="bob@test.de")
    confirm(res)
    out = _send(res, "confirmed")
    assert out["sent"] == 1
    assert "bob@test.de" in mailoutbox[-1].to


@pytest.mark.django_db
def test_cancelled_email(mailoutbox):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Cara", email="cara@test.de")
    cancel(res)
    out = _send(res, "cancelled")
    assert out["sent"] == 1
    assert "storniert" in mailoutbox[-1].subject.lower()


@pytest.mark.django_db
def test_missing_reservation_is_safe():
    import uuid

    out = send_reservation_email(
        dedupe_key=None, schema_name="public", reservation_id=str(uuid.uuid4()), event="created"
    )
    assert out == {"skipped": "missing"}
