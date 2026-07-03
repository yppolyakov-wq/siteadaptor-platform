"""CM-8 — карточка клиента 360°: KPI-шапка LTV, недостающие разделы за
модуль-гейтом, отзывы по email-матчу (fail-soft)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.crm import views
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant=None):
    import uuid

    request = RequestFactory().get("/crm/x/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o{uuid.uuid4().hex[:10]}", email="o@t.de", password="pw12345678"
    )
    request.tenant = tenant or TenantFactory.build()
    return request


def _customer(**kw):
    kw.setdefault("name", "Kim Kunde")
    kw.setdefault("email", "kim@test.de")
    return Customer.objects.create(**kw)


def test_kpi_header_ltv_and_counts():
    from apps.catalog.tests.factories import ProductFactory
    from apps.finance.services import record_revenue
    from apps.orders import services as order_services

    customer = _customer()
    order_services.create_order(items=[(ProductFactory(), 1)], name="Kim", email="kim@test.de")
    record_revenue(source="order", source_ref="r1", amount=Decimal("42.50"), customer=customer)
    body = views.customer_detail(_req(), pk=customer.pk).content.decode()
    assert "42,50" in body or "42.50" in body  # LTV из RevenueEntry
    assert "Orders" in body  # счётчик заказов в KPI-строке


def test_sections_gated_by_module():
    from apps.booking import services as booking_services
    from apps.booking.models import Resource

    customer = _customer(email="gate@test.de")
    start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    booking_services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="Kim",
        email="gate@test.de",
    )
    on = views.customer_detail(_req(), pk=customer.pk).content.decode()
    assert "Appointments" in on
    off = views.customer_detail(
        _req(tenant=TenantFactory.build(disabled_modules=["booking"])), pk=customer.pk
    ).content.decode()
    assert "Appointments" not in off  # модуль выключен → раздела нет


def test_reviews_matched_by_email_only():
    from apps.reviews.models import Review

    customer = _customer(email="rev@test.de")
    import uuid

    Review.objects.create(
        entity_kind="product",
        entity_id=uuid.uuid4(),
        email="REV@test.de",  # регистронезависимый матч
        author_name="Kim",
        rating=5,
        comment="Super Laden!",
        is_published=True,
    )
    body = views.customer_detail(_req(), pk=customer.pk).content.decode()
    assert "Super Laden!" in body
    # клиент без email — секции отзывов нет (матчить не по чему)
    anon = _customer(name="Ohne Mail", email="")
    body2 = views.customer_detail(_req(), pk=anon.pk).content.decode()
    assert "Super Laden!" not in body2
