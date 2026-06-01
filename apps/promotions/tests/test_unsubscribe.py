"""Тесты быстрой отписки от писем."""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Customer
from apps.promotions.notifications import send_reservation_email
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory


@pytest.mark.django_db
def test_unsubscribed_customer_gets_no_email(mailoutbox):
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Anna", email="anna@test.de")
    res.customer.unsubscribed = True
    res.customer.save(update_fields=["unsubscribed"])

    out = send_reservation_email(
        dedupe_key=None, schema_name="public", reservation_id=str(res.id), event="created"
    )
    assert out["sent"] == 0
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_unsubscribe_view_sets_flag():
    promo = PromotionFactory(available_quantity=5)
    res = reserve(promo, name="Bob", email="bob@test.de")
    token = res.customer.unsubscribe_token

    resp = public_views.unsubscribe(RequestFactory().get(f"/u/{token}/"), token=token)
    assert resp.status_code == 200
    assert Customer.objects.get(pk=res.customer_id).unsubscribed is True


@pytest.mark.django_db
def test_unsubscribe_unknown_token_is_safe():
    import uuid

    resp = public_views.unsubscribe(RequestFactory().get("/u/x/"), token=uuid.uuid4())
    assert resp.status_code == 200
