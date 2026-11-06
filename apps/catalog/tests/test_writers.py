"""AIS A-4a: писатели «создать» поверх форм экранов (архитектор: паритет по построению).

Ловушка ModelForm с частичными данными (класс W0): неотправленный флажок = «выкл» — товар
создался бы скрытым, без НДС по умолчанию и т. д. Писатель берёт данные «пустой формы
создания» (её значения по умолчанию) и кладёт поверх только поля пакета.
"""

from decimal import Decimal

import pytest

from apps.catalog import writers
from apps.catalog.forms import ProductForm
from apps.catalog.models import Category, Product
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_product_keeps_form_defaults():
    tenant = TenantFactory(business_type="bakery")
    product = writers.create_product(tenant, {"name_de": "Käsekuchen", "base_price": "3,20"})
    blank = ProductForm(tenant=tenant)
    assert product.name.get("de") == "Käsekuchen"
    assert product.base_price == Decimal("3.20")
    assert product.is_active is True  # флажок «aktiv» пустой формы — включён
    assert product.vat_rate == Decimal("7.00")  # еда — 7 %, как у экрана создания
    for name in ("unit",):
        if name in blank.fields:
            assert str(getattr(product, name)) == str(blank[name].value() or getattr(product, name))


def test_product_non_food_vat_19():
    tenant = TenantFactory(business_type="shop")
    product = writers.create_product(tenant, {"name_de": "Tasse", "base_price": "9"})
    assert product.vat_rate == Decimal("19.00")


def test_invalid_data_raises_with_field_errors():
    tenant = TenantFactory(business_type="bakery")
    with pytest.raises(writers.WriteError) as exc:
        writers.create_product(tenant, {"name_de": "", "base_price": "abc"})
    assert exc.value.errors  # ошибки по полям, ничего не создано
    assert not Product.objects.exists()


def test_product_in_category_and_unknown_fields_ignored():
    tenant = TenantFactory(business_type="bakery")
    cat = writers.create_category(tenant, {"name_de": "Kuchen"})
    product = writers.create_product(
        tenant,
        {
            "name_de": "Apfelkuchen",
            "base_price": "2,50",
            "category": str(cat.pk),
            "is_featured": "on",
            "evil": "x",
        },
    )
    assert product.category_id == cat.pk
    assert isinstance(cat, Category) and cat.is_active


def test_stock_ledger_written_like_the_screen():
    from apps.inventory.models import StockMovement

    tenant = TenantFactory(business_type="bakery")
    product = writers.create_product(
        tenant, {"name_de": "Brot", "base_price": "4", "stock_quantity": "5"}, actor="owner"
    )
    assert StockMovement.objects.filter(product=product).exists()


def test_service_writer_same_path_as_screen():
    from apps.booking import writers as bw

    tenant = TenantFactory(business_type="friseur")
    service = bw.create_service(
        tenant, {"name": "Haarschnitt", "price_eur": "25,00", "duration": "45"}
    )
    assert service.price_cents == 2500 and service.duration_minutes == 45
    with pytest.raises(writers.WriteError):
        bw.create_service(tenant, {"name": "", "price_eur": "x"})
