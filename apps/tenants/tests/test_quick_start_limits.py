"""T-8.30k: «Veröffentlichen» в Mini App снова «Zu viele Versuche» (фидбэк 2026-10-21).

Причины: лимиты считали ПОПЫТКИ, а не регистрации (суточная корзина Telegram-аккаунта —
1 в сутки — сгорала на первой же неудачной попытке), и все лимиты отвечали одним текстом —
по экрану не понять, какой сработал. Теперь корзины возвращаются, если бизнес не создан;
у каждого лимита свой текст; кнопка показывает «Wird veröffentlicht…».
"""

import uuid
from importlib import import_module
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.db import IntegrityError
from django.test import RequestFactory

from apps.core import ratelimit
from apps.platform_bot import signup, web_signup
from apps.tenants import quickstart_views
from apps.tenants.models import Domain, Tenant
from apps.tenants.tests.test_quick_start import EMAIL, _old_stamp, _post_data

pytestmark = pytest.mark.django_db
TPL = Path(__file__).resolve().parents[3] / "templates" / "tenants" / "quick_start.html"
UID = 770001


@pytest.fixture(autouse=True)
def _private_ratelimit(monkeypatch):
    from django.core.cache.backends.locmem import LocMemCache

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-qs-limits-{uuid.uuid4()}", {}))
    yield
    signup.cache.delete(signup._pending_key(UID))


def _count(scope, ident):
    return ratelimit.cache.get(f"rl:{scope}:{ident}") or 0


def _request(*, linked=True, ip="10.87.0.1", **data):
    req = RequestFactory().post("/aktion-starten/", _post_data(stamp=_old_stamp(), **data))
    req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(req)
    req.META["REMOTE_ADDR"] = ip
    if linked:
        web_signup.remember(req, uid=UID, lang="de", name="A")
    return req


def _submit(req):
    with mock.patch("apps.tenants.tasks.provision_quick.delay"):
        return quickstart_views.quick_start(req)


def _drop():
    for t in Tenant.objects.filter(slug__startswith="baeckerei-mueller"):
        Domain.objects.filter(tenant=t).delete()
        t.delete()


# --- ratelimit.refund ------------------------------------------------------------------


def test_refund_returns_one_attempt_and_never_goes_below_zero():
    assert ratelimit.hit("t", "x", limit=1, window=60) is False
    assert ratelimit.hit("t", "x", limit=1, window=60) is True
    ratelimit.refund("t", "x")
    ratelimit.refund("t", "x")
    ratelimit.refund("t", "x")
    assert _count("t", "x") == 0
    ratelimit.refund("t", "missing")  # нет ключа — без ошибки и без ключа
    assert ratelimit.cache.get("rl:t:missing") is None


# --- корзины считают регистрации, а не попытки ----------------------------------------


def test_failed_provisioning_returns_all_buckets():
    req = _request()
    with mock.patch.object(
        quickstart_views, "start_quick_provisioning", side_effect=IntegrityError
    ):
        resp = _submit(req)
    assert resp.status_code == 200
    assert _count("quick-start", "10.87.0.1") == 0
    assert _count("tgplat-signup", UID) == 0
    assert _count("tgplat-signup-global-unverified", "all") == 0


def test_mini_app_account_may_register_more_than_once_a_day():
    try:
        for i in range(2):
            resp = _submit(_request(subdomain=f"baeckerei-mueller-{i}", ip=f"10.87.1.{i}"))
            assert resp.status_code == 302, resp.content.decode()[:400]
        assert _count("tgplat-signup", UID) == 2
    finally:
        _drop()


# --- у каждого лимита свой текст ------------------------------------------------------


def _assert_message(resp, text):
    html = resp.content.decode()
    assert resp.status_code == 200 and text in html, html[:2000]
    assert "Zu viele Versuche. Bitte später erneut." not in html


def test_account_limit_has_own_message_and_returns_ip_attempt():
    for _ in range(signup.LIMIT_SIGNUP):
        ratelimit.hit("tgplat-signup", str(UID), limit=99, window=86400)
    resp = _submit(_request())
    _assert_message(resp, "diesem Telegram-Konto")
    assert _count("quick-start", "10.87.0.1") == 0
    assert not Tenant.objects.filter(slug__startswith="baeckerei-mueller").exists()


def test_mail_limit_has_own_message_and_returns_account_attempt():
    import hashlib

    key = hashlib.sha256(EMAIL.encode()).hexdigest()
    for _ in range(signup.LIMIT_MAIL):
        ratelimit.hit("tgplat-signup-mail", key, limit=99, window=86400)
    resp = _submit(_request())
    _assert_message(resp, "diese E-Mail-Adresse")
    assert _count("tgplat-signup", UID) == 0
    assert _count("quick-start", "10.87.0.1") == 0


def test_ip_limit_has_own_message():
    for _ in range(5):
        ratelimit.hit("quick-start", "10.87.0.1", limit=99, window=3600)
    resp = _submit(_request(linked=False))
    _assert_message(resp, "aus diesem Netzwerk")


# --- кнопка ---------------------------------------------------------------------------


def test_publish_button_shows_progress_and_blocks_double_submit():
    src = TPL.read_text()
    assert "data-qs-busy" in src and "Wird veröffentlicht" in src


def test_unexpected_error_keeps_ip_attempt():
    req = _request(linked=False)
    with mock.patch.object(
        quickstart_views, "start_quick_provisioning", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(RuntimeError):
            _submit(req)
    assert _count("quick-start", "10.87.0.1") == 1


# --- повторная отправка той же формы ---------------------------------------------------


def test_double_submit_returns_first_result_without_second_business():
    stamp = _old_stamp()
    req1 = _request()
    req1.POST = req1.POST.copy()
    req1.POST["stamp"] = stamp
    req2 = _request(ip="10.87.0.2")
    req2.POST = req2.POST.copy()
    req2.POST["stamp"] = stamp
    try:
        r1 = _submit(req1)
        r2 = _submit(req2)
        assert r1.status_code == 302 and r2.status_code == 302
        assert r1["Location"] == r2["Location"]
        assert Tenant.objects.filter(slug__startswith="baeckerei-mueller").count() == 1
        slug = r1["Location"].strip("/").split("/")[-1]
        assert slug in req2.session[quickstart_views.SESSION_KEY]
        assert _count("tgplat-signup", UID) == 1
        assert _count("quick-start", "10.87.0.2") == 0
    finally:
        _drop()


def test_failed_first_submit_frees_the_form_for_retry():
    stamp = _old_stamp()
    req = _request()
    req.POST = req.POST.copy()
    req.POST["stamp"] = stamp
    with mock.patch.object(
        quickstart_views, "start_quick_provisioning", side_effect=IntegrityError
    ):
        assert _submit(req).status_code == 200
    key, done = quickstart_views._claim_submit(stamp)
    assert done is None and key.startswith("qs-submit:")


def test_busy_submit_waits_then_reports_in_progress(monkeypatch):
    stamp = _old_stamp()
    monkeypatch.setattr(quickstart_views, "SUBMIT_WAIT", 0)
    key, _done = quickstart_views._claim_submit(stamp)
    try:
        req = _request()
        req.POST = req.POST.copy()
        req.POST["stamp"] = stamp
        resp = _submit(req)
        assert resp.status_code == 200
        assert "wird gerade angelegt" in resp.content.decode()
        assert not Tenant.objects.filter(slug__startswith="baeckerei-mueller").exists()
    finally:
        quickstart_views.cache.delete(key)
