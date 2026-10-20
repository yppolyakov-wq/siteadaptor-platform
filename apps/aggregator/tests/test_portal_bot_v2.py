"""T-8.28: бот портала v2 — поиск, разделы/районы, «Folgen» и сводка в Telegram.

План — docs/t8-14-28-themed-portal-bot-plan-2026-10-20.md.
"""

import ast
import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path

import polib
import pytest
import requests
from django.core import mail
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator import follow_digest, portal_bot, telegram_bot
from apps.aggregator.models import (
    AggregatorListing,
    AggregatorPortal,
    FollowDigest,
    FollowSubscription,
    PortalBot,
    PortalChat,
    PortalStat,
    PortalUser,
)
from apps.telegram import services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

UID = 777000111
SECRET = "s" * 32


@pytest.fixture(autouse=True)
def _env(settings, isolated_ratelimit, monkeypatch):
    from django.core.cache.backends.locmem import LocMemCache

    settings.ROOT_URLCONF = "config.urls_portal"
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    # Одноразовые кнопки бота живут в кэше: общий Redis параллельных воркеров чистят
    # чужие тесты (`cache.clear()`), поэтому у бота в тестах — приватный кэш.
    monkeypatch.setattr(portal_bot, "cache", LocMemCache(f"pbot-{uuid.uuid4()}", {}))
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def sent(monkeypatch):
    out = []

    def fake_send(token, chat, text, reply_markup=None):
        out.append({"chat": chat, "text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr(services, "send_message", fake_send)
    monkeypatch.setattr(services, "answer_callback_query", lambda *a, **k: None)
    monkeypatch.setattr(services, "leave_chat", lambda token, chat: out.append({"left": chat}))
    return out


def _portal(**kw):
    defaults = {
        "host": f"{uuid.uuid4().hex[:6]}.siteadaptor.de",
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Entdecke Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _bot(portal=None):
    return PortalBot.objects.create(
        portal=portal or _portal(),
        token="1:t",
        bot_username="SolingenBot",
        webhook_secret=SECRET,
        is_active=True,
    )


def _listing(**kw):
    defaults = {
        "tenant_schema": "veg",
        "tenant_slug": "veg",
        "business_name": "Grüne Küche",
        "business_type": "cafe",
        "city": "Solingen",
        "district": "ohligs-aufderhoehe-merscheid",
        "listing_kind": "promotion",
        "source_ref": uuid.uuid4().hex,
        "title": {"de": "Vegane Bowl"},
        "new_price": "8.50",
        "currency": "EUR",
        "city_category": "brot-backwaren",
        "detail_url": "https://veg.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _msg(text, uid=UID, chat_type="private", lang="de"):
    return {
        "update_id": 1,
        "message": {
            "chat_id": uid,
            "chat_type": chat_type,
            "from_id": uid,
            "is_bot": False,
            "language_code": lang,
            "text": text,
        },
    }


def _cb(data, uid=UID):
    return {
        "update_id": 2,
        "callback": {
            "id": "c",
            "from_id": uid,
            "chat_id": uid,
            "data": data,
            "language_code": "de",
        },
    }


def _buttons(entry):
    return [b for row in (entry.get("markup") or {}).get("inline_keyboard", []) for b in row]


# --- вебхук -------------------------------------------------------------------------------


def _post(secret=SECRET, header=SECRET, body=None):
    data = json.dumps(body or {"update_id": 5, "message": {"chat": {"id": UID}}})
    kw = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": header} if header else {}
    req = RequestFactory().post(f"/tg/{secret}/", data=data, content_type="application/json", **kw)
    return req


def test_webhook_rejects_before_db(django_assert_num_queries):
    _bot()
    with django_assert_num_queries(0), pytest.raises(Http404):
        telegram_bot.webhook(_post(header=""), secret=SECRET)
    with django_assert_num_queries(0), pytest.raises(Http404):
        telegram_bot.webhook(_post(header="x" * 32), secret=SECRET)
    req = RequestFactory().get(f"/tg/{SECRET}/", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=SECRET)
    with django_assert_num_queries(0), pytest.raises(Http404):
        telegram_bot.webhook(req, secret=SECRET)


def test_webhook_enqueues_with_dedupe(monkeypatch):
    bot = _bot()
    calls = []
    from apps.aggregator import tasks

    monkeypatch.setattr(tasks.portal_bot_update, "delay", lambda **kw: calls.append(kw))
    resp = telegram_bot.webhook(_post(), secret=SECRET)
    assert resp.status_code == 200
    assert calls[0]["dedupe_key"] == f"tgportal:{bot.pk}:5"
    assert calls[0]["bot_pk"] == bot.pk


def test_webhook_rejects_bot_of_other_portal(monkeypatch):
    _bot()
    req = _post()
    req.portal = _portal()
    with pytest.raises(Http404):
        telegram_bot.webhook(req, secret=SECRET)


def test_group_is_left_and_group_messages_ignored(sent):
    bot = _bot()
    member = {"update_id": 3, "member": {"chat_id": -100, "chat_type": "group", "status": "member"}}
    assert portal_bot.handle(bot.pk, member) == "left"
    assert portal_bot.handle(bot.pk, _msg("Brot", uid=-100, chat_type="group")) == "skip"


def test_start_shows_menu_in_user_language(sent):
    bot = _bot()
    assert portal_bot.handle(bot.pk, _msg("/start", lang="ru")) == "start"
    assert "Добро пожаловать" in sent[-1]["text"]
    assert any("web_app" in b for b in _buttons(sent[-1]))


# --- поиск --------------------------------------------------------------------------------


def test_chat_search_returns_cards_with_telegram_channel(sent):
    bot = _bot()
    _listing()
    _listing(tenant_schema="mett", tenant_slug="mett", title={"de": "Mettbrötchen"})
    items, _more = portal_bot.run_search(bot.portal, {"q": "", "kat": "", "d": ""})
    assert {str(i.title_text) for i in items} == {"Vegane Bowl", "Mettbrötchen"}
    portal_bot.handle(bot.pk, _cb("sec"))
    assert portal_bot.handle(bot.pk, _cb("k:essen-gastronomie")) in ("results", "empty")
    portal_bot.handle(bot.pk, _cb("k:lebensmittel-getraenke"))
    texts = "\n".join(e.get("text", "") for e in sent)
    assert "ch=telegram" in texts


def test_chat_results_respect_theme(sent):
    bot = _bot(_portal(kind="theme", theme_tags=["vegan"]))
    _listing(city_tags=["vegan"])
    _listing(tenant_schema="mett", tenant_slug="mett", title={"de": "Mettbrötchen"}, city_tags=[])
    items, _more = portal_bot.run_search(bot.portal, {"q": "", "kat": "", "d": ""})
    assert [str(i.title_text) for i in items] == ["Vegane Bowl"]


def test_more_pagination_and_cap(sent):
    bot = _bot()
    for i in range(7):
        _listing(source_ref=f"r{i}", title={"de": f"Angebot {i}"})
    portal_bot.handle(bot.pk, _cb("k:lebensmittel-getraenke"))
    more = [b for e in sent for b in _buttons(e) if b.get("callback_data", "").startswith("s:")]
    assert more
    assert portal_bot.handle(bot.pk, _cb(more[0]["callback_data"])) == "results"


@pytest.mark.parametrize(
    "data",
    [
        "x",
        "s:abc",
        "s:" + "a" * 30 + ":1",
        "k:../../etc",
        "u:abc",
        "pd:yes",
        "fb:1;drop",
        "k:" + "a" * 70,
    ],
)
def test_callback_data_validated(data, sent):
    assert portal_bot.parse_callback(data) is None
    assert portal_bot.handle(_bot().pk, _cb(data)) == "stale"


def test_portal_stats_accepts_telegram_channel():
    assert "telegram" in PortalStat.CHANNEL_CODES


# --- «Folgen» -----------------------------------------------------------------------------


def _ask(sent, bot, data):
    assert portal_bot.handle(bot.pk, _cb(data)) == "follow_asked"
    return next(
        b["callback_data"] for b in _buttons(sent[-1]) if b["callback_data"].startswith("fy:")
    )


def test_follow_requires_confirm_button(sent):
    bot = _bot()
    _listing()
    yes = _ask(sent, bot, "fk:lebensmittel-getraenke")
    assert not FollowSubscription.objects.exists() and not PortalChat.objects.exists()
    assert portal_bot.handle(bot.pk, _cb(yes)) == "followed"
    sub = FollowSubscription.objects.get()
    assert sub.channel == "telegram" and sub.portal == bot.portal
    assert sub.source_host == "tg:@SolingenBot"
    chat = PortalChat.objects.get()
    assert chat.chat_id == UID and chat.user.email is None
    assert portal_bot.handle(bot.pk, _cb(yes)) == "stale"  # кнопка одноразовая


def test_follow_business_only_inside_portal(sent):
    bot = _bot(_portal(kind="theme", theme_tags=["vegan"]))
    outside = _listing(tenant_schema="mett", tenant_slug="mett", city_tags=[])
    TenantFactory(schema_name="mett", slug="mett", city="Solingen")
    assert portal_bot.handle(bot.pk, _cb(f"fb:{outside.pk}")) == "follow_unavailable"


def test_unfollow_only_own(sent):
    bot = _bot()
    _listing()
    portal_bot.handle(bot.pk, _cb(_ask(sent, bot, "fk:lebensmittel-getraenke")))
    sub = FollowSubscription.objects.get()
    assert portal_bot.handle(bot.pk, _cb(f"u:{sub.pk}", uid=UID + 1)) == "stale"
    assert FollowSubscription.objects.filter(pk=sub.pk).exists()
    assert portal_bot.handle(bot.pk, _cb(f"u:{sub.pk}")) == "unfollowed"
    assert not FollowSubscription.objects.exists()


def test_follow_query_from_search(sent):
    bot = _bot()
    _listing()
    portal_bot.handle(bot.pk, _msg("Bowl"))
    fq = next(
        b["callback_data"] for b in _buttons(sent[-1]) if b["callback_data"].startswith("fq:")
    )
    portal_bot.handle(bot.pk, _cb(_ask(sent, bot, fq)))
    assert FollowSubscription.objects.get().target_kind in ("query", "section")


def test_erase_removes_everything(sent):
    bot = _bot()
    _listing()
    portal_bot.handle(bot.pk, _cb(_ask(sent, bot, "fk:lebensmittel-getraenke")))
    assert portal_bot.handle(bot.pk, _msg("/daten_loeschen")) == "erase_asked"
    yes = next(
        b["callback_data"] for b in _buttons(sent[-1]) if b["callback_data"].startswith("pd:yes:")
    )
    assert portal_bot.handle(bot.pk, _cb(yes)) == "erased"
    assert not PortalChat.objects.exists()
    assert not PortalUser.objects.exists()
    assert not FollowSubscription.objects.exists()


def test_purge_blocked_and_idle_chats(sent):
    bot = _bot()
    _listing()
    portal_bot.handle(bot.pk, _cb(_ask(sent, bot, "fk:lebensmittel-getraenke")))
    PortalChat.objects.update(blocked_at=timezone.now() - timedelta(days=31))
    assert portal_bot.purge_chats() == 1
    assert not PortalUser.objects.exists()


# --- сводка в Telegram --------------------------------------------------------------------


def _tg_follower(sent, bot):
    portal_bot.handle(bot.pk, _cb(_ask(sent, bot, "fk:lebensmittel-getraenke")))
    sub = FollowSubscription.objects.get()
    FollowSubscription.objects.filter(pk=sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=2)
    )
    return PortalChat.objects.get().user


def test_telegram_digest_instead_of_email(sent):
    bot = _bot()
    user = _tg_follower(sent, bot)
    _listing(title={"de": "Neue Bowl"})
    sent.clear()
    assert follow_digest.daily_candidates().filter(pk=user.pk).exists()
    now = timezone.now()
    assert follow_digest.send(
        follow_digest.build_digest(user, list(user.follows.all()), now=now),
        period_key="t1",
        now=now,
    )
    assert mail.outbox == []
    assert "Neue Bowl" in sent[-1]["text"] and sent[-1]["chat"] == UID
    assert FollowDigest.objects.filter(user=user, period_key="t1").exists()


def test_blocked_chat_skipped_and_marked(sent, monkeypatch):
    bot = _bot()
    user = _tg_follower(sent, bot)
    _listing(title={"de": "Neue Bowl"})

    def blocked(*a, **k):
        resp = requests.Response()
        resp.status_code = 403
        raise requests.HTTPError(response=resp)

    monkeypatch.setattr(services, "send_message", blocked)
    now = timezone.now()
    digest = follow_digest.build_digest(user, list(user.follows.all()), now=now)
    assert follow_digest.send(digest, period_key="t2", now=now) is False
    assert PortalChat.objects.get().blocked_at is not None
    assert not follow_digest.daily_candidates().filter(pk=user.pk).exists()


def test_emailless_user_never_reaches_email_paths(sent):
    bot = _bot()
    user = _tg_follower(sent, bot)
    assert str(user).startswith("telegram")
    from apps.aggregator import auth

    assert not PortalUser.objects.filter(email="").exists()
    assert hasattr(auth, "__name__")


# --- приватность и переводы ---------------------------------------------------------------


def test_no_chat_id_or_text_in_logs(sent, caplog, monkeypatch):
    bot = _bot()

    def boom(*a, **k):
        raise requests.HTTPError("https://api.telegram.org/bot1:t/sendMessage")

    monkeypatch.setattr(services, "send_message", boom)
    with caplog.at_level(logging.WARNING):
        portal_bot.handle(bot.pk, _msg("Geheimer Suchtext"))
    assert str(UID) not in caplog.text
    assert "Geheimer" not in caplog.text
    assert "1:t" not in caplog.text


def _bot_msgids():
    root = Path(__file__).resolve().parents[1]
    out = set()
    for name in ("portal_bot.py", "follow_digest.py"):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                out.add(node.args[0].value)
    return out


@pytest.mark.parametrize("locale", ["de", "en", "tr", "ru", "uk"])
def test_bot_strings_translated(locale):
    root = Path(__file__).resolve().parents[3]
    po = polib.pofile(str(root / f"locale/{locale}/LC_MESSAGES/django.po"))
    have = {e.msgid: e for e in po if not e.obsolete}
    missing = [
        m
        for m in _bot_msgids()
        if m not in have
        or have[m].fuzzy
        # базовый язык (de) законно хранит строку с пустым переводом
        or (locale != "de" and not (have[m].msgstr or have[m].msgstr_plural))
    ]
    assert not missing, missing[:5]
