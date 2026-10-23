"""KA-12 E2.7: время самовывоза у покупки по акции и принятия предложения."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.orders import pickup_slots
from apps.orders.models import Order
from apps.promotions import public_views as promo_views
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALL_DAY = {str(d): ["00:00", "23:59"] for d in range(7)}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slots=True, capacity=0):
    cfg = {"pickup_slots": {"step": 30, "capacity": capacity, "lead": 0, "days": 2}}
    return TenantFactory.build(
        business_type="bakery",
        opening_hours_structured=ALL_DAY,
        site_config=cfg if slots else {},
    )


def _promo(quantity=5):
    promo = PromotionFactory(product=None, available_quantity=quantity, price_override=Decimal("4"))
    Promotion.objects.filter(pk=promo.pk).update(status="active")
    promo.refresh_from_db()
    return promo


def _buy(promo, tenant, **extra):
    data = {
        "name": "Anna",
        "email": f"a{uuid.uuid4().hex[:6]}@example.com",
        "quantity": "1",
        "form_token": uuid.uuid4().hex,
        **extra,
    }
    req = RequestFactory().post(f"/p/{promo.pk}/kaufen/", data)
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.1.9"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return promo_views.promotion_purchase(req, pk=promo.pk)


def test_promo_purchase_without_slot_is_refused_and_limit_untouched():
    t, promo = _tenant(), _promo()
    resp = _buy(promo, t)
    assert resp.status_code == 200 and not Order.objects.exists()
    promo.refresh_from_db()
    assert promo.available_quantity == 5


def test_promo_purchase_stores_the_chosen_slot():
    t, promo = _tenant(), _promo()
    slot = pickup_slots.slots_for(t)[0][1][0][0]
    resp = _buy(promo, t, pickup_slot=slot.isoformat())
    assert resp.status_code == 302
    assert Order.objects.get().pickup_slot == slot


def test_full_slot_rolls_back_the_campaign_limit():
    t, promo = _tenant(capacity=1), _promo()
    slot = pickup_slots.slots_for(t)[0][1][0][0]
    assert _buy(promo, t, pickup_slot=slot.isoformat()).status_code == 302
    # тот же слот уже занят (ёмкость 1) → validate не пропустит; гонку закрывает claim
    resp = _buy(promo, t, pickup_slot=slot.isoformat())
    assert resp.status_code == 200 and Order.objects.count() == 1
    promo.refresh_from_db()
    assert promo.available_quantity == 4


def test_without_slots_promo_purchase_is_unchanged():
    t, promo = _tenant(slots=False), _promo()
    assert _buy(promo, t).status_code == 302
    assert Order.objects.get().pickup_slot is None


def test_promo_detail_shows_the_slot_field_only_when_enabled():
    promo = _promo()
    for slots, expected in ((True, True), (False, False)):
        req = RequestFactory().get(f"/p/{promo.pk}/")
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.tenant = _tenant(slots=slots)
        ctx = promo_views._pickup_ctx(req)
        assert bool(ctx.get("pickup_slot_enabled")) is expected
