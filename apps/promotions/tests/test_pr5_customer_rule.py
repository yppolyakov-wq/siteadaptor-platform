"""KA-12 PR-5: «nur für Neukunden» / «einmal pro Kunde» — проверка в create_order."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.promotions.eligibility import PromoNotEligible
from apps.promotions.models import Promotion

pytestmark = pytest.mark.django_db


def _setup(rule, limit=None):
    p = Product.objects.create(name={"de": "Brot"}, base_price=Decimal("4.00"))
    promo = Promotion.objects.create(
        title={"de": "Willkommen"},
        product=p,
        status="active",
        starts_at=timezone.now(),
        discount_percent=50,
        available_quantity=limit,
        metadata={"customer_rule": rule},
    )
    return p, promo


def test_new_customer_rule():
    p, promo = _setup("new", limit=10)
    order = order_services.create_order(items=[(p, 1)], name="A", email="a@x.de")
    assert order.total == Decimal("2.00")
    with pytest.raises(PromoNotEligible):
        order_services.create_order(items=[(p, 1)], name="A", email="A@x.de")
    promo.refresh_from_db()
    assert promo.available_quantity == 9  # отказ не съел лимит


def test_once_per_customer_and_cancelled_order_does_not_count():
    p, promo = _setup("once")
    first = order_services.create_order(items=[(p, 1)], name="B", email="b@x.de")
    with pytest.raises(PromoNotEligible):
        order_services.create_order(items=[(p, 1)], name="B", email="b@x.de")
    Order.objects.filter(pk=first.pk).update(status="cancelled")
    again = order_services.create_order(items=[(p, 1)], name="B", email="b@x.de")
    assert again.total == Decimal("2.00")


def test_no_rule_no_check():
    p, _ = _setup("")
    order_services.create_order(items=[(p, 1)], name="C", email="c@x.de")
    order_services.create_order(items=[(p, 1)], name="C", email="c@x.de")


def test_direct_purchase_respects_rule():
    from apps.promotions import services

    p, promo = _setup("new", limit=5)
    order_services.create_order(items=[(p, 1)], name="D", email="d@x.de")
    with pytest.raises(PromoNotEligible):
        services.purchase(promo, quantity=1, name="D", email="d@x.de")
    promo.refresh_from_db()
    assert promo.available_quantity == 4  # отказ до списания лимита


def test_phone_written_differently_is_same_customer():
    p, _ = _setup("new")
    order_services.create_order(items=[(p, 1)], name="E", phone="0171 1234567")
    with pytest.raises(PromoNotEligible):
        order_services.create_order(items=[(p, 1)], name="E", phone="+49 171 1234567")


def test_form_rejects_rule_on_service_and_off_above_price():
    from apps.booking.models import Service
    from apps.promotions.forms import PromotionForm

    svc = Service.objects.create(name="Schnitt", duration_minutes=30, price_cents=3000)
    p, _ = _setup("")
    base = {
        "title_de": "X",
        "promo_type": "discount",
        "starts_at": "2030-01-01T10:00",
        "ends_at": "2030-01-08T10:00",
        "discount_style": "",
        "recurrence": "",
    }
    form = PromotionForm(
        data={**base, "service": svc.pk, "customer_rule": "new", "discount_percent": 10}
    )
    assert not form.is_valid() and "customer_rule" in form.errors
    form = PromotionForm(data={**base, "product": p.pk, "discount_off": "4,00"})
    assert not form.is_valid() and "discount_off" in form.errors
