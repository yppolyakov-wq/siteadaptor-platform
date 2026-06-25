"""Спринт C (правовой долг): Widerrufsbelehrung для товаров + онлайн-форма Widerruf."""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- C.2: текст Widerrufsbelehrung ------------------------------------------------


def test_goods_widerruf_text_for_delivery_seller():
    tenant = TenantFactory.build(
        name="Hofladen", address="Feldweg 1, 50000 Köln", delivery_enabled=True
    )
    text = tenant.withdrawal_text()
    assert "Widerrufsbelehrung" in text
    assert "vierzehn Tagen" in text  # 14-Tage-Frist
    assert "Muster-Widerrufsformular" in text
    assert "/widerruf-formular/" in text  # ссылка на онлайн-форму


def test_reservation_text_when_no_delivery():
    tenant = TenantFactory.build(name="Salon", delivery_enabled=False)
    text = tenant.withdrawal_text()
    assert "Reservierung" in text
    assert "Muster-Widerrufsformular" not in text


def test_owner_override_wins():
    tenant = TenantFactory.build(delivery_enabled=True, withdrawal_policy="Eigener Text.")
    assert tenant.withdrawal_text() == "Eigener Text."


# --- C.1: онлайн-форма Widerruf ---------------------------------------------------


def _req(method="get", data=None, tenant=None):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    request = getattr(RequestFactory(), method)("/widerruf-formular/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def test_withdrawal_form_get_renders():
    tenant = TenantFactory(schema_name="public", slug="wf-get", name="Shop")
    html = public_views.withdrawal_form(_req(tenant=tenant)).content.decode()
    assert "Widerruf erklären" in html and 'name="goods"' in html


def test_withdrawal_form_post_sends_and_confirms(mailoutbox):
    tenant = TenantFactory(
        schema_name="public", slug="wf-post", name="Shop", contact_email="shop@example.de"
    )
    response = public_views.withdrawal_form(
        _req("post", {"name": "Max", "goods": "1× Buch", "order_code": "A-1"}, tenant)
    )
    assert response.status_code == 200
    assert "eingegangen" in response.content.decode()
    # письмо продавцу отправлено с заявлением.
    assert len(mailoutbox) == 1
    assert "Widerruf" in mailoutbox[0].subject
    assert "1× Buch" in mailoutbox[0].body


def test_withdrawal_form_requires_name_and_goods():
    tenant = TenantFactory(schema_name="public", slug="wf-req", name="Shop")
    response = public_views.withdrawal_form(_req("post", {"name": "Max"}, tenant))
    assert "Widerruf erklären" in response.content.decode()  # вернулись к форме


def test_withdrawal_form_honeypot_redirects():
    tenant = TenantFactory(schema_name="public", slug="wf-hp", name="Shop")
    response = public_views.withdrawal_form(
        _req("post", {"name": "Max", "goods": "X", "website": "bot"}, tenant)
    )
    assert response.status_code == 302
