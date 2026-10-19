"""T-8.10g (G-2): кнопка «✨ Antwort vorschlagen» в треде и её эндпоинты."""

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from apps.core.i18n_cabinet import CABINET_PREFIXES
from apps.inbox import ai_reply, services, tasks, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _user():
    o = uuid.uuid4().hex[:8]
    return get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )


def _req(method="get", path="/dashboard/inbox/", user=None, data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = tenant or TenantFactory.build(disabled_modules=[])
    return request


def _conv():
    return services.start_conversation(subject="Frage", body="Habt ihr Brot?", email="a@t.de")


def _json(resp):
    return json.loads(resp.content)


def test_start_anonymous_redirects_to_login():
    conv = _conv()
    resp = views.reply_draft_start(_req("post", user=AnonymousUser()), pk=conv.pk)
    assert resp.status_code == 302 and "login" in resp["Location"]


def test_start_get_is_405(ai_on):
    conv = _conv()
    assert views.reply_draft_start(_req("get"), pk=conv.pk).status_code == 405


def test_start_foreign_thread_404(ai_on):
    with pytest.raises(Http404):
        views.reply_draft_start(_req("post"), pk=uuid.uuid4())


def test_start_disabled_returns_code_and_thread_has_no_button(settings):
    settings.AI_ENABLED = False
    conv = _conv()
    assert _json(views.reply_draft_start(_req("post"), pk=conv.pk)) == {"code": "disabled"}
    html = views.thread(_req("get"), pk=conv.pk).content.decode()
    assert "data-ai-reply-box" not in html


def test_thread_renders_button_when_ai_enabled(ai_on):
    conv = _conv()
    html = views.thread(_req("get"), pk=conv.pk).content.decode()
    assert "data-ai-reply-box" in html
    assert reverse("inbox:reply-draft", args=[conv.pk]) in html


def test_user_limit_10_and_tenant_limit_30(ai_on, isolated_ratelimit, monkeypatch):
    monkeypatch.setattr(tasks.ai_reply_draft, "delay", lambda **kw: None)
    conv = _conv()
    user = _user()
    codes = []
    for i in range(ai_reply.RATE_LIMIT + 1):
        # новое сообщение = новый digest: кэш не срабатывает
        services.post_message(conv, body=f"und {i}?", author_role="customer")
        codes.append(_json(views.reply_draft_start(_req("post", user=user), pk=conv.pk)))
    assert all("job" in c for c in codes[:-1])
    assert codes[-1] == {"code": "quota"}

    isolated_ratelimit.clear()
    results = []
    for i in range(ai_reply.RATE_LIMIT_TENANT + 1):
        services.post_message(conv, body=f"noch {i}?", author_role="customer")
        results.append(_json(views.reply_draft_start(_req("post"), pk=conv.pk)))
    assert all("job" in c for c in results[:-1])
    assert results[-1] == {"code": "quota"}


def test_cache_hit_bypasses_rate_limit_and_generate(ai_on, isolated_ratelimit, monkeypatch):
    from apps.inbox import ai_facts

    def boom(**kw):
        raise AssertionError("must not start a job on cache hit")

    monkeypatch.setattr(ai_reply, "start_job", boom)
    conv = _conv()
    req = _req("post")
    digest = ai_reply.digest_for(conv, ai_facts.facts_for(conv, req.tenant))
    schema = views._ai_schema()
    cache.set(ai_reply._cache_key(schema, digest), {"draft": "Ja, gern.", "language": "de"}, 60)
    for _ in range(ai_reply.RATE_LIMIT + 5):
        data = _json(views.reply_draft_start(_req("post", tenant=req.tenant), pk=conv.pk))
        assert data["state"] == "done" and data["draft"] == "Ja, gern." and data["label"]


def test_result_bad_job_id_404():
    with pytest.raises(Http404):
        views.reply_draft_result(_req("get"), job="../etc")


def test_result_other_user_404(ai_on, monkeypatch):
    monkeypatch.setattr(tasks.ai_reply_draft, "delay", lambda **kw: None)
    conv = _conv()
    data = _json(views.reply_draft_start(_req("post"), pk=conv.pk))
    with pytest.raises(Http404):
        views.reply_draft_result(_req("get"), job=data["job"])


def test_result_done_returns_draft_and_label(ai_on, monkeypatch):
    monkeypatch.setattr(tasks.ai_reply_draft, "delay", lambda **kw: None)
    conv = _conv()
    user = _user()
    job = _json(views.reply_draft_start(_req("post", user=user), pk=conv.pk))["job"]
    pending = _json(views.reply_draft_result(_req("get", user=user), job=job))
    assert pending == {"state": "pending"}
    cache.set(
        ai_reply._job_key(views._ai_schema(), user.pk, job),
        {"state": "done", "draft": "Wir prüfen das.", "language": "de"},
        60,
    )
    data = _json(views.reply_draft_result(_req("get", user=user), job=job))
    assert data["state"] == "done" and data["draft"] == "Wir prüfen das."
    assert data["label"] and data["language"] == "de"


def test_urls_live_under_cabinet_prefix():
    start = reverse("inbox:reply-draft", args=[uuid.uuid4()])
    result = reverse("inbox:reply-draft-result", args=["a" * 32])
    assert start.startswith(CABINET_PREFIXES) and result.startswith(CABINET_PREFIXES)


# --- О-2: Datenschutz -------------------------------------------------------------------


def test_privacy_text_gets_ai_paragraph_only_when_ai_and_inbox_on(settings):
    tenant = TenantFactory.build(enabled_modules=["catalog", "inbox"], disabled_modules=[])
    settings.AI_ENABLED = False
    before = tenant.privacy_text()
    assert "KI-Diensten" not in before
    settings.AI_ENABLED = True
    with_ai = tenant.privacy_text()
    assert "KI-Diensten" in with_ai and "Art. 28 DSGVO" in with_ai
    assert with_ai.replace(tenant._privacy_ai_paragraph(), "") == before

    no_inbox = TenantFactory.build(disabled_modules=["inbox"])
    assert "KI-Diensten" not in no_inbox.privacy_text()

    own = TenantFactory.build(privacy_policy="Eigener Text.", disabled_modules=[])
    assert own.privacy_text() == "Eigener Text."
