"""T-8.30h: первый запуск — Mini App без бизнеса не тупик (фидбэк владельца со скриншотом).

`unlinked` несёт бота и адрес веб-регистрации, страница даёт действия; регистрация в
чате и ожидание почты — отдельный ответ `pending`; бот понимает `/start neu|mail`.
"""

import time
from pathlib import Path

import pytest

from apps.platform_bot import handler, links, signup
from apps.platform_bot.tests.test_h5_signup import _msg, bot  # noqa: F401
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    UID,
    _auth,
    _tenant,
    on,
)
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db
TPL = Path(__file__).resolve().parents[3] / "templates" / "platform_bot" / "miniapp.html"


def test_unlinked_offers_bot_signup_and_web():
    status, body = _auth(uid=990001)
    assert status == 200 and body["error"] == "unlinked" and "next" not in body
    assert body["bot"] == "PlattformBot"
    assert body["web_url"].endswith("/aktion-starten/")
    assert "/hilfe" not in body["message"]


def test_pending_email_answers_pending():
    t = _tenant()
    t.email_pending = True
    t.site_config = {"notify": {"pending_tg_owner": {"uid": UID, "at": int(time.time())}}}
    t.save()
    body = _auth()[1]
    assert body["error"] == "pending" and "next" not in body and body["bot"] == "PlattformBot"


def test_link_to_business_still_provisioning_answers_pending():
    t = _tenant()
    links.bind(UID, t)
    Tenant.objects.filter(pk=t.pk).update(provisioning_status=Tenant.PROVISIONING_PENDING)
    assert _auth()[1]["error"] == "pending"


def test_page_has_first_run_actions():
    src = TPL.read_text()
    assert "data-unlinked" in src and "toBot(\"neu\")" in src and "?start=" in src
    assert "openTelegramLink" in src
    assert "data-pending" in src


def test_start_neu_begins_signup(bot):  # noqa: F811
    handler.handle(_msg("/start neu"))
    assert signup.load(handler_uid()) is not None


def test_start_mail_without_pending_is_onboarding(bot):  # noqa: F811
    assert handler.handle(_msg("/start mail")) == "onboarding"


def test_start_mail_reminds_pending_email(bot):  # noqa: F811
    from apps.platform_bot.tests.test_h5_signup import USER

    t = _tenant()
    t.email_pending = True
    t.site_config = {"notify": {"pending_tg_owner": {"uid": USER, "at": int(time.time())}}}
    t.save()
    assert handler.handle(_msg("/start mail")) not in ("", "onboarding")


def handler_uid():
    from apps.platform_bot.tests.test_h5_signup import USER

    return USER
