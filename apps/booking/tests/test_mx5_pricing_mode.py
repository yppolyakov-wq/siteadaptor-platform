"""MX-5: режим цены Работы «за человека» (Tripster) + способ продажи товара."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import public_views
from apps.booking.models import AvailabilityRule, Booking, Resource, Service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(enabled_modules=["booking", "catalog", "orders", "jobs"])
    return tenant


def _post(path, data, tenant=None):
    # уникальный IP — rl:* в Redis переживает прогоны (грабля из CLAUDE.md)
    request = RequestFactory().post(path, data, REMOTE_ADDR=f"10.9.{uuid.uuid4().int % 250}.7")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = type("U", (), {"is_authenticated": False})()
    request.tenant = tenant or _tenant()
    return request


def _service(**kw):
    kw.setdefault("name", f"Tour {uuid.uuid4().hex[:6]}")
    kw.setdefault("price_cents", 2500)
    kw.setdefault("duration_minutes", 60)
    service = Service.objects.create(**kw)
    resource = Resource.objects.create(name="Guide", capacity=1)
    for wd in range(7):
        AvailabilityRule.objects.create(
            resource=resource, weekday=wd, start_time="09:00", end_time="18:00", slot_minutes=60
        )
    return service


def _book(service, persons=None):
    day = timezone.localdate() + timedelta(days=5)
    start = timezone.make_aware(timezone.datetime(day.year, day.month, day.day, 10, 0))
    data = {"start": [start.isoformat()], "name": "Gast", "email": "g@t.de"}
    if persons is not None:
        data["personen"] = str(persons)
    resp = public_views.service_book(_post(f"/termin/{service.pk}/buchen/", data), pk=service.pk)
    assert resp.status_code == 302
    return Booking.objects.latest("created_at")


def test_per_person_multiplies_price_and_stores_party_size():
    service = _service(pricing_mode="per_person")
    b = _book(service, persons=3)
    assert b.price_cents == 7500  # 25 € × 3
    assert b.party_size == 3


def test_default_mode_ignores_persons_field():
    """Легаси-режим «за бронь»: поле «Personen» (даже подсунутое) цену не множит."""
    service = _service()  # pricing_mode=""
    b = _book(service, persons=4)
    assert b.price_cents == 2500
    assert b.party_size == 1


def test_product_request_mode_hides_cart_shows_anfrage():
    from django.test import RequestFactory as RF

    from apps.catalog.tests.factories import ProductFactory
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(enabled_modules=["catalog", "orders", "jobs"])
    product = ProductFactory(primary_action="request", stock_quantity=None)
    from apps.catalog import views as catalog_views  # noqa: F401 — деталь рендерит promotions view
    from apps.promotions import public_views as promo_public

    request = RF().get(f"/sortiment/p/{product.slug or product.pk}/")
    request.tenant = tenant
    request.user = type("U", (), {"is_authenticated": False})()
    SessionMiddleware(lambda r: None).process_request(request)
    resp = promo_public.product_detail(request, pk=product.pk)
    body = resp.content.decode()
    assert "Request a quote" in body or "Angebot anfragen" in body or "anfrage" in body.lower()
    assert "_add_to_cart" not in body and 'name="qty"' not in body
