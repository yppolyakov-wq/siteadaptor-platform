"""T-8.30i: «Neues Geschäft anlegen» в Mini App — регистрация в ТОМ ЖЕ окне.

Фидбэк владельца: кнопка закрывала окно и уводила в чат. Ссылки-токена нет (ревью:
пересланная ссылка привязала бы чужой бизнес к Telegram отправителя) — метку Telegram в
сессию кладёт запрос самой страницы Mini App с подписью; быстрая регистрация передаёт её в
провижининг, кабинет до почты не открывается. План — docs/t8-30i-miniapp-signup-plan-2026-10-21.md.
"""

import json
from importlib import import_module
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from apps.platform_bot import links, miniapp, signup, web_signup
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    UID,
    _auth,
    _init_data,
    _tenant,
    on,
)
from apps.tenants import quickstart_views
from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.test_quick_start import _old_stamp, _post_data

pytestmark = pytest.mark.django_db
TPL = Path(__file__).resolve().parents[3] / "templates" / "platform_bot" / "miniapp.html"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    signup.cache.delete(signup._pending_key(UID))


def _session(request):
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


def _signup_req(uid=UID, lang="ru", **headers):
    hdr = {"HTTP_X_TG_APP": "1"}
    hdr.update(headers)
    req = RequestFactory().post(
        "/tg/app/registrieren/",
        urlencode({"init_data": _init_data(uid=uid, lang=lang)}),
        content_type="application/x-www-form-urlencoded",
        **hdr,
    )
    return _session(req)


def _linked_session(uid=UID, lang="ru"):
    req = _signup_req(uid, lang)
    resp = miniapp.app_signup(req)
    assert resp.status_code == 200, resp.content
    assert json.loads(resp.content)["next"] == "/aktion-starten/"
    return req


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


def test_unlinked_offers_in_app_signup_without_link_token():
    status, body = _auth(uid=990101)
    assert status == 200 and body["error"] == "unlinked"
    assert body["signup"] is True and body["web_url"].endswith("/aktion-starten/")
    assert "signup_url" not in body and "990101" not in body["web_url"]


def test_no_signup_when_cap_reached(monkeypatch):
    monkeypatch.setattr(web_signup, "allowed", lambda uid: False)
    assert _auth(uid=990103)[1]["signup"] is False


def test_restricted_user_is_not_allowed(monkeypatch):
    from apps.platform_bot import rights

    monkeypatch.setattr(rights, "is_restricted", lambda uid: True)
    assert web_signup.allowed(990104) is False


def test_signup_marks_this_browser_only_with_app_header_and_signature():
    req = _linked_session(uid=990105)
    assert req.session[web_signup.SESSION_KEY]["uid"] == 990105
    assert req.session[web_signup.SESSION_KEY]["name"] == "A"
    # Чужой сайт: без заголовка Mini App (нужен CORS-preflight) — отказ.
    no_hdr = _signup_req(990106, HTTP_X_TG_APP="")
    assert miniapp.app_signup(no_hdr).status_code == 403
    assert web_signup.SESSION_KEY not in no_hdr.session
    # Чужой Origin — отказ.
    cross = _signup_req(990107, HTTP_ORIGIN="https://evil.example")
    assert miniapp.app_signup(cross).status_code == 403
    # Без подписи — отказ.
    bad = _session(
        RequestFactory().post(
            "/tg/app/registrieren/",
            "init_data=x",
            content_type="application/x-www-form-urlencoded",
            HTTP_X_TG_APP="1",
        )
    )
    assert miniapp.app_signup(bad).status_code == 403


def test_signup_refused_over_cap(monkeypatch):
    monkeypatch.setattr(web_signup, "allowed", lambda uid: False)
    req = _signup_req(990108)
    assert miniapp.app_signup(req).status_code == 403
    assert web_signup.SESSION_KEY not in req.session


def test_banner_names_the_linked_telegram_account():
    req = _linked_session()
    get = _session(RequestFactory().get("/aktion-starten/"))
    get.session = req.session
    html = quickstart_views.quick_start(get).content.decode()
    assert "data-tg-linked" in html and "„A“" in html
    plain = quickstart_views.quick_start(_session(RequestFactory().get("/aktion-starten/")))
    assert "data-tg-linked" not in plain.content.decode()


def test_linked_submit_passes_telegram_and_no_login_token():
    req = _linked_session(lang="ru")
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
    req = _linked_session(lang="de")
    monkeypatch.setattr(signup, "_rate", lambda *a, **k: True)
    try:
        _sub, resp, delay = _submit(req.session)
        assert resp.status_code == 200 and not delay.called
        assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()
    finally:
        _drop()


def test_linked_submit_over_cap_falls_back_to_error(monkeypatch):
    req = _linked_session(lang="de")
    monkeypatch.setattr(web_signup, "allowed", lambda uid: False)
    try:
        sub, resp, _ = _submit(req.session)
        assert resp.status_code == 200
        assert not Tenant.objects.filter(slug__startswith="baeckerei").exists()
        assert web_signup.SESSION_KEY not in sub.session
    finally:
        _drop()


def test_waiting_in_telegram_mode_shows_done_without_cabinet():
    req = _linked_session(lang="de")
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
    assert '"X-TG-App": "1"' in src and 'credentials: "same-origin"' in src


def test_failed_photo_does_not_burn_quota(monkeypatch):
    """Ревью: лимиты Telegram-регистрации — после проверки фото."""
    from django.core.exceptions import ValidationError

    req = _linked_session(lang="de")
    calls = []
    monkeypatch.setattr(signup, "_rate", lambda *a, **k: calls.append(a) or False)

    def boom(_):
        raise ValidationError("kaputt")

    monkeypatch.setattr("apps.promotions.quick.save_photos", boom)
    sub = _session(
        RequestFactory().post(
            "/aktion-starten/",
            {**_post_data(stamp=_old_stamp()), "photo": _jpeg()},
        )
    )
    sub.session = req.session
    sub.META["REMOTE_ADDR"] = "10.86.0.9"
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        resp = quickstart_views.quick_start(sub)
    assert resp.status_code == 200 and b"kaputt" in resp.content and calls == []


def _jpeg():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("a.jpg", b"\xff\xd8\xff" + b"0" * 64, content_type="image/jpeg")
