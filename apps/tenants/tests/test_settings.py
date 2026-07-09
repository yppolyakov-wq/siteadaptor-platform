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
def test_settings_page_renders_all_form_fields():
    """Регресс-замок бага потери данных: КАЖДОЕ поле формы должно рендериться на
    странице, иначе на Save оно приходит пустым и затирает БД (small_business/НДС и т.п.)."""
    from apps.tenants.forms import BusinessSettingsForm

    tenant = TenantFactory()
    user = get_user_model().objects.create_user("r", "r@test.de", "pw12345678")
    req = _attach(RequestFactory().get("/dashboard/settings/"), user)
    req.tenant = tenant
    resp = core_views.settings_view(req)
    assert resp.status_code == 200
    html = resp.content.decode()
    missing = [f for f in BusinessSettingsForm.Meta.fields if f"id_{f}" not in html]
    assert not missing, f"поля формы не выводятся (будут стёрты на Save): {missing}"


@pytest.mark.django_db
def test_settings_view_preserves_previously_dropped_fields():
    """Ранее не выводимые поля не должны обнуляться при сохранении формы."""
    tenant = TenantFactory(small_business=True, tax_number="DE-42", voucher_max_percent=25)
    user = get_user_model().objects.create_user("p", "p@test.de", "pw12345678")
    # POST как из отрисованной формы (чекбоксы включены, значения переданы).
    data = {
        "name": tenant.name,
        "small_business": "on",
        "tax_number": "DE-42",
        "owner_digest_enabled": "on",
        "voucher_max_percent": "25",
        "service_area_plz": "40724",
    }
    req = _attach(RequestFactory().post("/dashboard/settings/", data), user)
    req.tenant = tenant
    resp = core_views.settings_view(req)
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.small_business is True  # НДС-статус не слетел
    assert tenant.tax_number == "DE-42"
    assert tenant.owner_digest_enabled is True
    assert tenant.voucher_max_percent == 25
    assert tenant.service_area_plz == "40724"


@pytest.mark.django_db
def test_impressum_page_renders():
    tenant = TenantFactory(name="Bäckerei Y")
    req = _attach(RequestFactory().get("/impressum/"))
    req.tenant = tenant
    resp = public_views.impressum(req)
    assert resp.status_code == 200
    assert b"Impressum" in resp.content
    assert "Bäckerei Y".encode() in resp.content
