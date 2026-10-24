"""T-8.29 «Verbindungen sichtbar» (план docs/t8-29-30-integrations-miniapp-plan-2026-10-20.md).

Владелец лёгкого кабинета находит «Verbindungen» и свой Telegram-бот; модуль бота
включается с экрана интеграций (только владельцем); кнопка общего бота больше не ведёт
в 404; подключение своего бота не рвёт связь с общим ботом (Р-1).
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core import lite_cabinet, modules, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ACTIVATE = "/dashboard/integrationen/telegram-aktivieren/"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(lite=True, telegram_off=True):
    slug = f"t829-{uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {"profile": "aktionen"} if lite else {}
    t.disabled_modules = ["telegram", "finance"] if telegram_off else ["finance"]
    t.save()
    return t


def _member(role):
    from apps.core.models import Membership

    o = uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"m-{o}@t.de", email=f"m-{o}@t.de", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _req(method, path, tenant, user=None):
    rf = RequestFactory()
    req = rf.post(path, {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    from apps.core.models import Membership

    req.user = user or _member(Membership.ROLE_OWNER)
    req.tenant = tenant
    return req


def test_lite_nav_has_verbindungen():
    # T-8.31c: вход — «Sichtbar», полный список подключений — ссылкой оттуда.
    items = [i["url_name"] for i in lite_cabinet.sidebar_items(_tenant())]
    assert "lite-visibility" in items
    # полный кабинет не меняется (якоря заморожены — integrations живёт в настройках)
    full = [i["url_name"] for i in modules.sidebar_nav(_tenant(lite=False))]
    assert "integrations-home" not in full


def _card(tenant):
    from apps.core.models import Membership

    # KA-12 E8.6: карточка своего бота — в секции «Verbindungen» страницы каналов.
    body = views.notifications_settings(
        _req("get", "/dashboard/settings/notifications/", tenant, _member(Membership.ROLE_OWNER))
    ).content.decode()
    return body


def test_own_bot_card_module_off_offers_activation_with_explanation():
    # KA-12 E8.6: секция «Verbindungen» — у полного пакета; лёгкому — «Sichtbarkeit».
    body = _card(_tenant(lite=False))
    assert "data-own-bot" in body
    assert ACTIVATE in body
    assert "data-own-bot-confirm" in body  # подтверждение с объяснением (Р-4)


def test_own_bot_card_module_on_without_token_links_settings():
    body = _card(_tenant(lite=False, telegram_off=False))
    assert ACTIVATE not in body
    assert "/dashboard/telegram/" in body


def test_own_bot_card_hides_activation_for_staff():
    from apps.core.models import Membership

    t = _tenant(lite=False)
    body = views.notifications_settings(
        _req("get", "/dashboard/settings/notifications/", t, _member(Membership.ROLE_STAFF))
    ).content.decode()
    assert "data-own-bot" in body and ACTIVATE not in body


def test_activate_enables_only_telegram_and_redirects_to_settings():
    t = _tenant()
    resp = views.integrations_telegram_activate(_req("post", ACTIVATE, t))
    assert resp.status_code == 302 and resp["Location"] == "/dashboard/telegram/"
    t.refresh_from_db()
    assert "telegram" not in t.disabled_modules and "finance" in t.disabled_modules
    assert modules.is_module_active(t, "telegram")
    # повтор безопасен
    resp = views.integrations_telegram_activate(_req("post", ACTIVATE, t))
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.disabled_modules == ["finance"]


def test_activate_is_post_only():
    resp = views.integrations_telegram_activate(_req("get", ACTIVATE, _tenant()))
    assert resp.status_code == 405


def test_activate_requires_login():
    from django.contrib.auth.models import AnonymousUser

    req = _req("post", ACTIVATE, _tenant())
    req.user = AnonymousUser()
    assert views.integrations_telegram_activate(req).status_code == 302


def test_activate_is_owner_only_over_http():
    from apps.core.middleware import CabinetOwnerAccessMiddleware
    from apps.core.models import Membership

    mw = CabinetOwnerAccessMiddleware(lambda r: HttpResponse("ok"))
    t = _tenant()
    for role, status in ((Membership.ROLE_STAFF, 403), (Membership.ROLE_OWNER, 200)):
        assert mw(_req("post", ACTIVATE, t, _member(role))).status_code == status, role


def test_activate_path_not_under_gated_prefix():
    """Иначе ModuleGatingMiddleware ответит 404 раньше, чем вьюха включит модуль."""
    assert not ACTIVATE.startswith("/dashboard/telegram/")


def test_platform_bot_own_bot_target_never_404s():
    from apps.platform_bot import menu

    # KA-12 E8.6: «Verbindungen» — секция страницы каналов (экран всегда есть).
    assert menu.TARGETS["t"] == "notifications-settings"
    assert menu.target_path("t") == "/dashboard/settings/notifications/"


def test_settings_screen_explains_token_stays_out_of_chat():
    from apps.telegram import views as tg_views

    t = _tenant(telegram_off=False)
    body = tg_views.settings_view(_req("get", "/dashboard/telegram/", t)).content.decode()
    assert "@BotFather" in body
    assert "data-token-not-in-chat" in body


def test_claiming_own_bot_keeps_platform_link():
    """Р-1: свой бот получает уведомления владельцу, акции и Mini App остаются в общем."""
    from apps.platform_bot import links

    t = _tenant(telegram_off=False)
    links.bind(777001, t)
    links.claim_for_tenant_bot(t, 555, rotate_token="new")
    t.refresh_from_db()
    node = t.site_config["notify"]
    assert node["owner_bot"] == "tenant" and node["owner_chat_id"] == "555"
    assert links.is_owner(777001, t)


def test_claim_keeps_revocation_of_removed_owner():
    """Ревью T-8.29 (HIGH): после заявки своего бота удалённый из команды владелец НЕ
    сохраняет доступ к бизнесу через общий бот (метка owner_user_pk не стирается)."""
    from django_tenants.utils import schema_context

    from apps.core.models import Membership
    from apps.platform_bot import links

    t = _tenant(telegram_off=False)
    links.bind(777002, t)  # в тесте первое сохранение бизнеса создаёт его схему
    # T-8.30f-0: Membership живёт в схеме бизнеса — там его и создаём (как в проде).
    with schema_context(t.schema_name):
        owner = _member(Membership.ROLE_OWNER)
    links.bind(777002, t, user_pk=owner.pk)
    links.claim_for_tenant_bot(t, 556, rotate_token="new2")
    t.refresh_from_db()
    assert links.still_owner(t)
    with schema_context(t.schema_name):
        Membership.objects.filter(user=owner).delete()
    assert not links.still_owner(t)


@pytest.mark.parametrize("nav", ["integrations", "telegram"])
def test_lite_highlights_verbindungen(nav):
    """Ревью T-8.29: в лёгком кабинете экраны подключений подсвечивают «Verbindungen»,
    а не «Geschäft»; полный кабинет — карта W8 как раньше."""
    from types import SimpleNamespace

    from apps.core.templatetags.cabinet import sidebar_anchor

    lite = {"nav": nav, "request": SimpleNamespace(tenant=_tenant())}
    assert sidebar_anchor(lite) == "integrations"
    full = {"nav": nav, "request": SimpleNamespace(tenant=_tenant(lite=False))}
    from apps.core import nav_registry

    assert sidebar_anchor(full) == nav_registry.anchor_for(nav)
