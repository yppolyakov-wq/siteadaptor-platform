"""KA-12 О-3: в Betriebsferien заказ «как можно скорее», «Kaufen» и «Zurücklegen» по акции
закрыты (выдать некому); заказ на время из сетки и купон — работают."""

import uuid
from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.core.tests.test_closures import _close
from apps.orders import public_views as order_views
from apps.orders.models import Order
from apps.orders.tests.test_delivery import _pub_req
from apps.promotions import public_views as promo_views
from apps.promotions.models import Promotion, Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.promotions.tests.test_zuruecklegen import _request
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(schema_name="public")


def _promo():
    return PromotionFactory(status="active", available_quantity=5, promo_type=Promotion.DISCOUNT)


def _form():
    return {
        "name": "Anna",
        "email": "a@example.de",
        "quantity": "1",
        "form_token": uuid.uuid4().hex,
    }


def test_checkout_without_slot_is_refused_during_holidays():
    product = ProductFactory(base_price=Decimal("10.00"))
    tenant = TenantFactory.build(schema_name="public")
    _close()
    resp = order_views.checkout(
        _pub_req({"name": "K"}, tenant=tenant, session={"cart": {str(product.pk): 1}})
    )
    assert resp.status_code == 302 and "warenkorb" in resp.url
    assert not Order.objects.exists()


def test_checkout_works_when_open():
    product = ProductFactory(base_price=Decimal("10.00"))
    tenant = TenantFactory.build(schema_name="public")
    order_views.checkout(
        _pub_req({"name": "K"}, tenant=tenant, session={"cart": {str(product.pk): 1}})
    )
    assert Order.objects.count() == 1


def test_promo_purchase_refused_during_holidays():
    tenant, promo = _tenant(), _promo()
    _close()
    resp = promo_views.promotion_purchase(
        _request("post", f"/p/{promo.pk}/kaufen/", tenant, _form()), pk=promo.pk
    )
    assert resp.status_code == 302 and resp.url == f"/p/{promo.pk}/"
    assert not Order.objects.exists()


def test_promo_reserve_refused_during_holidays():
    tenant, promo = _tenant(), _promo()
    _close()
    resp = promo_views.reservation_create(
        _request("post", f"/p/{promo.pk}/reserve/", tenant, _form()), pk=promo.pk
    )
    assert resp.status_code == 302
    assert not Reservation.objects.exists()


def test_future_closure_does_not_block_today():
    from apps.core import closures

    tenant = _tenant()
    _close(days=2, offset=3)
    assert closures.closed_now_message(tenant) is None
    fresh = type(tenant).objects.get(pk=tenant.pk)  # окно закрытий — одно на запрос
    _close(days=1)
    assert "Betriebsferien" in closures.closed_now_message(fresh)
