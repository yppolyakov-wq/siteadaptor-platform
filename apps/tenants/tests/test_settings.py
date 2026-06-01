"""Тесты настроек бизнеса и правовых текстов."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.promotions import public_views
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory


def _attach(request, user=None):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if user is not None:
        request.user = user
    return request


def test_impressum_generated_from_fields():
    t = Tenant(name="Bäckerei X", address="Hauptstr. 1, 40721 Hilden", contact_email="b@x.de")
    text = t.impressum_text()
    assert "Bäckerei X" in text
    assert "Hauptstr. 1" in text
    assert "b@x.de" in text


def test_impressum_freetext_has_priority():
    t = Tenant(name="X", impressum="Mein eigenes Impressum")
    assert t.impressum_text() == "Mein eigenes Impressum"


def test_privacy_and_withdrawal_have_templates():
    t = Tenant(name="X", contact_email="b@x.de")
    assert "Datenschutz" in t.privacy_text()
    assert "Widerruf" in t.withdrawal_text() or "Storn" in t.withdrawal_text()


@pytest.mark.django_db
def test_settings_view_saves():
    tenant = TenantFactory()
    user = get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )
    req = _attach(
        RequestFactory().post("/dashboard/settings/", {"name": "Neuer Name", "city": "Hilden"}),
        user,
    )
    req.tenant = tenant
    resp = core_views.settings_view(req)
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.name == "Neuer Name"


@pytest.mark.django_db
def test_impressum_page_renders():
    tenant = TenantFactory(name="Bäckerei Y")
    req = _attach(RequestFactory().get("/impressum/"))
    req.tenant = tenant
    resp = public_views.impressum(req)
    assert resp.status_code == 200
    assert b"Impressum" in resp.content
    assert "Bäckerei Y".encode() in resp.content
