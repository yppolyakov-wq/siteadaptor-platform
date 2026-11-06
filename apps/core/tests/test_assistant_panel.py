"""AIS A-3c: плавающая кнопка «✨ Assistent» + вкладки KI · Support · Kunden в шторке.

Запрос владельца 2026-11-06: «плавающая кнопка справа снизу: переписка с ИИ, чат
техподдержки, вход в чат с клиентами». Замки:
* один вход — плавающая кнопка (прежней ссылки ✨ в верхней строке нет);
* вкладки — whitelist `?tab=`, мусор → KI; не-KI вкладки не считают диагнозы;
* Support — только треды СВОЕГО бизнеса, форма новой заявки из шторки;
* Kunden — только при модуле inbox и праве; без e-mail/телефона клиента;
* недоступная вкладка не показывается (Mini App/пакет/права — тот же `reachable`).
"""

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import assistant, assistant_panel, assistant_views
from apps.core.models import Membership
from apps.support import services as support_services
from apps.support.models import SupportThread
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def shop(db):
    return TenantFactory(schema_name="public", business_type="bakery", name="Bäckerei Panel")


def _user(role=Membership.ROLE_OWNER):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"p-{o}", email=f"p-{o}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _req(tenant, data=None, user=None, drawer=False, method="get", path="/dashboard/assistent/"):
    headers = {"X-Sf-Drawer": "1"} if drawer else {}
    request = getattr(RequestFactory(), method)(path, data or {}, headers=headers)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user or _user()
    request.tenant = tenant
    request._dont_enforce_csrf_checks = True
    return request


def _page(tenant, **data):
    return assistant_views.assistant_view(_req(tenant, data)).content.decode()


def test_one_entry_is_the_floating_button(shop):
    html = _page(shop)
    assert html.count("data-assistant-open") == 1
    assert "data-assistant-fab" in html


def test_tabs_whitelist_and_default_ki(shop):
    assert 'data-assistant-tab="ki"' in _page(shop, tab="nonsense")
    assert 'data-assistant-tab="support"' in _page(shop, tab="support")


def test_non_ki_tab_does_not_run_diagnoses(shop, monkeypatch):
    calls = []
    real = assistant.build
    monkeypatch.setattr(assistant, "build", lambda *a, **k: calls.append(1) or real(*a, **k))
    _page(shop, tab="support")
    assert calls == []


def test_support_tab_lists_only_own_threads(shop):
    support_services.open_thread(tenant=shop, subject="Kasse hängt", body="x")
    other = TenantFactory(name="Fremd")
    support_services.open_thread(tenant=other, subject="FREMDES THEMA", body="y")
    html = _page(shop, tab="support")
    assert "Kasse hängt" in html and "FREMDES THEMA" not in html
    assert "data-drawer-form" in html and 'name="subject"' in html


def test_support_form_from_drawer_answers_json(shop):
    from apps.support import views as support_views

    resp = support_views.help_list(
        _req(
            shop,
            {"subject": "Frage", "body": "Wie geht das?"},
            drawer=True,
            method="post",
            path="/dashboard/help/",
        )
    )
    data = json.loads(resp.content)
    assert data["ok"] is True
    assert SupportThread.objects.filter(tenant=shop, subject="Frage").exists()


def test_kunden_tab_shows_conversations_without_contacts(shop):
    from apps.inbox.models import Conversation
    from apps.promotions.models import Customer

    cust = Customer.objects.create(
        name="Erika Muster", email="erika@private.test", phone="+49 170 1234567"
    )
    Conversation.objects.create(customer=cust, subject="Torte bestellen", unread_for_staff=True)
    html = _page(shop, tab="kunden")
    assert "Torte bestellen" in html and "Erika Muster" in html
    assert "erika@private.test" not in html and "1234567" not in html


def test_kunden_tab_hidden_without_inbox_module(shop, monkeypatch):
    real = type(shop).is_module_active
    monkeypatch.setattr(
        type(shop),
        "is_module_active",
        lambda self, key: False if key == "inbox" else real(self, key),
    )
    html = _page(shop)
    assert 'data-assistant-tablink="kunden"' not in html
    assert 'data-assistant-tab="ki"' in _page(shop, tab="kunden")


def test_tabs_respect_reachability(shop, monkeypatch):
    from apps.core import setup_assistant

    monkeypatch.setattr(setup_assistant, "reachable", lambda request, name: False)
    tabs = assistant_panel.tabs_for(_req(shop), "ki")
    assert [t["key"] for t in tabs] == ["ki"]


def test_support_unread_dot(shop):
    from apps.support.models import SupportMessage

    thread = support_services.open_thread(tenant=shop, subject="Q", body="hi")
    support_services.add_message(thread, body="Antwort", author_role=SupportMessage.AUTHOR_PLATFORM)
    assert assistant_panel.support_unread(_req(shop)) == 1
    assert "data-assistant-support-dot" in _page(shop)
