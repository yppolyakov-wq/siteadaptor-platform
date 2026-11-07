"""FB-24d: свои опции на витрине — ряды выбора поверх селекта и фильтр ?opt_<код>=."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import options
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/sortiment/", params=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Laden", disabled_modules=[])
    return request


def _shirt(name, materials):
    p = ProductFactory(name={"de": name})
    material = options.enable_standard("material")
    options.set_product_axes(p, ["size", "material"])
    for size in ("S", "M"):
        for m in materials:
            v = ProductVariant.objects.create(product=p, size=size, label=f"{size} · {m}")
            options.set_variant_option(v, material, m)
    return p


def test_detail_has_material_row_and_option_attributes():
    p = _shirt("Hemd", ["Baumwolle", "Leinen"])
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    assert 'data-pick-axis="material"' in body
    # стенд: ряд размера пропадал, когда у товара не задан вид выбора
    assert 'data-pick-axis="size"' in body
    assert 'data-o-material="Leinen"' in body
    assert 'data-pick-value="Baumwolle"' in body
    # селект остаётся единственным полем варианта
    assert body.count('name="variant"') == 1


def test_product_without_custom_axes_unchanged():
    p = ProductFactory(name={"de": "Brot"})
    ProductVariant.objects.create(product=p, label="500 g")
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    import re

    # разметка, а не строки общего скрипта страницы
    assert not re.search(r'data-o-[\w-]+="', body)
    assert 'data-pick-axis="' not in body


def test_catalog_filter_by_material_and_chip_row():
    _shirt("Hemd Leinen", ["Leinen"])
    _shirt("Hemd Baumwolle", ["Baumwolle"])
    body = public_views.product_list(_req()).content.decode()
    assert 'name="opt_material"' in body  # ряд фильтра виден (два значения в каталоге)
    body = public_views.product_list(_req(params={"opt_material": "Leinen"})).content.decode()
    assert "Hemd Leinen" in body and "Hemd Baumwolle" not in body


def test_unknown_option_code_is_ignored():
    _shirt("Hemd Leinen", ["Leinen"])
    body = public_views.product_list(_req(params={"opt_evil": "x"})).content.decode()
    assert "Hemd Leinen" in body
