"""KA-12 E2.3: сортировка списков продаж `?sort=` по белому списку.

Ключ — короткое слово, которое приходит из URL; в `order_by` попадает только
значение из словаря `transactions.LIST_SORTS`. Неизвестный ключ — порядок
по умолчанию, а не 500. Сумма — только у видов, где итог лежит в одном поле БД.
"""

from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.core import sales_page, transactions

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _order(name, price):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal(price))
    return create_order(items=[(product, 1)], name=name, email=f"{name.lower()}@test.de")


def _codes(qs):
    return [o.reference_code for o in qs]


def test_sum_sort_orders_by_total_desc():
    small = _order("Anna", "5.00")
    big = _order("Berta", "50.00")
    qs = transactions._managed_queryset("order", sort="summe")
    assert _codes(qs)[:2] == [big.reference_code, small.reference_code]


def test_customer_sort_orders_alphabetically():
    zed = _order("Zora", "5.00")
    abe = _order("Abel", "5.00")
    qs = transactions._managed_queryset("order", sort="kunde")
    assert _codes(qs)[:2] == [abe.reference_code, zed.reference_code]


def test_old_first_reverses_default():
    first = _order("Anna", "5.00")
    second = _order("Berta", "5.00")
    assert _codes(transactions._managed_queryset("order"))[:2] == [
        second.reference_code,
        first.reference_code,
    ]
    assert _codes(transactions._managed_queryset("order", sort="alt"))[:2] == [
        first.reference_code,
        second.reference_code,
    ]


@pytest.mark.parametrize("junk", ["';drop table", "-total", "__class__", "pk"])
def test_unknown_sort_key_keeps_default_order(junk):
    first = _order("Anna", "5.00")
    second = _order("Berta", "50.00")
    qs = transactions._managed_queryset("order", sort=junk)
    assert _codes(qs)[:2] == [second.reference_code, first.reference_code]


def test_sum_sort_not_offered_where_total_is_computed_in_python():
    for kind in ("booking", "ticket", "reservation"):
        assert "summe" not in {key for key, _label in transactions.list_sort_options(kind)}
    for kind in ("order", "job", "stay"):
        assert "summe" in {key for key, _label in transactions.list_sort_options(kind)}


def test_every_sort_key_builds_a_valid_query():
    """Каждый ключ белого списка обязан строить работающий запрос у своего вида."""
    for kind in transactions.TRANSACTION_KINDS:
        for key, _label in transactions.list_sort_options(kind):
            list(transactions._managed_queryset(kind, sort=key)[:1])


def test_sort_is_not_a_filter_and_does_not_switch_view():
    assert sales_page.view_for_filters("order", "board", {"sort": "summe"}) == "board"


def test_order_list_honours_sort_and_offers_options():
    from apps.tenants.tests.factories import TenantFactory

    small = _order("Anna", "5.00")
    big = _order("Berta", "50.00")
    tenant = TenantFactory.build(schema_name="public")
    req = RequestFactory().get("/dashboard/verkaeufe/", {"tab": "order", "sort": "summe"})
    req.tenant = tenant
    ctx = sales_page.body_context(req, "order", "liste")
    assert _codes(ctx["orders"])[:2] == [big.reference_code, small.reference_code]
    assert ctx["list_sort"] == "summe"
    assert "summe" in {key for key, _label in ctx["list_sort_options"]}


def test_order_list_junk_sort_is_blanked_in_context():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(schema_name="public")
    req = RequestFactory().get("/dashboard/verkaeufe/", {"tab": "order", "sort": "<x>"})
    req.tenant = tenant
    ctx = sales_page.body_context(req, "order", "liste")
    assert ctx["list_sort"] == ""
