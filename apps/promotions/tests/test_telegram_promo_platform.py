"""T-8.10h H-4: акции через ОБЩИЙ бот платформы — план §7 (тот же конвейер, что у своего
бота; права — по таблице связей; кнопки `pb:` с адресом превью в кэше)."""

import re
import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache

from apps.core.models import Membership
from apps.platform_bot import handler, links, routing, webhook
from apps.promotions import telegram_promo as tp
from apps.promotions.models import Promotion
from apps.telegram import services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

USER = 777000111222
PB_RE = re.compile(r"^pb:[A-Za-z0-9_-]{12}$")


@pytest.fixture
def plat(monkeypatch, settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:plat"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    from apps.platform_bot import config

    config.reset_cache()
    monkeypatch.setattr("django_tenants.models.schema_exists", lambda name: True)
    store = LocMemCache(f"tgplat-{uuid.uuid4()}", {})
    monkeypatch.setattr(tp, "cache", store)
    monkeypatch.setattr(routing, "cache", store)
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-{uuid.uuid4()}", {}))
    sent, answers, queued = [], [], []

    def _send(token, chat, text, reply_markup=None):
        sent.append({"token": token, "chat": chat, "text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr(services, "send_message", _send)
    monkeypatch.setattr(
        services,
        "send_photo",
        lambda t, c, f, text, reply_markup=None: _send(t, c, text, reply_markup),
    )
    monkeypatch.setattr(
        services, "answer_callback_query", lambda token, cid, text="": answers.append(text)
    )
    monkeypatch.setattr(services, "edit_message_reply_markup", lambda *a, **k: None)
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    tenant = TenantFactory(schema_name="public", slug="plat-a", name="Bäckerei Alpha")
    links.bind(USER, tenant)
    tenant.refresh_from_db()

    def _confirm_delay(**kw):  # ✅ — тело Celery-задачи сразу
        queued.append(dict(kw))
        kw.pop("dedupe_key")
        state["confirm"] = tp.handle_confirm(**kw)

    monkeypatch.setattr("apps.promotions.tasks.telegram_owner_confirm.delay", _confirm_delay)
    state = {"tenant": tenant, "sent": sent, "answers": answers, "queued": queued}
    return state


def _message(text, update_id=1, **extra):
    return webhook.slim(
        {
            "update_id": update_id,
            "message": {
                "chat": {"id": USER, "type": "private"},
                "from": {"id": USER, "is_bot": False, "language_code": "de"},
                "text": text,
                **extra,
            },
        }
    )


def _callback(data, from_id=USER, chat_id=USER):
    return webhook.slim(
        {
            "update_id": 99,
            "callback_query": {
                "id": "c9",
                "from": {"id": from_id, "language_code": "de"},
                "message": {"chat": {"id": chat_id}, "message_id": 5},
                "data": data,
            },
        }
    )


def _preview(plat, text="Brötchen 2,50 € statt 3,90 € heute bis 23 Uhr, 20 Stück"):
    assert handler.handle(_message(text)) == "preview"
    preview = plat["sent"][-1]
    buttons = preview["markup"]["inline_keyboard"][0]
    return preview, [b["callback_data"] for b in buttons if "callback_data" in b]


def test_platform_message_drafts_with_pb_buttons_and_business(plat):
    preview, data = _preview(plat)
    assert preview["token"] == "123:plat"
    assert "Für: Bäckerei Alpha" in preview["text"]
    assert data and all(PB_RE.match(d) and len(d.encode()) <= 64 for d in data)
    ok = routing.resolve(USER, data[0])
    assert ok[0] == "public" and ok[1].startswith("tp:ok:")


def test_confirm_via_pb_publishes_once(plat):
    _p, data = _preview(plat)
    assert handler.handle(_callback(data[0])) == "queued"
    assert plat["confirm"] == "published"
    assert plat["queued"][0]["bot_kind"] == "platform"
    assert plat["queued"][0]["dedupe_key"].startswith("tgcb:public:p:")
    assert Promotion.objects.get().status == "active"
    assert "Für: Bäckerei Alpha" in plat["sent"][-1]["text"]
    handler.handle(_callback(data[0]))
    assert plat["confirm"] == "already" and Promotion.objects.count() == 1


def test_pb_callback_answered_once_on_success(plat):
    _p, data = _preview(plat)
    plat["answers"].clear()
    handler.handle(_callback(data[-1]))  # ❌
    assert plat["answers"] == [""]


def test_foreign_user_cannot_use_ref(plat):
    _p, data = _preview(plat)
    assert handler.handle(_callback(data[0], from_id=5, chat_id=5)) == "expired"
    assert handler.handle(_callback(data[0], chat_id=5)) == "skip"
    assert Promotion.objects.count() == 0


def test_resolve_rejects_tampered_cache_value(plat):
    routing.cache.set(routing._key(USER, "A" * 12), {"schema": "x;drop", "data": "tp:ok:bad"})
    assert routing.resolve(USER, "pb:" + "A" * 12) is None


def test_demoted_owner_is_denied_message_and_confirm(plat):
    from django.contrib.auth import get_user_model

    tenant = plat["tenant"]
    user = get_user_model().objects.create_user(username="o4", password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    links.bind(USER, tenant, user_pk=user.pk)
    _p, data = _preview(plat)
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    assert handler.handle(_message("Brötchen −30 % heute", update_id=2)) == "denied"
    assert handler.handle(_callback(data[0])) == "denied"
    assert Promotion.objects.count() == 0


def test_unbind_between_tap_and_task_skips(plat, monkeypatch):
    _p, data = _preview(plat)
    real = tp.handle_confirm

    def late(**kw):
        links.unbind(plat["tenant"])
        return real(**kw)

    monkeypatch.setattr(tp, "handle_confirm", late)
    handler.handle(_callback(data[0]))
    assert plat["confirm"] == "skip" and Promotion.objects.count() == 0


def test_wiederholen_menu_uses_pb_refs(plat):
    Promotion.objects.create(title={"de": "Altes Brot"}, status="ended")
    assert handler.handle(_message("/wiederholen")) == "repeat_menu"
    rows = plat["sent"][-1]["markup"]["inline_keyboard"]
    assert all(PB_RE.match(r[0]["callback_data"]) for r in rows)
    assert handler.handle(_callback(rows[0][0]["callback_data"])) == "preview"


def test_bare_start_greets_and_unlinked_gets_onboarding(plat):
    assert handler.handle(_message("/start")) == "welcome_back"
    links.unbind(plat["tenant"])
    assert handler.handle(_message("Brötchen −30 % heute", update_id=3)) == "onboarding"


def test_tenant_bot_claim_keeps_platform_route(plat):
    """T-8.29 (Р-1): свой бот забирает только уведомления — акции через общий бот живут."""
    links.claim_for_tenant_bot(plat["tenant"], USER, rotate_token="x")
    assert handler.handle(_message("Brötchen −30 % heute", update_id=4)) == "preview"


def test_load_for_web_finds_platform_draft_with_stale_mirror(plat):
    _p, data = _preview(plat)
    token = routing.resolve(USER, data[0])[1].split(":", 2)[2]
    tenant = plat["tenant"]
    tenant.site_config["notify"].pop("owner_chat_id")
    assert tp.load_for_web(tenant, token) is not None


def test_tenant_preview_has_no_pb_or_business_line(plat):
    from apps.promotions import message_parse

    draft = tp.draft_from_parsed(message_parse.parse("Brot −30 % heute"), plat["tenant"])
    text, markup = tp.render_preview(
        draft, plat["tenant"], tp.form_for(draft, plat["tenant"]), "T" * 16
    )
    assert "Für:" not in text
    assert [b["callback_data"] for b in markup["inline_keyboard"][0] if "callback_data" in b] == [
        "tp:ok:" + "T" * 16,
        "tp:no:" + "T" * 16,
    ]


def test_tap_after_switch_confirms_in_preview_schema(plat, monkeypatch):
    """После /geschaeft ✅ старого превью идёт в схему ПРЕВЬЮ (ref), не текущего бизнеса."""
    _p, data = _preview(plat)
    other = TenantFactory(schema_name="zz_other", slug="plat-b", name="Laden B")
    links.bind(USER, other)  # текущий — B
    seen = []
    real = tp.handle_platform_callback
    monkeypatch.setattr(
        tp,
        "handle_platform_callback",
        lambda bot, schema, cb, inner: seen.append(schema) or real(bot, schema, cb, inner),
    )
    handler.handle(_callback(data[0]))
    assert seen == ["public"]
    assert plat["queued"][-1]["schema"] == "public"


def test_platform_album_collects_photos(plat, monkeypatch):
    monkeypatch.setattr(tp, "ai_fill", lambda *a, **k: False)
    first = _message("", update_id=11, photo=[{"file_id": "p1"}], media_group_id="g1")
    assert handler.handle(first) == "album_wait"
    second = _message(
        "Brot −30 % heute", update_id=12, photo=[{"file_id": "p2"}], media_group_id="g1"
    )
    second["message"]["text"] = "Brot −30 % heute"
    assert handler.handle(second) == "preview"
    assert "📷 2" in plat["sent"][-1]["text"]


def test_platform_rate_limit(plat, monkeypatch):
    monkeypatch.setattr(tp, "RATE_LIMIT", 1)
    assert handler.handle(_message("Brot −30 % heute", update_id=21)) == "preview"
    assert handler.handle(_message("Brot −30 % heute", update_id=22)) == "limited"


def test_confirm_task_accepts_platform_kwargs(monkeypatch):
    """Задача ✅ принимает ровно то, что шлёт enqueue_confirm (вкл. bot_kind)."""
    from apps.promotions import tasks

    seen = {}
    monkeypatch.setattr(tp, "handle_confirm", lambda *a, **kw: seen.update(args=a, **kw) or "ok")
    tasks.telegram_owner_confirm(
        schema="public", chat="1", token="t", message_id=1, language_code="de", bot_kind="platform"
    )
    assert seen.get("bot_kind") == "platform" or "platform" in seen.get("args", ())
