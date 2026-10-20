"""T-8.10h H-3: подключение бизнеса к общему боту из кабинета (план §6)."""

import logging
import re
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from apps.core import views
from apps.core.models import Membership
from apps.platform_bot import connect, handler, links, webhook
from apps.platform_bot.models import OwnerTelegramLink
from apps.tenants.tests.factories import TenantFactory

USER = 777000111222
SECRET = "s" * 32

pytestmark = pytest.mark.django_db


@pytest.fixture
def on(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:abc"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    settings.TELEGRAM_PLATFORM_WEBHOOK_SECRET = SECRET
    settings.ROOT_URLCONF = "config.urls_tenant"
    return settings


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(
        "apps.telegram.services.send_message",
        lambda token, chat, text, reply_markup=None: out.append((chat, text, reply_markup)),
    )
    monkeypatch.setattr("apps.telegram.services.answer_callback_query", lambda *a, **k: None)
    return out


@pytest.fixture
def mails(monkeypatch):
    out = []
    monkeypatch.setattr(
        "apps.platform_bot.tasks.send_connected_email.delay", lambda **kw: out.append(kw)
    )
    return out


def _owner(tenant, role=Membership.ROLE_OWNER, name="owner"):
    user = get_user_model().objects.create_user(
        username=f"{name}-{tenant.pk}", password="pw12345678", email=f"{name}@example.com"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _tenant(slug, schema="public"):
    return TenantFactory(schema_name=schema, slug=slug, name=f"Laden {slug}")


def _start(raw, uid=USER, update_id=1, chat=None):
    return webhook.slim(
        {
            "update_id": update_id,
            "message": {
                "chat": {"id": chat or uid, "type": "private"},
                "from": {"id": uid, "is_bot": False, "language_code": "de"},
                "text": f"/start b-{raw}",
            },
        }
    )


def _raw(link):
    return link.split("start=b-", 1)[1]


# --- токен ----------------------------------------------------------------------------


def test_issue_stores_only_hash_and_ttl(on):
    tenant = _tenant("h3a")
    user = _owner(tenant)
    with mock.patch.object(connect.cache, "set", wraps=cache.set) as setter:
        link = connect.issue(tenant, user, lang="de")
    raw = _raw(link)
    assert link.startswith("https://t.me/PlattformBot?start=b-")
    for call in setter.call_args_list:
        key, value, ttl = call.args
        assert raw not in key and raw not in str(value)
        assert ttl <= 900


def test_new_token_invalidates_previous(on):
    tenant = _tenant("h3b")
    user = _owner(tenant)
    first = _raw(connect.issue(tenant, user))
    second = _raw(connect.issue(tenant, user))
    assert connect.consume(first) is None
    assert connect.consume(second)["schema"] == tenant.schema_name


def test_consume_is_single_use_and_rejects_garbage(on):
    tenant = _tenant("h3c")
    raw = _raw(connect.issue(tenant, _owner(tenant)))
    assert connect.consume(raw) is not None
    assert connect.consume(raw) is None
    for junk in ("", "../x", "a" * 100, "ü" * 30, None):
        assert connect.consume(junk) is None


def test_issue_without_platform_bot_gives_nothing(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    tenant = _tenant("h3d")
    assert connect.issue(tenant, _owner(tenant)) == ""


# --- бот: /start b-… ------------------------------------------------------------------


def test_start_b_token_binds_mirrors_and_mails_once(on, sent, mails):
    tenant = _tenant("h3e")
    raw = _raw(connect.issue(tenant, _owner(tenant)))
    assert handler.handle(_start(raw, update_id=1)) == "connected"
    assert handler.handle(_start(raw, update_id=2)) == "connect_invalid"  # тот же токен
    link = OwnerTelegramLink.objects.get(tenant=tenant)
    assert link.is_active and link.via == OwnerTelegramLink.VIA_CABINET
    tenant.refresh_from_db()
    node = tenant.site_config["notify"]
    assert node["owner_chat_id"] == str(USER) and node["owner_bot"] == "platform"
    assert tenant.name in sent[0][1]
    assert len(mails) == 1 and mails[0]["email"] == "owner@example.com"


def test_start_b_refuses_non_owner_at_consume_time(on, sent, mails):
    tenant = _tenant("h3f")
    user = _owner(tenant)
    raw = _raw(connect.issue(tenant, user))
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    assert handler.handle(_start(raw)) == "connect_invalid"
    assert not OwnerTelegramLink.objects.exists() and not mails
    assert connect.consume(raw) is None  # токен сгорел


def test_start_b_from_foreign_chat_is_ignored(on, sent):
    tenant = _tenant("h3g")
    raw = _raw(connect.issue(tenant, _owner(tenant)))
    assert handler.handle(_start(raw, chat=5)) == "skip"
    assert not OwnerTelegramLink.objects.exists()


def test_start_b_rate_limited_per_tg_user(on, sent, monkeypatch, isolated_ratelimit):
    consume = mock.Mock(return_value=None)
    monkeypatch.setattr(connect, "consume", consume)
    for i in range(handler.CONNECT_LIMIT + 1):
        handler.handle(_start("x" * 32, update_id=i + 1))
    assert consume.call_count == handler.CONNECT_LIMIT


def test_token_never_logged(on, sent, mails, caplog, monkeypatch):
    tenant = _tenant("h3h")
    raw = _raw(connect.issue(tenant, _owner(tenant)))

    def boom(*a, **k):
        raise RuntimeError(f"https://api.telegram.org/bot123:abc/sendMessage?text=b-{raw}")

    monkeypatch.setattr("apps.telegram.services.send_message", boom)
    with caplog.at_level(logging.DEBUG):
        handler.handle(_start(raw))
    assert all(raw not in r.getMessage() for r in caplog.records)


# --- /geschaeft и выбор бизнеса ---------------------------------------------------------


def test_geschaeft_lists_only_own_links_and_selects(on, sent):
    a, b, foreign = _tenant("h3i", "h3i"), _tenant("h3j", "h3j"), _tenant("h3k", "h3k")
    links.bind(USER, a)
    links.bind(USER, b)
    other = links.bind(USER + 1, foreign)
    msg = _start("x")
    msg["message"]["text"] = "/geschaeft"
    assert handler.handle(msg) == "choose_menu"
    buttons = [row[0] for row in sent[-1][2]["inline_keyboard"]]
    assert len(buttons) == 2
    assert all(re.match(r"^g:[0-9a-f-]{36}$", btn["callback_data"]) for btn in buttons)
    assert all(foreign.name not in btn["text"] for btn in buttons)

    def cb(data, from_id=USER, chat_id=USER):
        return webhook.slim(
            {
                "update_id": 99,
                "callback_query": {
                    "id": "c1",
                    "from": {"id": from_id},
                    "message": {"chat": {"id": chat_id}, "message_id": 1},
                    "data": data,
                },
            }
        )

    target = OwnerTelegramLink.objects.get(tg_user_id=USER, tenant=a)
    assert handler.handle(cb(f"g:{target.pk}")) == "chosen"
    assert links.active_links(USER).first().tenant == a
    assert handler.handle(cb(f"g:{other.pk}")) == "choose_denied"  # чужая связь
    assert handler.handle(cb("g:zzz")) == "skip"
    assert handler.handle(cb(f"g:{target.pk}", chat_id=5)) == "skip"
    other.refresh_from_db()
    assert other.selected_at is not None  # чужое не тронуто нашим выбором (только bind)


# --- кабинет --------------------------------------------------------------------------


def _cabinet(path, user, tenant, method="post"):
    req = getattr(RequestFactory(), method)(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = tenant
    req._dont_enforce_csrf_checks = True
    return req


def test_connect_view_owner_only_post_only(on, isolated_ratelimit):
    tenant = _tenant("h3l")
    owner = _owner(tenant)
    url = "/dashboard/settings/notifications/telegram/connect/"
    assert views.platform_bot_connect(_cabinet(url, owner, tenant, "get")).status_code == 405
    resp = views.platform_bot_connect(_cabinet(url, owner, tenant))
    assert resp.status_code == 302 and resp["Location"].startswith(
        "https://t.me/PlattformBot?start=b-"
    )
    staff = _owner(tenant, role=Membership.ROLE_STAFF, name="staff")
    Membership.objects.filter(user=owner).delete()
    assert views.platform_bot_connect(_cabinet(url, staff, tenant)).status_code == 403


def test_connect_view_404_when_platform_disabled(settings):
    from django.http import Http404

    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    tenant = _tenant("h3m")
    with pytest.raises(Http404):
        views.platform_bot_connect(
            _cabinet("/dashboard/settings/notifications/telegram/connect/", _owner(tenant), tenant)
        )


def test_connect_issue_rate_limited_per_schema(on, isolated_ratelimit):
    tenant = _tenant("h3n")
    owner = _owner(tenant)
    url = "/dashboard/settings/notifications/telegram/connect/"
    codes = [
        views.platform_bot_connect(_cabinet(url, owner, tenant))["Location"] for _ in range(11)
    ]
    assert codes[-1].endswith("/dashboard/settings/notifications/")


def test_owner_only_prefix_covers_new_urls():
    from django.urls import reverse

    from apps.core.middleware import CabinetOwnerAccessMiddleware

    for name in ("platform-bot-connect", "platform-bot-disconnect"):
        path = reverse(name, urlconf="config.urls_tenant")
        assert path.startswith(CabinetOwnerAccessMiddleware._OWNER_ONLY)


def test_page_shows_platform_button_and_status(on):
    tenant = _tenant("h3o")
    owner = _owner(tenant)
    req = _cabinet("/dashboard/settings/notifications/", owner, tenant, "get")
    html = views.notifications_settings(req).content.decode()
    assert "data-platform-connect" in html and "Mit Telegram verbinden" in html
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    req = _cabinet("/dashboard/settings/notifications/", owner, tenant, "get")
    html = views.notifications_settings(req).content.decode()
    assert "Verbunden über Plattform-Bot" in html and "data-platform-connect" not in html


def test_page_unchanged_when_platform_disabled(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant("h3p")
    req = _cabinet("/dashboard/settings/notifications/", _owner(tenant), tenant, "get")
    html = views.notifications_settings(req).content.decode()
    assert "data-platform-connect" not in html


def test_disconnect_paths_deactivate_platform_link(on):
    tenant = _tenant("h3q")
    owner = _owner(tenant)
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    views.platform_bot_disconnect(
        _cabinet("/dashboard/settings/notifications/telegram/disconnect/", owner, tenant)
    )
    tenant.refresh_from_db()
    assert not links.is_owner(USER, tenant)
    assert "owner_chat_id" not in tenant.site_config["notify"]


def test_stale_matrix_save_does_not_resurrect_unbound_chat(on):
    """Save матрицы со старым объектом тенанта не возвращает чат, отключённый ботом."""
    tenant = _tenant("h3r")
    owner = _owner(tenant)
    links.bind(USER, tenant)
    stale = type(tenant).objects.get(pk=tenant.pk)
    links.unbind(tenant)
    req = _cabinet("/dashboard/settings/notifications/", owner, stale)
    req.POST = req.POST.copy()
    views.notifications_settings(req)
    tenant.refresh_from_db()
    assert "owner_chat_id" not in tenant.site_config["notify"]


def test_own_bot_start_takes_over_from_platform(on):
    from apps.telegram import notify

    tenant = _tenant("h3s")
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    node = dict(tenant.site_config["notify"], owner_link_token="tok")
    tenant.site_config["notify"] = node
    tenant.save()
    assert notify.link_owner_from_start("owner-tok", 555, tenant)
    tenant.refresh_from_db()
    node = tenant.site_config["notify"]
    assert node["owner_bot"] == "tenant" and node["owner_chat_id"] == "555"
    assert node["owner_link_token"] != "tok"
    assert not links.is_owner(USER, tenant)


# --- доставка владельцу ---------------------------------------------------------------


def test_send_to_owner_routes_platform_and_rechecks_at_delivery(on, monkeypatch):
    from apps.notifications import adapters
    from apps.notifications.models import Notification
    from apps.telegram import notify

    tenant = _tenant("h3t")
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    notify.send_to_owner(tenant, type="t", dedupe_key="h3t-1", text="Hallo")
    row = Notification.objects.get(dedupe_key="h3t-1")
    assert row.payload["bot"] == "platform" and row.recipient == str(USER)
    calls = []
    monkeypatch.setattr(
        "apps.telegram.services.send_message",
        lambda token, chat, text, reply_markup=None: calls.append(token),
    )
    adapters.send(row)
    assert calls == ["123:abc"]
    links.unbind(tenant)
    with pytest.raises(RuntimeError):
        adapters.send(row)


def test_send_to_owner_tenant_bot_payload_unchanged(on):
    from apps.notifications.models import Notification
    from apps.telegram import notify
    from apps.telegram.models import TelegramBot

    tenant = _tenant("h3u")
    TelegramBot.objects.create(token="999:own", bot_username="OwnBot", is_active=True)
    tenant.site_config = {"notify": {"owner_chat_id": "42"}}
    tenant.save()
    notify.send_to_owner(tenant, type="t", dedupe_key="h3u-1", text="Hallo")
    assert "bot" not in Notification.objects.get(dedupe_key="h3u-1").payload


def test_send_to_owner_noop_when_platform_link_blocked(on):
    from apps.notifications.models import Notification
    from apps.telegram import notify

    tenant = _tenant("h3v")
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    links.mark_blocked(USER)
    notify.send_to_owner(tenant, type="t", dedupe_key="h3v-1", text="Hallo")
    assert not Notification.objects.filter(dedupe_key="h3v-1").exists()


# --- каналы ---------------------------------------------------------------------------


def test_personal_channels_ready_via_platform_and_default(on):
    from apps.core.personal_channels import personal_channels

    tenant = _tenant("h3w")
    card = next(r for r in personal_channels(tenant) if r["key"] == "telegram")
    assert card["ready"] is False
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    card = next(r for r in personal_channels(tenant) if r["key"] == "telegram")
    assert card["ready"] is True and "Plattform" in str(card["hint"])


# --- правки ревью (2026-10-20) ----------------------------------------------------------


def test_network_error_never_puts_bot_token_into_last_error(on, monkeypatch):
    import requests

    from apps.notifications import adapters
    from apps.notifications.models import Notification
    from apps.telegram import notify

    tenant = _tenant("h3x")
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    notify.send_to_owner(tenant, type="t", dedupe_key="h3x-1", text="Hallo")
    row = Notification.objects.get(dedupe_key="h3x-1")

    def boom(*a, **k):
        raise requests.ConnectionError("Max retries exceeded with url: /bot123:abc/sendMessage")

    monkeypatch.setattr("apps.telegram.services.send_message", boom)
    with pytest.raises(RuntimeError) as exc:
        adapters.send(row)
    assert "123:abc" not in str(exc.value) and exc.value.__cause__ is None


def test_demoted_issuer_stops_platform_delivery(on, sent, mails):
    from apps.notifications.models import Notification
    from apps.telegram import notify

    tenant = _tenant("h3y")
    user = _owner(tenant)
    raw = _raw(connect.issue(tenant, user))
    assert handler.handle(_start(raw)) == "connected"
    tenant.refresh_from_db()
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    notify.send_to_owner(tenant, type="t", dedupe_key="h3y-1", text="Hallo")
    assert not Notification.objects.filter(dedupe_key="h3y-1").exists()


def test_staff_cannot_disconnect_owner_telegram(on):
    tenant = _tenant("h3z")
    staff = _owner(tenant, role=Membership.ROLE_STAFF, name="staff")
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    req = _cabinet("/dashboard/settings/notifications/", staff, tenant)
    req.POST = req.POST.copy()
    req.POST["action"] = "disconnect_owner"
    views.notifications_settings(req)
    assert links.is_owner(USER, tenant)


def test_bind_failure_keeps_token_for_retry(on, sent, mails, monkeypatch):
    tenant = _tenant("h3za")
    raw = _raw(connect.issue(tenant, _owner(tenant)))
    monkeypatch.setattr(links, "bind", mock.Mock(side_effect=RuntimeError("db")))
    with pytest.raises(RuntimeError):
        handler.handle(_start(raw))
    assert connect.consume(raw) is not None  # повтор апдейта примет ту же ссылку


def test_blocked_platform_link_is_not_shown_as_connected(on):
    tenant = _tenant("h3zb")
    owner = _owner(tenant)
    links.bind(USER, tenant)
    links.mark_blocked(USER)
    tenant.refresh_from_db()
    req = _cabinet("/dashboard/settings/notifications/", owner, tenant, "get")
    html = views.notifications_settings(req).content.decode()
    assert "data-platform-connect" in html and "Verbunden über Plattform-Bot" not in html
