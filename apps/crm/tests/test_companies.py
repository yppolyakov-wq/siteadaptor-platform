"""CO-1 (корпоративный контур v1): справочник компаний + привязка клиентов."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.crm import views
from apps.crm.forms import CompanyForm, CustomerForm
from apps.crm.models import Company
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/crm/firmen/", data=None):
    import uuid

    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o{uuid.uuid4().hex[:10]}", email="o@test.de", password="pw12345678"
    )
    return request


def _company_data(**overrides):
    data = {
        "name": "Müller GmbH",
        "vat_id": "DE123456789",
        "street": "Hauptstr. 5",
        "postal_code": "40721",
        "city": "Hilden",
        "email": "buero@mueller.de",
        "phone": "",
        "discount_percent": "10",
        "note": "",
    }
    data.update(overrides)
    return data


def test_company_create_list_edit_delete():
    resp = views.company_create(_req("post", "/crm/firmen/neu/", _company_data()))
    assert resp.status_code == 302
    company = Company.objects.get(name="Müller GmbH")

    body = views.company_list(_req()).content.decode()
    assert "Müller GmbH" in body and "DE123456789" in body

    resp = views.company_detail(
        _req("post", f"/crm/firmen/{company.pk}/", _company_data(city="Solingen")),
        pk=company.pk,
    )
    assert resp.status_code == 302
    company.refresh_from_db()
    assert company.city == "Solingen"

    # Удаление: клиент остаётся, лишь отвязывается (SET_NULL).
    customer = Customer.objects.create(name="Frau Müller", company=company)
    resp = views.company_delete(_req("post", f"/crm/firmen/{company.pk}/loeschen/"), pk=company.pk)
    assert resp.status_code == 302
    assert not Company.objects.exists()
    customer.refresh_from_db()
    assert customer.company is None


def test_customer_form_links_company_and_chips_render():
    company = Company.objects.create(name="Bäcker AG")
    data = {
        "name": "Herr Korn",
        "email": "korn@test.de",
        "phone": "",
        "note": "",
        "tags_input": "",
        "company": str(company.pk),
    }
    resp = views.customer_create(_req("post", "/crm/new/", data))
    assert resp.status_code == 302
    customer = Customer.objects.get(name="Herr Korn")
    assert customer.company == company

    # Чип компании — в списке и на карточке 360°; компания видит клиента.
    assert "Bäcker AG" in views.customer_list(_req(path="/crm/")).content.decode()
    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    assert "Bäcker AG" in body.content.decode()
    body = views.company_detail(_req(path=f"/crm/firmen/{company.pk}/"), pk=company.pk)
    assert "Herr Korn" in body.content.decode()


def test_customer_form_hides_company_when_directory_empty():
    """Пустой справочник → селект не показывается (форма прежняя); появляется
    с первой компанией."""
    assert "company" not in CustomerForm().fields
    Company.objects.create(name="Erste GmbH")
    assert "company" in CustomerForm().fields


def test_invoice_recipient_multiline():
    company = Company.objects.create(
        name="Müller GmbH",
        street="Hauptstr. 5",
        postal_code="40721",
        city="Hilden",
        vat_id="DE123456789",
    )
    assert company.invoice_recipient == (
        "Müller GmbH\nHauptstr. 5\n40721 Hilden\nUSt-IdNr: DE123456789"
    )
    assert Company.objects.create(name="Nur Name").invoice_recipient == "Nur Name"


def test_discount_capped_at_50():
    form = CompanyForm(_company_data(discount_percent="60"))
    assert not form.is_valid() and "discount_percent" in form.errors
    assert CompanyForm(_company_data(discount_percent="50")).is_valid()
