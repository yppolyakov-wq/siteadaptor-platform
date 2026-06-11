"""P2.3d: центральная (от)подписка от писем бизнесов в /konto/."""

import uuid

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator import account_views, auth, tasks
from apps.aggregator.models import AggregatorPortal, PortalUser
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _portal_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def _email():
    return f"{uuid.uuid4().hex}@kunde.test"


def _req(method="get", path="/konto/", data=None, user=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    portal, _ = AggregatorPortal.objects.get_or_create(
        host="muenchen.siteadaptor.de",
        defaults={"kind": "city", "city": "München", "title": {"de": "Angebote München"}},
    )
    request.portal = portal
    if user is not None:
        request.session[auth.SESSION_KEY] = user.pk
    return request


def test_sync_sets_unsubscribed_across_tenants():
    tenant = TenantFactory(schema_name="public")
    email = _email()
    Customer.objects.create(name="K", email=email)
    Customer.objects.create(name="Other", email=_email())

    assert tasks.sync_marketing_opt_out(email, True, tenants=[tenant]) == 1
    assert Customer.objects.get(email=email).unsubscribed is True
    assert Customer.objects.exclude(email=email).get().unsubscribed is False

    assert tasks.sync_marketing_opt_out(email.upper(), False, tenants=[tenant]) == 1
    assert Customer.objects.get(email=email).unsubscribed is False  # case-insensitive


def test_toggle_flips_flag_and_enqueues(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.apply_marketing_opt_out, "delay", lambda **kw: sent.append(kw))
    user = PortalUser.objects.create(email=_email())

    resp = account_views.notifications_toggle(_req("post", user=user))
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.marketing_opt_out is True
    assert sent[-1]["opt_out"] is True
    assert sent[-1]["email"] == user.email

    account_views.notifications_toggle(_req("post", user=user))
    user.refresh_from_db()
    assert user.marketing_opt_out is False  # обратное переключение
    assert sent[-1]["opt_out"] is False


def test_toggle_requires_login(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.apply_marketing_opt_out, "delay", lambda **kw: sent.append(kw))
    resp = account_views.notifications_toggle(_req("post"))
    assert resp.status_code == 302
    assert resp.url == "/konto/login/"
    assert sent == []


def test_account_page_shows_unsubscribe_state(monkeypatch):
    from apps.aggregator import account_services

    monkeypatch.setattr(account_services, "reservations_for_email", lambda email, **kw: [])
    user = PortalUser.objects.create(email=_email())
    body = account_views.account(_req(user=user)).content.decode()
    assert "Unsubscribe from all" in body

    user.marketing_opt_out = True
    user.save(update_fields=["marketing_opt_out"])
    body = account_views.account(_req(user=user)).content.decode()
    assert "Subscribe again" in body
