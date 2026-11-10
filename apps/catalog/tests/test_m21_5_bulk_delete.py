"""M21.5: массовое удаление выбранных товаров, возврат на ту же страницу списка,
размер страницы 20/50/100 и «alle angezeigten auswählen» в виде Liste."""

from decimal import Decimal

import pytest

from apps.catalog import views
from apps.catalog.models import Product
from apps.catalog.tests.test_wr6_bulk_csv import _req

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _p(name="Tee"):
    return Product.objects.create(name={"de": name}, base_price=Decimal("5.00"))


def test_bulk_delete_soft_deletes_selected_and_returns_to_same_page():
    a, b, keep = _p("A"), _p("B"), _p("C")
    nxt = "/dashboard/angebote/?kategorie=x&seite=2&pro_seite=20"
    resp = views.products_bulk_delete(
        _req(data={"ids": [str(a.pk), str(b.pk), "garbage"], "next": nxt})
    )
    assert resp.status_code == 302 and resp["Location"] == nxt
    assert not Product.objects.filter(pk__in=[a.pk, b.pk]).exists()
    assert Product.all_objects.filter(pk__in=[a.pk, b.pk]).count() == 2  # soft-delete
    assert Product.objects.filter(pk=keep.pk).exists()


def test_bulk_back_rejects_foreign_next():
    a = _p()
    resp = views.products_bulk_delete(_req(data={"ids": [str(a.pk)], "next": "//evil.example/"}))
    assert resp["Location"] == "/dashboard/angebote/"


def test_bulk_delete_needs_the_same_right_as_single_delete():
    from apps.core.view_perms import RULES

    assert RULES["catalog:products-bulk-delete"] == RULES["catalog:product-delete"]


def test_page_size_paginates():
    from apps.core import sellable_manage as sm
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public")
    for i in range(25):
        _p(f"T{i:02d}")
    sections = sm.sellable_manage_sections_for(
        tenant, kind_only="product", page_raw="2", per_page=20
    )
    page = sections[0]["page"]
    assert page.total == 25 and page.page == 2 and len(page.items) == 5
