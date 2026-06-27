"""SE-1a: кнопка «Edit design» на витрине — только владельцу (Django-аутентиф.),
скрыта для посетителей и в режиме превью (?preview=1)."""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, user, path="/"):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = user
    return req


def _tenant():
    return TenantFactory(schema_name="public", slug="oe", name="OE")


def test_owner_sees_edit_button():
    body = public_views.storefront_home(
        _req(_tenant(), SimpleNamespace(is_authenticated=True))
    ).content.decode()
    assert "data-owner-edit" in body


def test_visitor_does_not_see_edit_button():
    body = public_views.storefront_home(_req(_tenant(), AnonymousUser())).content.decode()
    assert "data-owner-edit" not in body


def test_edit_button_hidden_in_preview():
    body = public_views.storefront_home(
        _req(_tenant(), SimpleNamespace(is_authenticated=True), path="/?preview=1")
    ).content.decode()
    assert "data-owner-edit" not in body
