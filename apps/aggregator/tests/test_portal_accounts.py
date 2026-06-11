"""P2.3a: magic-link вход клиента на порталах.

Email/IP в тестах — uuid: счётчики rate-limit и токены живут в общем Redis
дольше теста, уникальность изолирует тесты и повторные прогоны.
"""

import uuid

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import account_views, auth, tasks
from apps.aggregator.models import AggregatorPortal, PortalUser

pytestmark = pytest.mark.django_db


def _email():
    return f"{uuid.uuid4().hex}@kunde.test"


def _portal(**kw):
    defaults = {
        "kind": "city",
        "city": "München",
        "title": {"de": "Angebote München"},
        "is_active": True,
    }
    defaults.update(kw)
    host = defaults.pop("host", "muenchen.siteadaptor.de")
    portal, _ = AggregatorPortal.objects.get_or_create(host=host, defaults=defaults)
    return portal


def _req(method="get", path="/konto/login/", data=None, portal=None):
    factory = getattr(RequestFactory(), method)
    request = factory(path, data or {}, HTTP_X_FORWARDED_FOR=uuid.uuid4().hex)
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = portal if portal is not None else _portal()
    return request


# --- auth: токены --------------------------------------------------------------


def test_issue_and_consume_roundtrip():
    email = _email()
    token = auth.issue_magic_link(email)
    assert token
    assert auth.consume_magic_link(token) == {"email": email}


def test_token_is_single_use():
    token = auth.issue_magic_link(_email())
    assert auth.consume_magic_link(token) is not None
    assert auth.consume_magic_link(token) is None  # второй переход не работает


def test_raw_token_not_stored_in_cache():
    token = auth.issue_magic_link(_email())
    assert cache.get(f"ml_token:{token}") is None  # ключ — только хэш
    assert cache.get(f"ml_token:{auth._hash(token)}") is not None


def test_email_rate_limit_stops_issuing():
    email = _email()
    for _ in range(auth.EMAIL_RL_LIMIT):
        assert auth.issue_magic_link(email)
    assert auth.issue_magic_link(email) is None


def test_garbage_token_rejected():
    assert auth.consume_magic_link("nonsense") is None
    assert auth.consume_magic_link("") is None


# --- вьюхи ----------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_login_post_sends_link_and_shows_check_inbox(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_magic_link_email, "delay", lambda **kw: sent.append(kw))
    email = _email()
    resp = account_views.login_view(_req("post", data={"email": email}))
    assert resp.status_code == 200
    assert b"Check your inbox" in resp.content
    assert len(sent) == 1
    assert sent[0]["email"] == email
    assert "/konto/login/verify/?t=" in sent[0]["url"]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_login_response_identical_for_honeypot(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_magic_link_email, "delay", lambda **kw: sent.append(kw))
    resp = account_views.login_view(_req("post", data={"email": _email(), "website": "spam"}))
    assert resp.status_code == 200
    assert b"Check your inbox" in resp.content  # ответ тот же
    assert sent == []  # но письма нет


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_login_ip_rate_limit_silent(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_magic_link_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal(host="rl.siteadaptor.de")
    ip = uuid.uuid4().hex
    for _ in range(account_views.IP_RL_LIMIT + 1):
        request = RequestFactory().post(
            "/konto/login/", {"email": _email()}, HTTP_X_FORWARDED_FOR=ip
        )
        SessionMiddleware(lambda r: None).process_request(request)
        request.portal = portal
        resp = account_views.login_view(request)
        assert resp.status_code == 200  # ответ всегда одинаковый
    assert len(sent) == account_views.IP_RL_LIMIT  # сверх лимита — без письма


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_verify_logs_in_and_creates_user():
    email = _email()
    token = auth.issue_magic_link(email)
    request = _req("get", f"/konto/login/verify/?t={token}", data={"t": token})
    resp = account_views.login_verify(request)
    assert resp.status_code == 302
    assert resp.url == "/konto/"
    user = PortalUser.objects.get(email=email)
    assert request.session[auth.SESSION_KEY] == user.pk
    assert user.last_login_at is not None


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_verify_invalid_token_400():
    resp = account_views.login_verify(_req("get", "/konto/login/verify/", data={"t": "bad"}))
    assert resp.status_code == 400
    assert b"Link expired" in resp.content


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_account_requires_login():
    resp = account_views.account(_req("get", "/konto/"))
    assert resp.status_code == 302
    assert resp.url == "/konto/login/"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_account_shows_email_and_logout_clears_session():
    email = _email()
    user = PortalUser.objects.create(email=email)
    request = _req("get", "/konto/")
    request.session[auth.SESSION_KEY] = user.pk
    resp = account_views.account(request)
    assert resp.status_code == 200
    assert email.encode() in resp.content

    request = _req("post", "/konto/logout/")
    request.session[auth.SESSION_KEY] = user.pk
    resp = account_views.logout_view(request)
    assert resp.status_code == 302
    assert auth.SESSION_KEY not in request.session


def test_inactive_user_not_resolved():
    user = PortalUser.objects.create(email=_email(), is_active=False)
    request = _req("get", "/konto/")
    request.session[auth.SESSION_KEY] = user.pk
    assert auth.current_portal_user(request) is None


def test_send_magic_link_email_task_sends():
    tasks.send_magic_link_email(email="k@test.de", url="https://x.test/konto/login/verify/?t=abc")
    assert len(mail.outbox) == 1
    assert "https://x.test/konto/login/verify/?t=abc" in mail.outbox[0].body
    assert mail.outbox[0].to == ["k@test.de"]
