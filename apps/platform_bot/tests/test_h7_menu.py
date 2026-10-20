"""T-8.10h H-7b/c/g: «/hilfe», меню, «/kabinett» (вход письмом на нужный экран), «/eigener_bot».

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core import owner_login
from apps.core.models import Membership
from apps.platform_bot import handler, links, menu
from apps.platform_bot.tests.test_h5b_second_business_email import (  # noqa: F401
    MAIL,
    USER,
    _cb,
    _msg,
    bot,
)
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _owner(slug="m-1"):
    tenant = TenantFactory(schema_name="public", slug=slug, name=f"Laden {slug}")
    user = get_user_model().objects.create_user(
        username=f"u-{slug}", email=MAIL, password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    links.bind(USER, tenant, user_pk=user.pk)
    return tenant


def _datas(entry):
    rows = (entry["markup"] or {}).get("inline_keyboard", [])
    return [b.get("callback_data") or b.get("url") for row in rows for b in row]


def test_help_command_shows_menu_and_photo_tip(bot):  # noqa: F811
    assert handler.handle(_msg("/hilfe")) == "help"
    last = bot["sent"][-1]
    assert "📷" in last["text"] and "/kabinett" in last["text"]
    assert {"pm:k", "pm:b", "pm:d", "pm:h"} <= set(_datas(last))


def test_help_works_during_signup_and_is_not_promo_text(bot):  # noqa: F811
    _owner()
    assert handler.handle(_msg("/help")) == "help"


def test_cabinet_offers_whitelisted_screens(bot):  # noqa: F811
    tenant = _owner()
    assert handler.handle(_msg("/kabinett")) == "cabinet"
    datas = _datas(bot["sent"][-1])
    assert {f"pm:l:{c}" for c in menu.TARGETS} <= set(datas)
    assert any(d.startswith("http") and d.endswith("/dashboard/telegram/") for d in datas)
    assert tenant.name in bot["sent"][-1]["text"]


def test_cabinet_without_business_falls_back_to_onboarding(bot):  # noqa: F811
    assert handler.handle(_msg("/kabinett")) == "onboarding"


def test_login_button_sends_mail_with_next(bot, monkeypatch):  # noqa: F811
    _owner()
    calls = []
    monkeypatch.setattr(
        "apps.core.owner_login.send_login_link",
        lambda t, e, **k: calls.append((e, k.get("next_path"))),
    )
    assert handler.handle(_cb("pm:l:t")) == "sent"
    assert calls == [(MAIL, "/dashboard/telegram/")]


@pytest.mark.parametrize("data", ["pm:l:x", "pm:l:/evil", "pm:l://evil.com", "pm:zz", "pm:"])
def test_unknown_menu_callbacks_are_ignored(bot, monkeypatch, data):  # noqa: F811
    _owner()
    calls = []
    monkeypatch.setattr("apps.core.owner_login.send_login_link", lambda *a, **k: calls.append(a))
    assert handler.handle(_cb(data)) == "skip"
    assert not calls


def test_login_button_without_business_is_denied(bot, monkeypatch):  # noqa: F811
    monkeypatch.setattr("apps.core.owner_login.send_login_link", lambda *a, **k: 1 / 0)
    assert handler.handle(_cb("pm:l:a")) == "denied"


def test_mail_link_carries_next_and_rejects_foreign_hosts(monkeypatch):
    tenant = TenantFactory(schema_name="public", slug="m-next")
    bodies = []
    monkeypatch.setattr(owner_login, "tenant_url", lambda t: "https://m.example.com")
    monkeypatch.setattr(owner_login, "send_mail", lambda s, b, f, to, **k: bodies.append(b))
    owner_login.send_login_link(tenant, MAIL, next_path="/dashboard/telegram/")
    owner_login.send_login_link(tenant, MAIL, next_path="//evil.com/x")
    owner_login.send_login_link(tenant, MAIL, next_path="/\\evil.com")
    owner_login.send_login_link(tenant, MAIL, next_path="https://evil.com/")
    assert "?next=%2Fdashboard%2Ftelegram%2F" in bodies[0]
    assert all("next=" not in b for b in bodies[1:])


def test_owner_start_redirects_to_next():
    req = RequestFactory().get("/start/x/?next=//evil.com")
    assert owner_login.safe_next(req, "//evil.com") == owner_login.DEFAULT_NEXT
    assert owner_login.safe_next(req, "/dashboard/telegram/") == "/dashboard/telegram/"


def test_own_bot_never_asks_for_token_in_chat(bot):  # noqa: F811
    _owner()
    assert handler.handle(_msg("/eigener_bot")) == "own_bot"
    last = bot["sent"][-1]
    assert "@BotFather" in last["text"]
    assert "pm:l:t" in _datas(last)


def test_privacy_from_menu(bot):  # noqa: F811
    _owner()
    assert handler.handle(_cb("pm:d")) == "privacy_info"


def test_commands_include_menu_entries(monkeypatch):
    from apps.platform_bot import config

    seen = []
    monkeypatch.setattr(
        "apps.telegram.services.set_my_commands",
        lambda token, commands, language_code="": seen.append([c["command"] for c in commands]),
    )
    config.set_commands("123:x")
    assert seen and all({"hilfe", "kabinett", "eigener_bot"} <= set(cmds) for cmds in seen)
