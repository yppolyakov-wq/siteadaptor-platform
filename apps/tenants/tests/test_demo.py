"""M20: демо-контент витрины (load/clear), идемпотентность и точное удаление."""

import pytest

from apps.catalog.models import Product
from apps.promotions.models import Promotion
from apps.tenants import demo
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(business_type="bakery"):
    # schema_name=public → catalog/promotions таблицы доступны (как в test-настройке)
    return TenantFactory(schema_name="public", slug="x", name="X", business_type=business_type)


def test_load_demo_creates_catalog_and_promotion():
    tenant = _tenant("bakery")
    assert demo.load_demo(tenant) is True
    assert demo.has_demo(tenant) is True
    assert Product.objects.filter(metadata__demo=True).count() == 4  # bakery-набор
    promo = Promotion.objects.get(metadata__demo=True)
    assert promo.status == "active"
    assert tenant.site_config["demo"]["promotions"] == [str(promo.pk)]


def test_load_demo_is_idempotent():
    tenant = _tenant()
    assert demo.load_demo(tenant) is True
    assert demo.load_demo(tenant) is False  # повторно не дублирует
    assert Product.objects.filter(metadata__demo=True).count() == 4


def test_clear_demo_removes_exactly_demo_objects():
    tenant = _tenant()
    # сторонний (не-демо) товар не должен пострадать
    keep = Product.objects.create(name={"de": "Echt"}, base_price=1)
    demo.load_demo(tenant)
    assert demo.clear_demo(tenant) is True
    assert demo.has_demo(tenant) is False
    assert not Product.objects.filter(metadata__demo=True).exists()
    assert not Promotion.objects.filter(metadata__demo=True).exists()
    assert Product.objects.filter(pk=keep.pk).exists()  # чужое цело


def test_clear_demo_noop_when_absent():
    tenant = _tenant()
    assert demo.clear_demo(tenant) is False


def test_fallback_products_for_unknown_type():
    tenant = _tenant("other")
    demo.load_demo(tenant)
    assert Product.objects.filter(metadata__demo=True).count() == 3  # fallback-набор
