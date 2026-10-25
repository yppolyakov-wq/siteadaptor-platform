"""T-8.31c «Sichtbarkeit & Verbindungen» (план docs/t8-31-mein-laden-plan-2026-10-20.md §2)."""

import re
from unittest import mock
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import Resolver404, resolve

from apps.core import lite_cabinet, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
PATH = "/dashboard/sichtbarkeit/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(telegram_off=True, publishing=True):
    slug = f"vis-{uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {"profile": "aktionen"}
    off = ["finance"]
    if telegram_off:
        off.append("telegram")
    if not publishing:
        off.append("publishing")
    t.disabled_modules = off
    t.save()
    return t


def _member(role):
    from apps.core.models import Membership

    o = uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"v-{o}", password="pw12345678")
    Membership.objects.create(user=user, role=role)
    return user


def _req(tenant, user, method="get", path=PATH, data=None):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user, tenant
    return req


def _owner():
    from apps.core.models import Membership

    return _member(Membership.ROLE_OWNER)


def _staff():
    from apps.core.models import Membership

    return _member(Membership.ROLE_STAFF)


def _body(tenant, user):
    resp = lite_cabinet.lite_visibility(_req(tenant, user))
    assert resp.status_code == 200
    return resp.content.decode()


def test_owner_sees_all_blocks():
    body = _body(_tenant(), _owner())
    for key in ("website", "stadtportal", "google", "platform-bot"):
        assert f'data-vis="{key}"' in body, key
    assert "data-own-bot" in body
    # T-8.32b: оплата, домен и полный список подключений — вне пакета «Aktionen».
    for key in ("stripe", "domain"):
        assert f'data-vis="{key}"' not in body, key
    assert "data-all-connections" not in body


def test_portal_views_owner_only():
    t = _tenant()
    with (
        mock.patch("apps.promotions.where._catalog_reason", return_value=""),
        mock.patch("apps.aggregator.owner_stats.summary") as summary,
    ):
        summary.return_value = {"funnel": [{"code": "view", "value": 212}]}
        staff_body = _body(t, _staff())
        assert not summary.called
        owner_body = _body(t, _owner())
        assert summary.called
    assert "data-portal-views" not in staff_body
    assert "data-portal-views" in owner_body and "212" in owner_body


def test_google_only_for_owner_and_with_publishing():
    t = _tenant()
    assert 'data-vis="google"' not in _body(t, _staff())
    assert 'data-vis="google"' not in _body(_tenant(publishing=False), _owner())


def test_own_bot_module_off_shows_activation_with_return():
    body = _body(_tenant(), _owner())
    assert "/dashboard/integrationen/telegram-aktivieren/" in body
    assert f'name="next" value="{PATH}"' in body


def test_own_bot_module_on_without_token_shows_inline_form_for_owner():
    t = _tenant(telegram_off=False)
    body = _body(t, _owner())
    assert "data-own-bot-token" in body and "/dashboard/telegram/connect/" in body
    assert "@BotFather" in body
    assert "data-own-bot-token" not in _body(t, _staff())


def test_own_bot_connected_shows_username():
    from apps.telegram.models import TelegramBot

    t = _tenant(telegram_off=False)
    TelegramBot.objects.create(token="x", bot_username="krume_bot", is_active=True)
    body = _body(t, _owner())
    assert "@krume_bot" in body and "data-own-bot-token" not in body


def test_stripe_not_offered_to_the_aktionen_package():
    """T-8.32b: Zurücklegen и купон оплаты не требуют — карточки Stripe у пакета нет."""
    assert 'data-vis="stripe"' not in _body(_tenant(), _owner())


def test_every_link_resolves():
    body = _body(_tenant(telegram_off=False), _owner())
    page = body[body.index("data-lite-visibility") :]  # содержимое страницы, без хрома
    for href in re.findall(r'(?:href|action)="(/[^"]*)"', page):
        if href.startswith("/static/"):
            continue
        try:
            resolve(href.split("?")[0].split("#")[0])
        except Resolver404:
            pytest.fail(f"dead link {href}")


def test_broken_status_block_does_not_break_page():
    t = _tenant()
    with (
        mock.patch("apps.core.integration_status.domain", side_effect=RuntimeError("boom")),
        mock.patch.object(lite_cabinet, "_portal_block", side_effect=RuntimeError("boom")),
    ):
        assert lite_cabinet.lite_visibility(_req(t, _owner())).status_code == 200


def test_activation_returns_to_visibility():
    t = _tenant()
    resp = views.integrations_telegram_activate(_req(t, _owner(), "post", "/x/", {"next": PATH}))
    assert resp.status_code == 302 and resp.url == PATH
    resp = views.integrations_telegram_activate(
        _req(t, _owner(), "post", "/x/", {"next": "//evil.example/"})
    )
    assert resp.url == "/dashboard/telegram/"


def test_bot_connect_returns_to_visibility_on_error():
    from apps.telegram import views as tg_views

    t = _tenant(telegram_off=False)
    resp = tg_views.connect(_req(t, _owner(), "post", "/x/", {"token": "", "next": PATH}))
    assert resp.url == PATH
    resp = tg_views.connect(
        _req(t, _owner(), "post", "/x/", {"token": "", "next": "https://evil.example/"})
    )
    assert resp.url == "/dashboard/telegram/"


def test_integrations_home_output_unchanged_by_extraction():
    """Карточки «Integrationen» после выноса статусов — те же ключи и тексты."""
    # KA-12 E8.6: карточки — секция «Verbindungen» на странице каналов (полный пакет).
    t = _tenant()
    t.site_config = {}
    t.save(update_fields=["site_config"])
    body = views.notifications_settings(
        _req(t, _owner(), path="/dashboard/settings/notifications/")
    )
    html = body.content.decode()
    assert "Nicht verbunden" in html and "Keine eigene Domain" in html
    assert "data-own-bot-token" not in html  # форма токена — только на «Sichtbarkeit»


@pytest.mark.parametrize(
    "path", ["/dashboard/telegram/connect/", "/dashboard/telegram/disconnect/"]
)
def test_bot_token_endpoints_owner_only(path):
    """Ревью T-8.31: сотрудник не подменяет и не снимает бота клиентов."""

    from apps.core.tests.gates import ok, open_as

    t = _tenant(telegram_off=False)
    assert open_as(_req(t, _staff(), "post", path), ok).status_code == 403
    assert open_as(_req(t, _owner(), "post", path), ok).status_code == 200
