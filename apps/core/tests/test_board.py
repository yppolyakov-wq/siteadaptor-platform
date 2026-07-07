"""U-D2/3: /dashboard/board/ — рендер вкладок/колонок/карточек + гейтинг по модулю."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    pk = 1


def _make_order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"))
    return create_order(items=[(product, 1)], name="Max", email="max@test.de")


def _req(disabled=None):
    req = RequestFactory().get("/dashboard/board/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=disabled or [])
    return req


def test_board_renders_tabs_columns_and_card():
    order = _make_order()
    html = views.board(_req()).content.decode()
    assert "Aufgaben-Board" in html
    assert order.reference_code in html  # карточка заказа отрендерена
    assert "data-drop-stage" in html  # колонки-дропзоны есть
    assert 'data-board-tab="order"' in html  # вкладка заказов


def test_board_hides_inactive_transaction_module():
    _make_order()
    html = views.board(_req(disabled=["orders"])).content.decode()
    assert 'data-board-tab="order"' not in html


def test_board_empty_state_when_no_active_transactions():
    # выключаем все транзакционные модули → пустая доска, graceful empty-state
    disabled = ["orders", "booking", "stays", "events", "jobs", "promotions"]
    html = views.board(_req(disabled=disabled)).content.decode()
    assert "Noch keine Verkaufskanäle" in html
