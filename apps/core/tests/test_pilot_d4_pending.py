"""KA-D4 (решение владельца 2026-10-23): витрина не показывается, пока владелец не
подтвердил почту (`Tenant.email_pending`). Кабинет, вход по ссылке, Mini App,
вебхуки и превью для самого владельца работают."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import PendingStorefrontMiddleware
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _run(path, *, pending=True, user=None, method="get"):
    request = getattr(RequestFactory(), method)(path)
    request.tenant = TenantFactory.build(email_pending=pending)
    request.user = user or AnonymousUser()
    return PendingStorefrontMiddleware(lambda r: HttpResponse("shop"))(request)


def test_visitor_gets_coming_soon_with_noindex():
    response = _run("/")
    assert response.status_code == 503
    assert b"noindex" in response.content
    assert response["X-Robots-Tag"].startswith("noindex")


def test_confirmed_tenant_unchanged():
    assert _run("/", pending=False).content == b"shop"


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/",
        "/start/abc/",
        "/anmelden/link/",
        "/tg/start/abc/",
        "/tg/secret123/",
        "/accounts/login/",
        "/health/",
        "/media/x.jpg",
        "/robots.txt",
    ],
)
def test_service_paths_stay_open(path):
    assert _run(path).content == b"shop"


def test_post_requests_pass_through():
    """Вебхуки (Stripe, Telegram) — POST; их не трогаем."""
    assert _run("/sortiment/", method="post").content == b"shop"


def test_owner_sees_own_storefront():
    user = get_user_model().objects.create_user(f"o-{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert _run("/", user=user).content == b"shop"


def test_public_schema_untouched():
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(schema_name="public", email_pending=True)
    request.user = AnonymousUser()
    assert PendingStorefrontMiddleware(lambda r: HttpResponse("ok"))(request).content == b"ok"


def test_stay_price_feed_hidden_but_ical_open():
    assert _run("/stays/feed.json").status_code == 503
    assert _run("/stays/ical/tok.ics").content == b"shop"
