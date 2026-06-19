"""CA4: действия в ЛК — повтор заказа + отмена брони."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.account import auth, views
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views as orders_public
from apps.orders.services import create_order
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/konto/", customer=None):
    request = RequestFactory().post(path)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.5"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="restaurant")
    if customer is not None:
        request.session[auth.SESSION_KEY] = str(customer.pk)
    return request


def test_reorder_refills_cart_from_order():
    product = ProductFactory(base_price=Decimal("8.00"))
    order = create_order(items=[(product, 2)], name="Max", email="max@test.de")
    req = _req()
    resp = orders_public.reorder(req, code=order.reference_code)
    assert resp.status_code == 302
    cart = req.session[orders_public.CART_SESSION_KEY]
    assert cart.get(f"{product.pk}:") == 2


def test_cancel_booking_sets_cancelled():
    from django.utils import timezone

    from apps.booking.models import Booking, Resource
    from apps.booking.services import book

    customer = Customer.objects.create(name="Max", email="max@test.de")
    res = Resource.objects.create(name="Tisch 1", capacity=1)
    start = timezone.now() + timezone.timedelta(days=1)
    booking = book(
        resource=res,
        start=start,
        end=start + timezone.timedelta(hours=1),
        name="Max",
        email="max@test.de",
    )
    # бронь привязана к тому же Customer (reuse по email)
    booking.customer = customer
    booking.save(update_fields=["customer"])
    resp = views.cancel_booking(_req(customer=customer), code=booking.reference_code)
    assert resp.status_code == 302
    booking.refresh_from_db()
    assert booking.status == Booking.STATUS_CANCELLED
