"""T4: drill-down истории по сущности + CSV-экспорт движений."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.inventory import services, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "chef"


def _req(data=None):
    req = RequestFactory().get("/dashboard/stock/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(business_type="retail")
    return req


def test_csv_export_returns_movements():
    p = ProductFactory(stock_quantity=10)
    services.record_movement(product=p, kind="receipt", delta=10, source="manual")
    resp = views.stock(_req({"export": "csv"}))
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]
    body = resp.content.decode()
    assert "Produkt" in body and str(p) in body and "10" in body


def test_history_filter_renders_scoped_header():
    p1 = ProductFactory(stock_quantity=10)
    services.apply_manual_movement(product=p1, kind=services.StockMovement.KIND_RECEIPT, delta=3)
    html = views.stock(_req({"history": f"p{p1.id}"})).content.decode()
    assert "Verlauf" in html  # scoped-заголовок истории
    assert str(p1) in html
    assert "?export=csv" in html  # ссылка экспорта присутствует
