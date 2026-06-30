"""H0/H1: переключатель страниц превью редактора включает страницы-ДЕТАЛИ активных
архетипов (товар/номер/событие) — чтобы их можно было открыть на канве и править инлайн
(инлайн-эндпоинты H1.2). Источник правды — archetypes.example_detail_pages.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.core import archetypes, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("schema_name", "public")
    kw.setdefault("disabled_modules", [])  # events/stays активны, если не отключены явно
    return TenantFactory(**kw)


def test_example_detail_pages_catalog_product():
    from apps.catalog.models import Product

    tenant = _tenant(slug="pp1", name="PP1")
    p = Product.objects.create(name={"de": "Brot"}, base_price="2.00", is_active=True)
    urls = [pg["url"] for pg in archetypes.example_detail_pages(tenant)]
    assert reverse("storefront-product", args=[p.pk]) in urls


def test_example_detail_pages_empty_without_items():
    # Архетипы активны, но опубликованных объектов нет → детали-страниц нет.
    assert archetypes.example_detail_pages(_tenant(slug="pp2", name="PP2")) == []


def test_example_detail_pages_published_event_only():
    """Гейт фильтра status=published: черновик-событие не попадает в превью."""
    from apps.events.models import Event

    tenant = _tenant(slug="pp3", name="PP3")
    draft = Event.objects.create(
        title="Draft",
        starts_at=timezone.now() + timedelta(days=3),
        status=Event.STATUS_DRAFT,
        price_cents=1000,
        capacity=5,
    )
    pub = Event.objects.create(
        title="Live",
        starts_at=timezone.now() + timedelta(days=5),
        status=Event.STATUS_PUBLISHED,
        price_cents=2000,
        capacity=10,
    )
    urls = [pg["url"] for pg in archetypes.example_detail_pages(tenant)]
    assert reverse("storefront-event", args=[pub.pk]) in urls
    assert reverse("storefront-event", args=[draft.pk]) not in urls


def test_example_detail_pages_stay_unit():
    from apps.stays.models import StayUnit

    tenant = _tenant(slug="pp4", name="PP4")
    u = StayUnit.objects.create(name="Doppelzimmer")
    urls = [pg["url"] for pg in archetypes.example_detail_pages(tenant)]
    assert reverse("storefront-unterkunft-unit", args=[u.pk]) in urls


def test_disabled_archetype_excluded_from_detail_pages():
    """Выключенный архетип не даёт детали-страницы, даже если объект есть."""
    from apps.stays.models import StayUnit

    tenant = _tenant(slug="pp5", name="PP5", disabled_modules=["stays"])
    u = StayUnit.objects.create(name="Zimmer")
    urls = [pg["url"] for pg in archetypes.example_detail_pages(tenant)]
    assert reverse("storefront-unterkunft-unit", args=[u.pk]) not in urls


def test_editor_preview_switcher_lists_product_detail():
    """Интеграция: редактор главной рендерит деталь товара в переключателе превью."""
    from apps.catalog.models import Product

    tenant = _tenant(
        slug="pp6",
        name="PP6",
        business_type="bakery",
        disabled_modules=["stays", "events", "booking", "jobs", "orders", "loyalty"],
    )
    p = Product.objects.create(name={"de": "Brot"}, base_price="2.00", is_active=True)
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    body = views.home_builder_view(req).content.decode()
    assert reverse("storefront-product", args=[p.pk]) in body
