"""H2-1 (мультиархетип): aggregate_primary_sections — «главный» блок каждого активного
архетипа в порядке реестра (_PRIORITY). Для авто-композиции главной сборного сайта."""

from apps.core import archetypes


class _FakeTenant:
    def __init__(self, active):
        self._active = set(active)

    def is_module_active(self, key):
        return key in self._active


def test_aggregate_orders_by_registry_priority():
    # _PRIORITY: events > stays > booking > catalog > promotions
    t = _FakeTenant({"catalog", "booking", "events"})
    agg = archetypes.aggregate_primary_sections(t)
    assert [a["key"] for a in agg] == ["events", "services", "products"]
    assert [a["module"] for a in agg] == ["events", "booking", "catalog"]
    assert [a["order"] for a in agg] == [0, 2, 3]  # позиции в _PRIORITY


def test_aggregate_single_archetype():
    t = _FakeTenant({"catalog"})
    assert archetypes.aggregate_primary_sections(t) == [
        {"key": "products", "module": "catalog", "order": 3}
    ]


def test_aggregate_full_multiarchetype():
    t = _FakeTenant({"catalog", "stays", "booking", "events", "promotions"})
    assert [a["key"] for a in archetypes.aggregate_primary_sections(t)] == [
        "events",
        "stay_rooms",
        "services",
        "products",
        "promotions",
    ]


def test_aggregate_none_active():
    # модуль без PRIMARY_SECTION (jobs) или неактивные → пусто
    assert archetypes.aggregate_primary_sections(_FakeTenant({"jobs", "inbox"})) == []


def test_aggregate_skips_inactive():
    t = _FakeTenant({"stays"})  # только отель
    assert [a["key"] for a in archetypes.aggregate_primary_sections(t)] == ["stay_rooms"]


# --- H2-2: интеграция — мультиархетип-дефолт главной (storefront_home) ---
from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.promotions import public_views  # noqa: E402
from apps.tenants.tests.factories import TenantFactory  # noqa: E402


def _home(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


@pytest.mark.django_db
def test_multiarchetype_home_enables_each_archetype_primary(settings):
    """H2-2: сборный сайт (catalog+events) без явных sections → главная включает блок
    КАЖДОГО архетипа (товары + события), а не только один primary."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.catalog.models import Product
    from apps.events.models import Event

    tenant = TenantFactory(
        schema_name="public", slug="ma", name="MA", disabled_modules=[], site_config={}
    )
    Product.objects.create(name={"de": "Brot"}, base_price="2.00", is_active=True, is_featured=True)
    Event.objects.create(
        title="Retreat-Wochenende",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
        price_cents=5000,
        capacity=10,
    )
    body = _home(tenant)
    assert "Retreat-Wochenende" in body  # events-секция включена (архетип events)
    assert "Brot" in body  # products-секция (архетип catalog) тоже


@pytest.mark.django_db
def test_home_default_untouched_when_sections_configured(settings):
    """H2-2 гард: если владелец задал sections — авто-агрегация НЕ вмешивается."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.events.models import Event

    tenant = TenantFactory(
        schema_name="public",
        slug="ma2",
        name="MA2",
        disabled_modules=[],
        site_config={"sections": [{"key": "hero", "enabled": True}]},  # явная композиция
    )
    Event.objects.create(
        title="Versteckt",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
        price_cents=5000,
        capacity=10,
    )
    # events не в заданных sections → не авто-включается (интент владельца сохранён)
    assert "Versteckt" not in _home(tenant)
