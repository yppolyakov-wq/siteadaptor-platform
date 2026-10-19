"""T-8.10b B-1: акция из сообщения владельца в Telegram — замки плана §6.

Клиентский чат — прежний ответ; только владелец (личный чат) получает черновик; ✅
проходит ту же форму и хвост, что веб-ассистент; двойной ✅ — одна акция; ❌ и протухший
черновик; лимит; подписка; ✏️ в вебе и поздний ✅."""

import uuid

import pytest
from django.utils.translation import gettext
from django.core.cache.backends.locmem import LocMemCache

from apps.promotions import limits
from apps.promotions import telegram_promo as tp
from apps.promotions.models import Promotion
from apps.telegram import notify, services
from apps.telegram import webhook as wh
from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

OWNER = 4242


@pytest.fixture
def tg(monkeypatch):
    store = LocMemCache(f"tgpromo-{uuid.uuid4()}", {})
    monkeypatch.setattr(tp, "cache", store)
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-{uuid.uuid4()}", {}))
    sent = []

    def _send(token, chat, text, reply_markup=None):
        sent.append({"chat": chat, "text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr(services, "send_message", _send)
    monkeypatch.setattr(
        services,
        "send_photo",
        lambda t, c, f, text, reply_markup=None: _send(t, c, text, reply_markup),
    )
    monkeypatch.setattr(services, "answer_callback_query", lambda *a, **k: None)
    monkeypatch.setattr(services, "edit_message_reply_markup", lambda *a, **k: None)
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    bot = TelegramBot.objects.create(token="t", bot_username="ShopBot", is_active=True)
    tenant = TenantFactory()
    notify._save_notify_node(tenant, {"owner_chat_id": str(OWNER)})
    return {"bot": bot, "tenant": tenant, "sent": sent, "cache": store}


def _req(tenant):
    return type(
        "R", (), {"build_absolute_uri": lambda self, u: "https://shop.test/", "tenant": tenant}
    )()


def _msg(text, chat=OWNER, sender=OWNER, kind="private", **extra):
    return {
        "update_id": extra.pop("update_id", 1),
        "message": {
            "chat": {"id": chat, "type": kind},
            "from": {"id": sender, "is_bot": False, "language_code": "de"},
            "text": text,
            **extra,
        },
    }


def _draft(tg, text="Brötchen 2,50 € statt 3,90 € heute bis 23 Uhr, 20 Stück"):
    """Сообщение владельца → (token, превью) напрямую через тело задачи."""
    slim = tp.slim_update(_msg(text))
    result = tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim)
    assert result == "preview", result
    preview = tg["sent"][-1]
    buttons = preview["markup"]["inline_keyboard"][0]
    ok = next(b for b in buttons if b.get("callback_data", "").startswith("tp:ok:"))
    return ok["callback_data"].split(":", 2)[2], preview


def _cb(tg, data, sender=OWNER, chat=OWNER):
    return tp.handle_callback(
        tg["bot"],
        {
            "id": "c1",
            "from": {"id": sender},
            "message": {"chat": {"id": chat}, "message_id": 7},
            "data": data,
        },
        tg["tenant"],
    )


# --- маршрутизация --------------------------------------------------------------------


def test_customer_chat_unchanged(tg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.promotions.tasks.telegram_owner_message.delay", lambda **kw: calls.append(kw)
    )
    assert (
        wh.handle_update(tg["bot"], _msg("Brötchen −30 %", chat=99, sender=99), _req(tg["tenant"]))
        == "sent"
    )
    assert tg["sent"][-1]["text"] == gettext("Tap below to open the shop.")
    assert "web_app" in tg["sent"][-1]["markup"]["inline_keyboard"][0][0]
    assert calls == []


def test_owner_message_is_queued_with_update_dedupe(tg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.promotions.tasks.telegram_owner_message.delay", lambda **kw: calls.append(kw)
    )
    out = wh.handle_update(tg["bot"], _msg("Brötchen −30 %", update_id=77), _req(tg["tenant"]))
    assert out == "queued" and calls[0]["dedupe_key"].endswith(":77")
    assert calls[0]["update"]["text"] == "Brötchen −30 %"


def test_owner_start_and_group_keep_their_branches(tg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.promotions.tasks.telegram_owner_message.delay", lambda **kw: calls.append(kw)
    )
    wh.handle_update(tg["bot"], _msg("/start"), _req(tg["tenant"]))
    assert tg["sent"][-1]["text"] == gettext("Welcome! Tap below to open the shop.")
    monkeypatch.setattr(wh, "_handle_group", lambda bot, m, c: "group")
    assert (
        wh.handle_update(tg["bot"], _msg("Brötchen −30 %", kind="group"), _req(tg["tenant"]))
        == "group"
    )
    assert calls == []


def test_owner_in_foreign_chat_or_spoofed_sender_not_owner(tg):
    assert not tp.is_owner_private(_msg("x", chat=OWNER, sender=1)["message"], tg["tenant"])
    assert not tp.is_owner_private(_msg("x", chat=1, sender=OWNER)["message"], tg["tenant"])
    bot_msg = _msg("x")["message"]
    bot_msg["from"]["is_bot"] = True
    assert not tp.is_owner_private(bot_msg, tg["tenant"])


def test_broker_down_answers_honestly(tg, monkeypatch):
    def down(**kw):
        raise ConnectionError("broker")

    monkeypatch.setattr("apps.promotions.tasks.telegram_owner_message.delay", down)
    assert wh.handle_update(tg["bot"], _msg("Brötchen −30 %"), _req(tg["tenant"])) == "failed"
    assert "Gerade nicht möglich" in tg["sent"][-1]["text"]


def test_callback_from_stranger_denied(tg):
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:ok:{token}", sender=1) == "denied"
    assert Promotion.objects.count() == 0


def test_set_webhook_subscribes_callbacks(monkeypatch):
    seen = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def post(url, data=None, timeout=None):
        seen.update(data)
        return R()

    monkeypatch.setattr("apps.telegram.services.requests.post", post)
    services.set_webhook("t", "https://x/tg/s/", "s")
    assert "callback_query" in seen["allowed_updates"]


# --- черновик и публикация ------------------------------------------------------------


def test_hint_without_signals_and_question_without_title(tg):
    slim = tp.slim_update(_msg("Ruf an: 0212 123456"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "hint"
    slim = tp.slim_update(_msg("−30 %"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "no_title"


def test_preview_shows_parsed_facts(tg):
    _token, preview = _draft(tg)
    assert "Brötchen" in preview["text"] and "20 Stück" in preview["text"]
    assert "2,50" in preview["text"] and "3,90" in preview["text"]


def test_double_confirm_creates_one_promotion(tg):
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:ok:{token}") == "published"
    assert _cb(tg, f"tp:ok:{token}") == "already"
    promo = Promotion.objects.get()
    assert promo.status == "active"
    assert str(promo.price_override) == "2.50" and str(promo.compare_at_price) == "3.90"
    assert promo.available_quantity == 20
    assert "Schon veröffentlicht" in tg["sent"][-1]["text"]


def test_discard_then_confirm_is_expired(tg):
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:no:{token}") == "dropped"
    assert _cb(tg, f"tp:ok:{token}") == "expired"
    assert Promotion.objects.count() == 0


def test_limit_keeps_promotion_as_draft(tg, monkeypatch):
    def full(promo, tenant, actor=None):
        raise limits.ActivationLimit(5)

    monkeypatch.setattr(limits, "activate", full)
    monkeypatch.setattr(limits, "active_limit", lambda tenant: 5)
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:ok:{token}") == "draft"
    assert Promotion.objects.get().status == "draft"


def test_gated_subscription_refused(tg):
    tg["tenant"].subscription_status = "suspended"
    slim = tp.slim_update(_msg("Brötchen −30 % heute"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "gated"
    assert Promotion.objects.count() == 0


def test_garbage_callback_ignored(tg):
    assert _cb(tg, "tp:ok:../../etc") == "skip"
    assert _cb(tg, "xx") == "skip"


def test_relinked_owner_loses_old_drafts(tg):
    token, _p = _draft(tg)
    notify._save_notify_node(tg["tenant"], {"owner_chat_id": "999"})
    assert tp.load_for_web(tg["tenant"], token) is None


def test_web_edit_then_late_confirm(tg, monkeypatch):
    """✏️ сохранил акцию в вебе → поздний ✅ в Telegram новую не создаёт."""
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import views

    monkeypatch.setattr(tp, "connection", type("C", (), {"schema_name": "public"})())
    monkeypatch.setattr(views, "connection", type("C", (), {"schema_name": "public"})())
    token, _p = _draft(tg)
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username=f"o{uuid.uuid4().hex[:6]}", password="x")

    def req(method, data):
        r = getattr(RequestFactory(), method)("/promotions/schnell/", data)
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.user, r.tenant = user, tg["tenant"]
        return r

    get = (
        views.promotion_quick.__wrapped__(req("get", {"entwurf": token}))
        if hasattr(views.promotion_quick, "__wrapped__")
        else None
    )
    if get is not None:
        assert "Brötchen" in get.content.decode()
    draft = tp.load_for_web(tg["tenant"], token)
    data = {k: v for k, v in draft.items() if k not in ("photo_ids", "warnings") and v}
    data["entwurf"] = token
    view = getattr(views.promotion_quick, "__wrapped__", views.promotion_quick)
    resp = view(req("post", data))
    assert resp.status_code == 302
    assert _cb(tg, f"tp:ok:{token}") == "already"
    assert Promotion.objects.count() == 1
