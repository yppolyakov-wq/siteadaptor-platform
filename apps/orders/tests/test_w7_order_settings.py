"""W7a (аудит 2026-08-05): мёртвые POST-ветки order_settings удалены — легаси-POST
не может обнулить delivery_*/bank_*/orders_prepay (их UI живёт на payment_settings)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.orders import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _post(data, tenant):
    req = RequestFactory().post("/dashboard/orders/settings/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant
    return req


def test_legacy_delivery_form_no_longer_wipes_fields():
    tenant = TenantFactory(business_type="bakery")
    tenant.delivery_enabled = True
    tenant.delivery_fee_cents = 350
    tenant.vorkasse_enabled = True
    tenant.bank_iban = "DE02120300000000202051"
    tenant.orders_prepay = True
    tenant.save(
        update_fields=[
            "delivery_enabled",
            "delivery_fee_cents",
            "vorkasse_enabled",
            "bank_iban",
            "orders_prepay",
        ]
    )
    for form in ("delivery", "vorkasse", ""):  # "" — бывший дефолт save_prepay
        resp = views.order_settings(_post({"form": form}, tenant))
        assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.delivery_enabled is True
    assert tenant.delivery_fee_cents == 350
    assert tenant.vorkasse_enabled is True
    assert tenant.bank_iban == "DE02120300000000202051"
    assert tenant.orders_prepay is True


def test_status_labels_branch_removed():
    """W9-8: ветка status_labels переехала на generic status-labels-save («Abläufe») —
    легаси-POST сюда больше НИЧЕГО не пишет (no-op редирект)."""
    tenant = TenantFactory(business_type="bakery")
    resp = views.order_settings(_post({"form": "status_labels", "label_ready": "Fertig!"}, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert "status_labels" not in (tenant.site_config or {})
