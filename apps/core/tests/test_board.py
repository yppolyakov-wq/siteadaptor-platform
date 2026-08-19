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


def test_board_redirects_to_unified_sales_page():
    """X2b (осознанная переписка): легаси-доска снесена → 302 на Verkäufe.
    Прежние четыре теста проверяли её рендер (вкладки/колонки/архив/пустое
    состояние) — эта функциональность живёт видом «Board» вкладки Verkäufe и
    покрыта test_verkaeufe."""
    _make_order()
    resp = views.board(_req())
    assert resp.status_code == 302
    assert resp["Location"].startswith("/dashboard/verkaeufe/")


def test_board_redirect_maps_kind_param_to_tab():
    """Семантика параметра: доска знала ?kind=, единая страница — ?tab=;
    старый ключ в новый адрес не тащим."""
    req = _req()
    req.GET = req.GET.copy()
    req.GET["kind"] = "order"
    resp = views.board(req)
    assert resp.status_code == 302
    assert "tab=order" in resp["Location"] and "kind=" not in resp["Location"]
