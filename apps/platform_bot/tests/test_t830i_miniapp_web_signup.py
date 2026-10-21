"""T-8.30i: «Neues Geschäft anlegen» в Mini App — регистрация в ТОМ ЖЕ окне.

Фидбэк владельца: кнопка закрывала окно и уводила в чат. Теперь `unlinked` несёт
одноразовую ссылку на быструю регистрацию; метка в сессии публичного хоста передаёт
Telegram-пользователя в провижининг (чат станет владельцем после подтверждения почты),
кабинет до почты не открывается. План — docs/t8-30i-miniapp-signup-plan-2026-10-21.md.
"""

from importlib import import_module
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory

from apps.platform_bot import links, signup, web_signup
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    UID,
    _auth,
    _tenant,
    on,
)
from apps.tenants import quickstart_views
from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.test_quick_start import _old_stamp, _post_data

pytestmark = pytest.mark.django_db
TPL = Path(__file__).resolve().parents[3] / "templates" / "platform_bot" / "miniapp.html"


@pytest.fixture(autouse=True)
def _cache(on):  # noqa: F811
    web_signup.cache = on
    yield
    web_signup.cache = cache
    signup.cache.delete(signup._pending_key(UID))


def _session(request):
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def _token_from(body) -> str:
    return body["signup_url"].rstrip("/").rsplit("/", 1)[-1]


def _linked_session(raw):
    req = _session(RequestFactory().post(f"/aktion-starten/tg/{raw}/"))
    req.META["REMOTE_ADDR"] = "10.86.0.1"
    resp = quickstart_views.quick_start_tg(req, raw)
    return req, resp


def _submit(session, ip="10.86.0.2"):
    req = _session(RequestFactory().post("/aktion-starten/", _post_data(stamp=_old_stamp())))
    req.session = session
    req.META["REMOTE_ADDR"] = ip
    with mock.patch("apps.tenants.tasks.provision_quick.delay") as delay:
        resp = quickstart_views.quick_start(req)
    return req, resp, delay


def _drop(slug="baeckerei-mueller-soehne"):
    for t in Tenant.objects.filter(slug__startswith=slug):
        Domain.objects.filter(tenant=t).delete()
        t.delete()


def test_unlinked_carries_one_time_signup_url_without_uid():
    status, body = _auth(uid=990101)
    assert status == 200 and body["error"] == "unlinked"
    url = body["signup_url"]
    assert url.startswith("https://") and "/aktion-starten/tg/" in url
    assert "990101" not in url and "web_url" not in body
    assert web_signup.peek(_token_from(body))["uid"] == 990101


def test_replay_kills_previous_signup_token():
    from apps.platform_bot import miniapp
    from apps.platform_bot.tests.test_t830_miniapp_views import _init_data, _post

    init = _init_data(uid=990102)
    first = _post(miniapp.app_auth, {"init_data": init})[1]
    second = _post(miniapp.app_auth, {"init_data": init})[1]
    assert web_signup.peek(_token_from(first)) is None
    assert web_signup.peek(_token_from(second))["uid"] == 990102


def test_no_signup_url_when_cap_reached(monkeypatch):
    monkeypatch.setattr(web_signup, "allowed", lambda uid: False)
    body = _auth(uid=990103)[1]
    assert body["error"] == "unlinked" and not body.get("signup_url")


def test_restricted_user_is_not_allowed(monkeypatch):
    from apps.platform_bot import rights

    monkeypatch.setattr(rights, "is_restricted", lambda uid: True)
    assert web_signup.allowed(990104) is False


def test_get_does_not_consume_post_consumes_once():
    raw = web_signup.issue(990105, "ru")
    get = _session(RequestFactory().get(f"/aktion-starten/tg/{raw}/"))
    resp = quickstart_views.quick_start_tg(get, raw)
    assert resp.status_code == 200 and b'method="post"' in resp.content
    assert resp["Cache-Control"] == "no-store" and resp["Referrer-Policy"] == "no-referrer"
    assert web_signup.peek(raw) is not None
    req, resp = _linked_session(raw)
    assert resp.status_code == 302 and resp.url == "/aktion-starten/"
    assert req.session[web_signup.SESSION_KEY]["uid"] == 990105
    assert web_signup.peek(raw) is None
    with pytest.raises(Http404):
        _linked_session(raw)
    with pytest.raises(Http404):
        quickstart_views.quick_start_tg(_session(RequestFactory().get("/")), "nope")


def test_banner_on_form_when_linked():
    req, _ = _linked_session(web_signup.issue(UID, "de"))
    get = _session(RequestFactory().get("/aktion-starten/"))
    get.session = req.session
    html = quickstart_views.quick_start(get).content.decode()
    assert "data-tg-linked" in html
    plain = quickstart_views.quick_start(_session(RequestFactory().get("/aktion-starten/")))
    assert "data-tg-linked" not in plain.content.decode()


def test_linked_submit_passes_telegram_and_no_login_token():
    req, _ = _linked_session(web_signup.issue(UID, "ru"))
    try:
        with mock.patch("apps.core.owner_login.issue_token") as issue:
            sub, resp, delay = _submit(req.session)
        tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
        assert resp.status_code == 302
        assert not issue.called
        marker = tenant.site_config["notify"]["pending_tg_owner"]
        assert marker["uid"] == UID and marker["lang"] == "ru"
        assert web_signup.SESSION_KEY not in sub.session
        entry = sub.session[quickstart_views.SESSION_KEY][tenant.slug]
        assert entry["tg"] is True and "token" not in entry
        assert signup.cache.get(signup._pending_key(UID))
    finally:
        _drop()


def test_unlinked_submit_unchanged():
    req = _session(RequestFactory().get("/"))
    try:
        sub, resp, _ = _submit(req.session)
        tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
        assert "pending_tg_owner" not in (tenant.site_config.get("notify") or {})
        assert "token" in sub.session[quickstart_views.SESSION_KEY][tenant.slug]
    finally:
        _drop()


def test_linked_submit_respects_shared_bot_limit(monkeypatch):
    req, _ = _linked_session(web_signup.issue(UID, "de"))
    monkeypatch.setattr(signup, "_rate", lambda *a, **k: True)
    try:
        _sub, resp, delay = _submit(req.session)
        assert resp.status_code == 200 and not delay.called
        assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()
    finally:
        _drop()


def test_linked_submit_over_cap_falls_back_to_error(monkeypatch):
    req, _ = _linked_session(web_signup.issue(UID, "de"))
    monkeypatch.setattr(web_signup, "allowed", lambda uid: False)
    try:
        sub, resp, _ = _submit(req.session)
        assert resp.status_code == 200
        assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()
        assert web_signup.SESSION_KEY not in sub.session
    finally:
        _drop()


def test_waiting_in_telegram_mode_shows_done_without_cabinet():
    req, _ = _linked_session(web_signup.issue(UID, "de"))
    try:
        sub, _resp, _ = _submit(req.session)
        tenant = Tenant.objects.get(slug="baeckerei-mueller-soehne")
        Tenant.objects.filter(pk=tenant.pk).update(provisioning_status=Tenant.PROVISIONING_READY)
        cache.set(f"quick_promo:{tenant.pk}", "abc", 60)
        poll = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/?poll=1"))
        poll.session = sub.session
        data = quickstart_views.quick_waiting(poll, slug=tenant.slug)
        assert b"fertig=1" in data.content and b"/start/" not in data.content
        done = _session(RequestFactory().get(f"/aktion-starten/{tenant.slug}/?fertig=1"))
        done.session = sub.session
        resp = quickstart_views.quick_waiting(done, slug=tenant.slug)
        html = resp.content.decode()
        assert resp.status_code == 200 and "data-tg-done" in html
        assert "/start/" not in html and "i***@krume.test" in html
    finally:
        cache.delete("quick_promo:" + str(tenant.pk)) if "tenant" in dir() else None
        _drop()


def test_email_confirmation_binds_chat_then_mini_app_opens_business():
    import time

    from django.contrib.auth import get_user_model
    from django_tenants.utils import schema_context

    from apps.core.models import Membership

    t = _tenant()
    t.email_pending = True
    t.site_config = {
        "notify": {"pending_tg_owner": {"uid": UID, "lang": "de", "at": int(time.time())}}
    }
    t.save()
    assert _auth()[1]["error"] == "pending"
    with schema_context(t.schema_name):
        user = get_user_model().objects.create_user(username="i-owner", password="pw12345678")
        Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert links.complete_pending(t)[0] == "bound"
    body = _auth()[1]
    assert "/tg/start/" in body.get("next", "")


def test_page_opens_signup_in_same_window():
    src = TPL.read_text()
    assert "data-web-signup" not in src
    assert 'toBot("neu")' not in src
    assert "signup_url" in src
