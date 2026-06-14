"""M22c: платформенная поддержка — сервисы + кабинет «Hilfe», скоупинг по тенанту."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.support import services, views
from apps.support.models import SupportMessage, SupportThread
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/help/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant or TenantFactory()
    return request


# --- сервисы ----------------------------------------------------------------------


def test_open_thread_and_platform_reply():
    thread = services.open_thread(tenant=TenantFactory(), subject="Hilfe", body="Frage")
    assert thread.messages.get().author_role == "owner" and thread.unread_for_platform
    services.add_message(thread, body="Antwort", author_role=SupportMessage.AUTHOR_PLATFORM)
    thread.refresh_from_db()
    assert thread.unread_for_owner and not thread.unread_for_platform


def test_owner_reply_reopens_resolved():
    thread = services.open_thread(tenant=TenantFactory(), subject="X", body="hi")
    thread.status = "resolved"
    thread.save(update_fields=["status"])
    services.add_message(thread, body="noch offen", author_role=SupportMessage.AUTHOR_OWNER)
    thread.refresh_from_db()
    assert thread.status == "open"


# --- кабинет «Hilfe» --------------------------------------------------------------


def test_cabinet_create_and_list():
    tenant = TenantFactory()
    resp = views.help_list(_req("post", data={"subject": "Bug", "body": "kaputt"}, tenant=tenant))
    assert resp.status_code == 302
    assert SupportThread.objects.get(tenant=tenant).subject == "Bug"
    assert "Bug" in views.help_list(_req(tenant=tenant)).content.decode()


def test_cabinet_thread_reply_scoped_to_tenant():
    tenant = TenantFactory()
    thread = services.open_thread(tenant=tenant, subject="Q", body="hi")
    views.help_thread(
        _req("post", f"/dashboard/help/{thread.pk}/", {"body": "Danke"}, tenant=tenant),
        pk=thread.pk,
    )
    thread.refresh_from_db()
    assert thread.messages.filter(author_role="owner").count() == 2
    # чужой тенант не видит чужой тред → 404
    with pytest.raises(Http404):
        views.help_thread(_req(tenant=TenantFactory()), pk=thread.pk)
