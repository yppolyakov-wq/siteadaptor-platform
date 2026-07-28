"""CA3: профиль ЛК + согласие на маркетинг + DSGVO (экспорт/удаление)."""

import json
import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.account import auth, views
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, customer=None):
    request = getattr(RequestFactory(), method)("/konto/profil/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.4"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="restaurant")
    if customer is not None:
        request.session[auth.SESSION_KEY] = str(customer.pk)
    return request


def test_profile_save_updates_name_and_marketing():
    c = Customer.objects.create(name="Alt", email="a@test.de")
    resp = views.profile_view(_req("post", {"name": "Neu", "phone": "0151", "marketing": "on"}, c))
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.name == "Neu" and c.phone == "0151"
    assert c.marketing_opt_in and not c.unsubscribed


def test_profile_unchecking_marketing_clears_opt_in():
    c = Customer.objects.create(name="A", email="a@test.de", marketing_opt_in=True)
    views.profile_view(_req("post", {"name": "A", "marketing": ""}, c))
    c.refresh_from_db()
    assert c.marketing_opt_in is False


def test_profile_birthday_saved_and_cleared():
    """PMS-B2: гость сам дарит/забирает дату рождения; мусор не рушит форму."""
    from datetime import date

    c = Customer.objects.create(name="B", email="b@test.de")
    views.profile_view(_req("post", {"name": "B", "birthday": "1990-07-15"}, c))
    c.refresh_from_db()
    assert c.birthday == date(1990, 7, 15)

    views.profile_view(_req("post", {"name": "B", "birthday": "kaputt"}, c))
    c.refresh_from_db()
    assert c.birthday == date(1990, 7, 15)  # кривая дата — прежнее значение

    views.profile_view(_req("post", {"name": "B", "birthday": ""}, c))
    c.refresh_from_db()
    assert c.birthday is None


def test_export_returns_json_with_customer():
    c = Customer.objects.create(name="Max", email="max@test.de")
    body = views.export_data(_req(customer=c)).content.decode()
    assert json.loads(body)["email"] == "max@test.de"


def test_delete_anonymizes_and_logs_out():
    c = Customer.objects.create(name="Max", email="max@test.de")
    req = _req("post", customer=c)
    resp = views.delete_account(req)
    assert resp.status_code == 302
    c.refresh_from_db()
    assert c.email == "" and not c.marketing_opt_in
    assert auth.SESSION_KEY not in req.session


def test_profile_opt_in_records_consent_timestamp():
    """PMS-аудит 2026-07-27: момент согласия (UWG §7) фиксируется при включении."""
    c = Customer.objects.create(name="G", email="g@test.de")
    views.profile_view(_req("post", {"name": "G", "marketing": "on"}, c))
    c.refresh_from_db()
    assert c.marketing_opt_in and c.marketing_opt_in_at is not None
