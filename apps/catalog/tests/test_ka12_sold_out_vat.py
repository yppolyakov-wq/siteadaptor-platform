"""KA-12 E3.3 (НДС 7 % у еды по умолчанию) + E3.4 («Heute ausverkauft»)."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.forms import ProductForm
from apps.catalog.tests.factories import ProductFactory
from apps.core import sellable_manage
from apps.orders.services import OutOfStock, create_order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "btype,rate", [("bakery", "7.00"), ("restaurant", "7.00"), ("shop", "19.00")]
)
def test_new_product_default_vat_by_business_type(btype, rate):
    form = ProductForm(tenant=TenantFactory.build(business_type=btype))
    assert str(form.initial.get("vat_rate", form.fields["vat_rate"].initial)) == rate


def test_existing_product_keeps_its_rate():
    product = ProductFactory(vat_rate=Decimal("19.00"))
    form = ProductForm(instance=product, tenant=TenantFactory.build(business_type="bakery"))
    assert str(form.fields["vat_rate"].initial) != "7.00" or form.initial.get(
        "vat_rate"
    ) == Decimal("19.00")
    assert form.initial.get("vat_rate") == Decimal("19.00")


def test_sold_out_today_blocks_and_resets_tomorrow():
    product = ProductFactory(base_price=Decimal("3.00"), stock_quantity=None)
    sellable_manage.toggle_sold_out_today(product.pk, True)
    product.refresh_from_db()
    assert product.is_sold_out_today and not product.in_stock
    with pytest.raises(OutOfStock):
        create_order(items=[(product, 1)], name="K")
    # завтра — снова доступен без записи
    product.sold_out_until = timezone.localdate() - datetime.timedelta(days=1)
    product.save()
    assert product.in_stock
    create_order(items=[(product, 1)], name="K")


def test_toggle_off_restores_availability():
    product = ProductFactory(stock_quantity=4)
    sellable_manage.toggle_sold_out_today(product.pk, True)
    sellable_manage.toggle_sold_out_today(product.pk, False)
    product.refresh_from_db()
    assert product.sold_out_until is None and product.in_stock


def test_only_available_facet_excludes_sold_out_today():
    from apps.catalog.facets import CatalogFacets
    from apps.catalog.models import Product

    a = ProductFactory(stock_quantity=None)
    b = ProductFactory(stock_quantity=None)
    sellable_manage.toggle_sold_out_today(b.pk, True)
    ids = set(CatalogFacets._only_available(Product.objects.all()).values_list("pk", flat=True))
    assert a.pk in ids and b.pk not in ids
