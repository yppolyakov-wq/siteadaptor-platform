"""AIS-A A-0 срез A0.3: шторка «✨ Assistent» — права ссылок, только чтение, фрагмент."""

import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.core import assistant, assistant_views, diagnoses, packages, tg_login, view_perms
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    return TenantFactory(schema_name="public")


def _user(role=None):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"a-{o}", email=f"a-{o}@t.de", password="pw12345678"
    )
    if role:
        Membership.objects.create(user=user, role=role)
    return user


def _req(tenant, data=None, user=None, headers=None):
    request = RequestFactory().get("/dashboard/assistent/", data or {}, headers=headers or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user(Membership.ROLE_OWNER)
    request.tenant = tenant
    return request


def test_screen_registered_everywhere():
    assert view_perms.rule_for("assistant").read == view_perms.OPEN
    assert view_perms.rule_for("owner-confirm-resend").read == view_perms.FLOOR
    assert "assistant" in tg_login.TG_LITE_VIEWS
    assert "assistant" in packages._AKTIONEN_VIEWS


def test_requires_login_and_get(tenant):
    request = _req(tenant)
    request.user = AnonymousUser()
    assert assistant_views.assistant_view(request).status_code == 302
    post = RequestFactory().post("/dashboard/assistent/")
    post.user, post.tenant = _user(Membership.ROLE_OWNER), tenant
    assert assistant_views.assistant_view(post).status_code == 405


def test_full_page_and_fragment(tenant):
    page = assistant_views.assistant_view(_req(tenant))
    assert page.status_code == 200
    body = page.content.decode()
    assert "data-assistant" in body and "Gerade wichtig" in body
    box = assistant_views.assistant_view(_req(tenant, {"box": "1"}))
    assert box["X-Sf-Fragment"] == "1"
    frag = box.content.decode()
    assert "<script" not in frag
    assert not re.search(r"\son[a-z]+=", frag), "фрагмент шторки без on…="


def test_view_is_read_only(tenant):
    request = _req(tenant, {"seite": "dashboard", "q": "zeiten"})
    with CaptureQueriesContext(connection) as ctx:
        assistant_views.assistant_view(request)
    writes = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        and "django_session" not in q["sql"]
    ]
    assert not writes, writes[:3]


def test_seite_is_whitelisted(tenant):
    assert assistant_views._seite(_req(tenant, {"seite": "https://evil.test/"})) == ""
    assert assistant_views._seite(_req(tenant, {"seite": "settings"})) == "settings"


def test_staff_never_sees_billing_and_gets_owner_note(tenant, monkeypatch):
    staff = _user(Membership.ROLE_STAFF)
    request = _req(tenant, user=staff)
    assert assistant.link(request, "billing") is None
    assert assistant.link(request, "team") is None
    blocked = assistant.link(request, "owner-confirm-resend", method="POST")
    assert blocked.url == "" and blocked.blocked == assistant.BLOCK_OWNER
    owner = assistant.link(_req(tenant), "owner-confirm-resend", method="POST")
    assert owner.url and owner.method == "POST"


def test_owner_only_findings_hidden_for_staff(tenant, monkeypatch):
    from apps.aggregator import visibility

    monkeypatch.setattr(visibility, "withheld_reasons", lambda t: ["suspended"])
    staff_cards = assistant.diagnosis_cards(_req(tenant, user=_user(Membership.ROLE_STAFF)))
    owner_cards = assistant.diagnosis_cards(_req(tenant))
    by = {c["key"]: c for c in staff_cards}
    assert by["not_in_city"]["findings"] == []
    assert {c["key"]: c for c in owner_cards}["not_in_city"]["findings"]


def test_mini_app_offers_browser_note(tenant, monkeypatch):
    monkeypatch.setattr(tg_login, "is_tg_session", lambda r: True)
    got = assistant.link(_req(tenant), "booking:services")
    assert got.url == "" and got.blocked == assistant.BLOCK_BROWSER


def test_package_note(tenant, monkeypatch):
    monkeypatch.setattr(packages, "view_allowed", lambda t, name: name != "payment-settings")
    got = assistant.link(_req(tenant), "payment-settings")
    assert got.url == "" and got.blocked == assistant.BLOCK_PACKAGE


def test_heavy_diagnosis_runs_only_on_request(tenant, monkeypatch):
    calls = []
    monkeypatch.setattr(diagnoses, "applicable", lambda t: [diagnoses.BY_KEY["google_feed"]])
    real = diagnoses.run

    def spy(t, key):
        calls.append(key)
        return real(t, key)

    monkeypatch.setattr(diagnoses, "run", spy)
    assistant.diagnosis_cards(_req(tenant))
    assert "google_feed" not in calls
    assistant.diagnosis_cards(_req(tenant), "google_feed")
    assert "google_feed" in calls


def test_heavy_diagnosis_rate_limited(tenant, monkeypatch):
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "hit", lambda *a, **kw: True)
    monkeypatch.setattr(diagnoses, "applicable", lambda t: [diagnoses.BY_KEY["google_feed"]])
    body = assistant_views.assistant_view(_req(tenant, {"pruefen": "google_feed"})).content
    assert "Zu viele Prüfungen".encode() in body
    cache.clear()


def test_garbage_pruefen_is_ignored(tenant):
    assert (
        assistant_views.assistant_view(_req(tenant, {"pruefen": "website_hidden"})).status_code
        == 200
    )
    assert assistant_views.assistant_view(_req(tenant, {"pruefen": "x" * 500})).status_code == 200


def test_where_search_uses_palette_and_link(tenant):
    found = assistant.where_search(_req(tenant), "öffnungszeiten")
    assert found and all(w["link"].url.startswith("/") for w in found)
    assert assistant.where_search(_req(tenant), "") == []


def test_block_failure_does_not_break(tenant, monkeypatch):
    monkeypatch.setattr(assistant, "important", lambda r: 1 / 0)
    resp = assistant_views.assistant_view(_req(tenant))
    assert resp.status_code == 200
    assert "Einige Prüfungen konnten nicht ausgeführt werden" in resp.content.decode()


def test_important_never_says_done_when_unknown(tenant, monkeypatch):
    request = _req(tenant)
    request._assistant_rows = [
        {"key": "x", "label": "X", "level": "must", "done": None, "url_name": ""}
    ]
    monkeypatch.setattr("apps.core.storefront_state.hidden_reasons", lambda t: [])
    texts = [i["text"] for i in assistant.important(request)]
    assert "Alles Wichtige ist erledigt." not in texts


def test_chrome_only_links(settings):
    """Хром — только ссылка: шапка не зовёт readiness/диагнозы."""
    from pathlib import Path

    src = Path("templates/tenant/_base_dashboard.html").read_text(encoding="utf-8")
    assert "{% url 'assistant' %}" in src
    assert "assistant_rows" not in src and "diagnos" not in src
