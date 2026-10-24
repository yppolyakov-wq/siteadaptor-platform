"""KA-12 E2.4: peek (карточка сбоку) у строк заказов и карточек доски.

Peek живёт из тех же данных Transaction, что строка, — без запросов на клик.
Карточка, перерисованная fetch'ем после смены статуса, обязана нести
<template> заново (иначе peek пропадает), а его форма — возвращать на исходную
страницу, а не на адрес action-эндпоинта (GET туда — 405)."""

from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import sales_page, views
from apps.core.tests.test_kanban import _make_order, _post

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _list_ctx(params=None):
    from apps.tenants.tests.factories import TenantFactory

    req = RequestFactory().get("/dashboard/verkaeufe/", {"tab": "order", **(params or {})})
    req.tenant = TenantFactory.build(schema_name="public")
    return req, sales_page.body_context(req, "order", "liste")


def test_order_rows_carry_peek_template():
    order = _make_order()
    req, ctx = _list_ctx()
    html = render_to_string("orders/_order_rows.html", ctx, request=req)
    assert "data-peek-row" in html and "template data-peek" in html
    assert 'id="deal-peek"' in html
    assert f"#{order.reference_code}" in html


def test_order_rows_without_sales_context_render_as_before():
    """Строки вне страницы продаж (без o.tx) — без peek и без лишней колонки."""
    order = _make_order()
    html = render_to_string("orders/_order_rows.html", {"orders": [order]})
    assert "data-peek-row" not in html and 'id="deal-peek"' not in html


def test_order_list_query_count_does_not_grow_with_rows(django_assert_max_num_queries):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("3.00"))
    for i in range(3):
        create_order(items=[(product, 1)], name=f"K{i}", email=f"k{i}@t.de")
    req, _ctx = _list_ctx()
    with django_assert_max_num_queries(40) as small:
        sales_page.body_context(req, "order", "liste")
    for i in range(12):
        create_order(items=[(product, 1)], name=f"M{i}", email=f"m{i}@t.de")
    with django_assert_max_num_queries(len(small.captured_queries) + 2):
        sales_page.body_context(req, "order", "liste")


def test_kanban_card_redraw_keeps_peek_and_returns_to_origin():
    order = _make_order()
    req = _post("order", order.pk, "confirmed")
    req.POST = req.POST.copy()
    req.POST["next"] = "/dashboard/verkaeufe/?tab=order&view=board"
    resp = views.kanban_action(req, "order", order.pk)
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "data-peek-row" in html and "template data-peek" in html
    # форма внутри peek возвращает туда, откуда пришли, а не на action-URL
    assert 'value="/dashboard/verkaeufe/?tab=order&amp;view=board"' in html
    assert "/action/" not in html.split("template data-peek", 1)[1].split('name="next"', 1)[1][:80]


def test_board_has_peek_drawer_once():
    from apps.core import transactions
    from apps.tenants.tests.factories import TenantFactory

    _make_order()
    tenant = TenantFactory.build(schema_name="public")
    sections = transactions.manage_sections_for(tenant, only="order", per_column=10)
    req = RequestFactory().get("/dashboard/verkaeufe/")
    html = render_to_string(
        "core/_board_body.html", {"sections": sections, "active_kind": "order"}, request=req
    )
    assert "data-peek-row" in html
    assert html.count("<aside data-peek-drawer") == 1
    assert html.count("if (window.__dealPeekBound) return") == 1
