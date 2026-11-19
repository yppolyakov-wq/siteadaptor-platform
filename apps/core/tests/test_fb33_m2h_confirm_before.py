"""FB-33 M2h (ревью): подтверждения без своих настроек — байт-в-байт как до M2h.

Снимки сняты шаблонами `origin/main` ДО тегов `confirmation_lead`/`confirmation_after`
(заказ, запись по времени, резерв акции). Обновить (осознанно):
FB33M2H_GOLDEN=update uv run pytest <этот файл>
"""

from datetime import time
from decimal import Decimal

import pytest

from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.core.tests.test_fb33_m2h_before import _check
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
frozen_now = _p5.frozen_now


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory.build(
        name="Laden X", schema_name="laden_x", business_type="cafe", disabled_modules=[]
    )


def _snap(html, code):
    assert code, "у сделки нет кода — снимок был бы мусором"
    return _p5._normalize(html.replace(code, "CODE"))


def test_order_confirmation_before():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views, services
    from apps.orders.tests.test_orders import _req

    item = ProductFactory(base_price=Decimal("4.50"), name={"de": "Bauernbrot"})
    order = services.create_order(items=[(item, 2)], name="K", email="k@test.de", phone="+49 1")
    req = _req(path=f"/bestellung/{order.reference_code}/", tenant=_tenant())
    html = public_views.order_confirmation(req, code=order.reference_code).content.decode()
    _check("confirm-order", _snap(html, order.reference_code))


def test_booking_confirmation_before():
    from datetime import datetime

    from django.utils import timezone

    from apps.booking import public_views
    from apps.booking.models import Booking, Resource
    from apps.booking.tests.test_public import _req
    from apps.promotions.models import Customer

    resource = Resource.objects.create(name="Tisch 1", capacity=2)
    tz = timezone.get_current_timezone()
    start = datetime(2026, 11, 20, 10, 0, tzinfo=tz)
    booking = Booking.objects.create(
        resource=resource,
        customer=Customer.objects.create(name="Gast", email="g@test.de"),
        start=start,
        end=datetime.combine(start.date(), time(11, 0), tzinfo=tz),
        reference_code="T-M2HTEST",
    )
    req = _req(path=f"/t/{booking.reference_code}/", tenant=_tenant())
    html = public_views.termin_confirmation(req, code=booking.reference_code).content.decode()
    _check("confirm-booking", _snap(html, booking.reference_code))


def test_reservation_confirmation_before():
    from apps.promotions import public_views, services
    from apps.promotions.tests.test_zuruecklegen import _promo, _request

    tenant = _tenant()
    tenant.disabled_modules = ["orders"]
    promo = _promo(title={"de": "Frühstück"})
    res = services.reserve(promo, name="A", email="c@example.de")
    req = _request("get", f"/r/{res.reference_code}/", tenant)
    html = public_views.reservation_confirmation(req, code=res.reference_code).content.decode()
    _check("confirm-reservation", _snap(html, res.reference_code))
