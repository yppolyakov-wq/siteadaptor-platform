"""FB-29.8b: предпросмотр дизайна на пустом магазине показывает товары-примеры —
только в предпросмотре дизайна и без записи в базу."""

import pytest
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.catalog.tests.test_storefront import _req
from apps.core import design_samples
from apps.promotions import public_views

pytestmark = pytest.mark.django_db

SECTIONS = {"sections": [{"key": "products", "enabled": True}]}


def _home(query=""):
    req = _req("/" + query)
    req.tenant.site_config = dict(SECTIONS)
    return public_views.storefront_home(req).content.decode()


def test_wanted_only_in_a_design_preview():
    rf = RequestFactory()
    assert design_samples.wanted(rf.get("/?preview=1&bundle=fokus")) is True
    assert design_samples.wanted(rf.get("/?preview=1&look=klar")) is True
    assert design_samples.wanted(rf.get("/?preview=1")) is False
    assert design_samples.wanted(rf.get("/?bundle=fokus")) is False
    assert design_samples.wanted(rf.get("/")) is False


def test_empty_shop_shows_samples_in_the_design_preview_and_writes_nothing():
    html = _home("?preview=1&look=klar")
    assert "data-sample-products" in html
    assert design_samples.products()[0].name["de"] in html
    assert Product.all_objects.count() == 0 if hasattr(Product, "all_objects") else True
    assert Product.objects.count() == 0


def test_live_site_and_plain_preview_show_no_samples():
    assert "data-sample-products" not in _home()
    assert "data-sample-products" not in _home("?preview=1")


def test_shop_with_products_never_gets_samples():
    ProductFactory(name={"de": "Echter Tee", "en": ""}, base_price="3.00")
    html = _home("?preview=1&look=klar")
    assert "Echter Tee" in html and "data-sample-products" not in html


def test_samples_are_unsaved_and_cannot_be_clicked():
    items = design_samples.products()
    assert len(items) >= 4 and all(p._state.adding for p in items)
    assert all(p.get_absolute_url() == "#" for p in items)
    html = _home("?preview=1&look=klar")
    start = html.index("data-sample-products")
    assert "inert" in html[start - 200 : start + 200]


def test_catalog_page_shows_samples_instead_of_the_empty_text():
    req = _req("/sortiment/?preview=1&look=klar")
    html = public_views.product_list(req).content.decode()
    assert "data-sample-products" in html
    plain = public_views.product_list(_req("/sortiment/")).content.decode()
    assert "data-sample-products" not in plain
