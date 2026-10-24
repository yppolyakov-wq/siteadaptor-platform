"""W9-9 (Р-3, аудит 2026-08-05): «Integrationen» — вкладка Einstellungen.

- Якорь ушёл из сайдбара; страница рендерит таб-бар settings-хаба и подсвечивает
  якорь «Einstellungen» (карта W8).
- Карточки несут read-only статусы подключений (fail-safe, честные состояния).
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import modules, nav_registry, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _req(tenant=None):
    req = RequestFactory().get("/dashboard/settings/notifications/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant or TenantFactory(business_type="restaurant")
    return req


def test_integrations_left_sidebar_moved_to_settings_hub():
    """KA-12 E8.6 (осознанная переписка W9-9): отдельного экрана «Integrationen»
    больше нет — секция «Verbindungen» на «Kanäle & Benachrichtigungen»."""
    t = TenantFactory(business_type="restaurant")
    assert "integrations-home" not in [it["url_name"] for it in modules.sidebar_nav(t)]
    assert not any(e.url_name == "integrations-home" for e in nav_registry.ENTRIES)


def test_integrations_page_renders_settings_tabs_and_statuses():
    body = views.notifications_settings(_req()).content.decode()
    assert 'id="verbindungen"' in body
    assert "Nicht verbunden" in body  # Stripe без подключения — честный статус
    assert "Keine eigene Domain" in body


def test_integrations_stripe_status_reflects_tenant_flags():
    t = TenantFactory(business_type="restaurant")
    t.payments_enabled = True
    t.save(update_fields=["payments_enabled"])
    body = views.notifications_settings(_req(tenant=t)).content.decode()
    assert "Stripe verbunden" in body


def test_integrations_requires_login():
    """Регресс: @login_required был «съеден» хелпером `_google_rating_status`,
    вставленным между декоратором и вьюхой, — аноним получал 200 со статусами
    подключений (Stripe/Telegram/домен). Класс граблей из build-log 2026-08-01."""
    from django.contrib.auth.models import AnonymousUser

    req = _req()
    req.user = AnonymousUser()
    resp = views.integrations_home(req)
    assert resp.status_code == 302


def test_integrations_google_rating_status_shown():
    """Регресс: обёрнутый в login_required хелпер падал внутри _safe →
    карточка «Google Bewertungen» всегда показывала пустой muted-статус."""
    t = TenantFactory(business_type="restaurant")
    t.google_place_id = "ChIJ-test"
    t.google_rating = "4.70"
    t.google_rating_count = 12
    t.save(update_fields=["google_place_id", "google_rating", "google_rating_count"])
    body = views.notifications_settings(_req(tenant=t)).content.decode()
    assert "★ 4.70 · 12" in body


def test_integrations_bot_status_readonly():
    from apps.telegram.models import TelegramBot

    TelegramBot.objects.create(token="123:abc", bot_username="demo_bot", is_active=True)
    body = views.notifications_settings(_req()).content.decode()
    # KA-12 E8.6: карточка «Benachrichtigungen» бывшего экрана сама стала этой страницей —
    # статус бота показывает её блок «Ihr Telegram» (W9-7), без дубля в «Verbindungen».
    assert "Aktiver Bot:" in body
    assert "@demo_bot" in body
