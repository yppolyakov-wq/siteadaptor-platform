"""SHP-1b: вес и размеры товара для доставки.

Замки: поля в форме товара (карточка «Versand» в рейле); вес варианта пишется только при
presence-сентинеле (частичная форма не стирает, W0); мусор = «не знаю», а не 0; CSV ходит
туда-обратно, пустая колонка не стирает; профиль посылки: вариант → товар → неизвестно."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.forms import ProductForm
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.orders.shipping import parcel_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _post(data):
    req = RequestFactory().post("/x/", data)
    req.tenant = TenantFactory.build()
    req.user = get_user_model()(username="o", is_active=True)
    req.session = {}
    req._messages = FallbackStorage(req)
    return req


def test_product_form_has_shipping_fields_bound_to_the_form():
    form = ProductForm(tenant=TenantFactory.build())
    for name in ("shipping_weight_g", "length_cm", "width_cm", "height_cm", "bulky"):
        assert name in form.fields
        assert form.fields[name].widget.attrs.get("form") == "product-form"
    assert not form.fields["shipping_weight_g"].required


def test_variant_weight_written_only_with_sentinel_and_garbage_is_unknown():
    product = ProductFactory()
    variant = ProductVariant.objects.create(product=product, label="XL", shipping_weight_g=900)
    base = {"sort": "0", "is_active": "1"}
    views.variant_update(_post(base), pk=product.pk, vid=variant.pk)
    variant.refresh_from_db()
    assert variant.shipping_weight_g == 900  # форма без сентинела вес не трогает
    views.variant_update(
        _post({**base, "weight_present": "1", "weight_g": "1200"}), pk=product.pk, vid=variant.pk
    )
    variant.refresh_from_db()
    assert variant.shipping_weight_g == 1200
    views.variant_update(
        _post({**base, "weight_present": "1", "weight_g": "-5"}), pk=product.pk, vid=variant.pk
    )
    variant.refresh_from_db()
    assert variant.shipping_weight_g is None  # мусор = «не знаю», а не 0 g


def test_csv_import_sets_weight_and_empty_column_keeps_it():
    from apps.imports.processors.product import ProductProcessor

    product = ProductFactory(sku="W-1", shipping_weight_g=500, bulky=True)
    proc = ProductProcessor()
    row = {"name_de": "Topf", "sku": "W-1", "base_price": "10", "shipping_weight_g": ""}
    proc.create_or_update({**row, "bulky": ""}, update_existing=True)
    product.refresh_from_db()
    assert (product.shipping_weight_g, product.bulky) == (500, True)
    proc.create_or_update(
        {**row, "shipping_weight_g": "750", "length_cm": "40", "bulky": "0"},
        update_existing=True,
    )
    product.refresh_from_db()
    assert (product.shipping_weight_g, product.length_cm, product.bulky) == (750, 40, False)


def test_parcel_profile_variant_then_product_then_unknown():
    heavy = ProductFactory(shipping_weight_g=400, length_cm=30, width_cm=20)
    light = ProductFactory(shipping_weight_g=None, bulky=True)
    variant = ProductVariant.objects.create(product=heavy, label="XL", shipping_weight_g=600)
    parcel = parcel_for([(heavy, variant, 2), (heavy, None, 1), (light, None, 3), (None, None, 9)])
    assert parcel.known_g == 2 * 600 + 400
    assert parcel.unknown_qty == 3
    assert parcel.longest_cm == 30 and parcel.bulky
