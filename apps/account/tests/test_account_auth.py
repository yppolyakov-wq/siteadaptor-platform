"""CA1: magic-link вход в ЛК клиента на витрине + гейтинг модуля."""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.account import auth, views
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/konto/", data=None, session=None, disabled=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = TenantFactory.build(
        business_type="restaurant", disabled_modules=disabled or []
    )
    return request


def test_login_get_renders_when_module_active():
    body = views.login_view(_req()).content.decode()
    assert "konto" in body.lower() or "account" in body.lower() or "Konto" in body


def test_gated_404_when_module_disabled():
    with pytest.raises(Http404):
        views.login_view(_req(disabled=["customer_account"]))


def test_magic_link_login_creates_session_and_customer():
    token = auth.issue_magic_link("gast@test.de")
    assert token
    req = _req()
    auth.login(req, "gast@test.de")
    assert auth.current_customer(req) is not None
    assert Customer.objects.filter(email__iexact="gast@test.de").exists()


def test_consume_is_one_time():
    token = auth.issue_magic_link("a@test.de")
    assert auth.consume_magic_link(token)["email"] == "a@test.de"
    assert auth.consume_magic_link(token) is None  # второй раз — нет


def test_login_reuses_existing_customer():
    existing = Customer.objects.create(name="Max", email="max@test.de")
    req = _req()
    auth.login(req, "max@test.de")
    assert str(existing.pk) == req.session[auth.SESSION_KEY]


def test_account_home_redirects_when_anonymous():
    resp = views.account_home(_req())
    assert resp.status_code == 302 and "login" in resp.url
