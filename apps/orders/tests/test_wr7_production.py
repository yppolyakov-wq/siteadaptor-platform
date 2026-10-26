"""KA-12 WR-7 (E3.10): Produktionsliste — Σ штук под выдачи дня."""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders import production, views
from apps.orders.models import Order, OrderItem

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _order(product, qty, *, day, status=Order.STATUS_NEW, variant_label="", hour=9):
    slot = None
    if day is not None:
        slot = timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, 0)))
    from apps.promotions.models import Customer

    customer = Customer.objects.create(name="Kim", email=f"{uuid.uuid4().hex[:8]}@example.com")
    order = Order.objects.create(
        customer=customer,
        reference_code=f"O-{uuid.uuid4().hex[:6].upper()}",
        status=status,
        pickup_slot=slot,
        total=1,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        qty=qty,
        unit_price=Decimal("1.00"),
        variant_label=variant_label,
    )
    return order


def test_sums_per_product_and_variant_for_the_day_only():
    day = timezone.localdate()
    roll = Product.objects.create(name={"de": "Brötchen"}, base_price=Decimal("0.50"))
    cake = Product.objects.create(name={"de": "Torte"}, base_price=Decimal("20"))
    _order(roll, 10, day=day)
    _order(roll, 5, day=day, status=Order.STATUS_CONFIRMED)
    _order(roll, 3, day=day, status=Order.STATUS_READY)
    _order(roll, 99, day=day, status=Order.STATUS_CANCELLED)
    _order(roll, 99, day=day, status=Order.STATUS_PICKED_UP)
    _order(roll, 7, day=day + datetime.timedelta(days=1))
    _order(cake, 1, day=day, variant_label="groß")
    _order(cake, 2, day=day, variant_label="klein")
    rows = {(r.name, r.variant_label): r for r in production.production_list(day)}
    assert set(rows) == {("Brötchen", ""), ("Torte", "groß"), ("Torte", "klein")}
    r = rows[("Brötchen", "")]
    assert (r.todo, r.done, r.orders) == (15, 3, 3)
    assert production.production_list(day)[0].name == "Brötchen"  # больше всего — сверху


def test_late_evening_slot_counts_for_its_local_day():
    day = timezone.localdate()
    roll = Product.objects.create(name={"de": "Brötchen"}, base_price=Decimal("0.50"))
    _order(roll, 4, day=day, hour=23)
    assert production.production_list(day)[0].todo == 4


def test_unscheduled_open_orders_are_counted_not_listed():
    roll = Product.objects.create(name={"de": "Brötchen"}, base_price=Decimal("0.50"))
    _order(roll, 4, day=None)
    _order(roll, 4, day=None, status=Order.STATUS_PICKED_UP)
    assert production.unscheduled_open_orders() == 1
    assert production.production_list(timezone.localdate()) == []


def test_view_renders_and_tolerates_garbage_date():
    roll = Product.objects.create(name={"de": "Brötchen"}, base_price=Decimal("0.50"))
    _order(roll, 6, day=timezone.localdate())
    request = RequestFactory().get("/x/", {"tag": "not-a-date"})
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    request.tenant = None
    html = views.production(request).content.decode()
    assert "data-production-list" in html and "Brötchen" in html
