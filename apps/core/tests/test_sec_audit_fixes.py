"""Замки аудита безопасности 2026-11-01 (SEC-A2/A3/A6, SEC-B1/B6, SEC-E5, SEC-G4).

Каждый тест кодирует сценарий атаки из отчёта (`docs/security-audit-report-2026-11-01.md`)
и был красным до фикса.
"""

import time
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory

from apps.core import owner_login, team
from apps.core.models import Membership
from apps.platform_bot import links
from apps.platform_bot.models import OwnerTelegramLink
from apps.promotions import telegram_promo as tp
from apps.telegram import notify
from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
UID = 616161


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr("django_tenants.models.schema_exists", lambda name: True)
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-{uuid.uuid4()}", {}))


def _tenant():
    slug = f"sec-{uuid.uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {}
    t.save()
    return t


def _user(role=Membership.ROLE_OWNER):
    user = get_user_model().objects.create_user(
        username=f"sec-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _req(path="/", method="get", user=None, tenant=None, **params):
    rf = RequestFactory()
    req = rf.post(path, params) if method == "post" else rf.get(path, params)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or AnonymousUser()
    req.tenant = tenant or TenantFactory.build()
    return req


# --- SEC-A3: owner deep link своего бота — срок, выпустивший, still_owner ----------------


def test_owner_link_expires_and_remembers_issuer():
    TelegramBot.objects.create(token="t", bot_username="OwnerBot", is_active=True)
    tenant, user = _tenant(), _user()
    token = notify.owner_deep_link(tenant, user=user).rsplit("start=owner-", 1)[1]
    node = tenant.site_config["notify"]
    assert node["owner_link_user_pk"] == user.pk
    node["owner_link_token_at"] = int(time.time()) - notify.OWNER_LINK_TTL - 5
    tenant.save()
    assert notify.link_owner_from_start(f"owner-{token}", 42, tenant) is False  # просрочен
    fresh = notify.owner_deep_link(tenant, user=user).rsplit("start=owner-", 1)[1]
    assert fresh != token  # просроченный перевыпущен
    assert notify.link_owner_from_start(f"owner-{fresh}", 42, tenant) is True
    tenant.refresh_from_db()
    assert tenant.site_config["notify"]["owner_user_pk"] == user.pk


def test_demoted_owner_loses_tenant_bot_rights():
    TelegramBot.objects.create(token="t", bot_username="OwnerBot", is_active=True)
    tenant, user = _tenant(), _user()
    token = notify.owner_deep_link(tenant, user=user).rsplit("start=owner-", 1)[1]
    assert notify.link_owner_from_start(f"owner-{token}", 42, tenant) is True
    tenant.refresh_from_db()
    msg = {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}}
    assert tp.owner_ok(tenant, "42") and tp.is_owner_private(msg, tenant)
    assert links.owner_route(tenant) == (links.OWNER_BOT_TENANT, "42")
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    assert not tp.owner_ok(tenant, "42") and not tp.is_owner_private(msg, tenant)
    assert links.owner_route(tenant) == ("", "")


def test_release_user_disconnects_links_of_removed_owner():
    tenant, user = _tenant(), _user()
    links.bind(UID, tenant, user_pk=user.pk)
    assert links.is_owner(UID, tenant)
    assert links.release_user(tenant, user.pk) is True
    assert not links.is_owner(UID, tenant)
    assert "owner_chat_id" not in (tenant.site_config.get("notify") or {})


def test_release_user_ignores_other_users():
    tenant, user, other = _tenant(), _user(), _user()
    links.bind(UID, tenant, user_pk=user.pk)
    assert links.release_user(tenant, other.pk) is False
    assert links.is_owner(UID, tenant)


# --- SEC-A6: связь кабинета без пользователя — fail-closed -----------------------------------


def test_cabinet_link_without_user_is_not_owner():
    tenant = _tenant()
    links.bind(UID, tenant)  # via=cabinet, user_pk=None
    assert links.still_owner(tenant) is False
    OwnerTelegramLink.objects.filter(tenant=tenant).update(via=OwnerTelegramLink.VIA_SIGNUP)
    assert links.still_owner(tenant) is True  # регистрация в боте: владельца создал сам бот


# --- SEC-A2: deep link клиента — только подтверждённому владельцу карточки ---------------------


def test_customer_deep_link_hidden_from_strangers():
    from apps.account import auth as account_auth
    from apps.promotions.models import Customer

    TelegramBot.objects.create(token="t", bot_username="ShopBot", is_active=True)
    victim = Customer.objects.create(name="V", email="victim@example.com")
    other = Customer.objects.create(name="O", email="other@example.com")
    assert notify.deep_link_for_page(_req(), victim) == ""  # аноним со страницы по коду
    req = _req()
    req.session[account_auth.SESSION_KEY] = str(other.pk)
    assert notify.deep_link_for_page(req, victim) == ""  # чужой ЛК
    req = _req()
    req.session[account_auth.SESSION_KEY] = str(victim.pk)
    assert "start=" in notify.deep_link_for_page(req, victim)  # свой ЛК


# --- SEC-B1: одноразовые токены — забирает только тот, кто удалил ключ ------------------------


@pytest.mark.parametrize(
    "issue, consume",
    [
        (
            lambda: owner_login.issue_token("sec_schema", "a@b.de"),
            lambda t: owner_login.consume_token("sec_schema", t),
        ),
        (lambda: team.issue_invite("x@y.de", Membership.ROLE_STAFF), team.consume_invite),
    ],
)
def test_token_consume_is_atomic(issue, consume, monkeypatch):
    from django.core.cache import cache

    token = issue()
    monkeypatch.setattr(cache, "delete", lambda key: False)  # второй параллельный POST проиграл
    assert consume(token) is None


def test_account_and_portal_magic_links_consume_atomically(monkeypatch):
    from django.core.cache import cache

    from apps.account import auth as account_auth
    from apps.aggregator import auth as portal_auth

    monkeypatch.setattr(cache, "get", lambda key, default=None: {"email": "a@b.de"})
    monkeypatch.setattr(cache, "delete", lambda key: False)
    assert account_auth.consume_magic_link("x" * 40) is None
    assert portal_auth.consume_magic_link("x" * 40) is None


# --- SEC-E5: `next=` на витрине — только локальный путь ----------------------------------------


@pytest.mark.parametrize("nxt", ["https://evil.example/", "//evil.example", "/\\evil.example"])
def test_set_language_has_no_open_redirect(nxt):
    from apps.promotions.public_views import set_language

    resp = set_language(_req("/lang/", lang="de", next=nxt))
    assert resp.status_code == 302
    assert resp["Location"].startswith("/") and "evil" not in resp["Location"]


def test_safe_next_default_parameter():
    req = _req()
    assert owner_login.safe_next(req, "https://evil.example", "/fallback/") == "/fallback/"
    assert owner_login.safe_next(req, "/ok/?a=1", "/fallback/") == "/ok/?a=1"


# --- SEC (silent): упавшая идемпотентная задача освобождает ключ дедупа -----------------------


def test_idempotent_task_releases_lock_on_failure():
    from django.core.cache import cache

    from apps.core.jobs import idempotent_task

    @idempotent_task(name=f"sec.test.{uuid.uuid4().hex}")
    def boom(**kwargs):
        raise RuntimeError("db")

    key = f"sec-{uuid.uuid4().hex}"
    cache.delete(f"job_lock:{key}")
    with pytest.raises(RuntimeError):
        boom(dedupe_key=key)
    assert cache.get(f"job_lock:{key}") is None


# --- SEC-G4: документ без поездки получает срок хранения ----------------------------------------


def test_document_without_ticket_gets_retention():
    from datetime import timedelta

    from django.utils import timezone

    from apps.documents import services

    assert services._ticket_expiry("", "") == timezone.localdate() + timedelta(
        days=services.retention_days()
    )
    assert services._ticket_expiry("ticket", "not-a-uuid") is not None


def test_receipts_are_exempt_from_retention(monkeypatch):
    """GoBD: Beleg/Eingangsrechnung хранится 10 лет — ретеншн документов участников его не трогает."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.documents import services
    from apps.documents.models import SecureDocument

    monkeypatch.setattr(services, "save_encrypted", lambda uploaded: ("x.enc", "image/png", 3))
    doc = services.store(
        type("U", (), {"name": "r.png"})(),
        owner=None,
        kind=SecureDocument.KIND_RECEIPT,
        uploaded_by=None,
    )
    assert doc.expires_at is None
    services.purge_expired(today=timezone.localdate() + timedelta(days=5000))
    assert SecureDocument.objects.filter(pk=doc.pk).exists()


def test_platform_send_403_marks_blocked_with_sanitized_error(monkeypatch):
    from apps.notifications import adapters
    from apps.notifications.models import Notification
    from apps.telegram import bots, services

    from django.db import connection

    tenant = TenantFactory(schema_name=connection.schema_name)  # «текущая» схема теста
    links.bind(UID, tenant, user_pk=_user().pk)
    monkeypatch.setattr(bots, "platform_bot", lambda: bots.BotRef(bots.PLATFORM, "t", "b"))

    def boom(*a, **k):
        raise services.TelegramAPIError("sendMessage", status=403)

    monkeypatch.setattr(services, "send_message", boom)
    n = Notification(recipient=str(UID), payload={"bot": "platform", "body": "x"})
    with pytest.raises(RuntimeError, match="403"):
        adapters._send_platform(n)
    assert OwnerTelegramLink.objects.get(tg_user_id=UID, tenant=tenant).blocked_at is not None


def test_sentry_scrubs_breadcrumb_urls_and_spans():
    from config.settings import production

    token = "123456:ABC-DEF_ghi"
    event = {
        "breadcrumbs": {"values": [{"data": {"url": f"https://api.telegram.org/bot{token}/x"}}]},
        "spans": [{"description": f"GET https://api.telegram.org/bot{token}/x", "data": {}}],
    }
    out = production._sentry_before_send(event, {})
    assert token not in str(out)
    crumb = production._sentry_before_breadcrumb({"data": {"url": f"bot{token}"}}, {})
    assert token not in str(crumb)
