"""T-8.10h H-6: DSGVO в общем боте — /datenschutz, /daten_loeschen, сроки хранения."""

import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.utils import timezone

from apps.platform_bot import handler, links, privacy, signup, webhook
from apps.platform_bot.models import OwnerTelegramLink
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

USER = 444000111222


@pytest.fixture
def bot(monkeypatch, settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:plat"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    store = LocMemCache(f"h6-{uuid.uuid4()}", {})
    monkeypatch.setattr(privacy, "cache", store)
    monkeypatch.setattr(signup, "cache", store)
    sent = []

    def _send(token, chat, text, reply_markup=None):
        sent.append({"text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr("apps.telegram.services.send_message", _send)
    monkeypatch.setattr("apps.telegram.services.answer_callback_query", lambda *a, **k: None)
    return {"sent": sent, "cache": store}


def _msg(text, update_id=1):
    return webhook.slim(
        {
            "update_id": update_id,
            "message": {
                "chat": {"id": USER, "type": "private"},
                "from": {"id": USER, "is_bot": False, "language_code": "de"},
                "text": text,
            },
        }
    )


def _cb(data, chat=USER):
    return webhook.slim(
        {
            "update_id": 9,
            "callback_query": {
                "id": "c",
                "from": {"id": USER, "language_code": "de"},
                "message": {"chat": {"id": chat}, "message_id": 1},
                "data": data,
            },
        }
    )


def _yes(bot):
    for row in bot["sent"][-1]["markup"]["inline_keyboard"]:
        if row[0]["callback_data"].startswith("pd:yes:"):
            return row[0]["callback_data"]
    raise AssertionError("no confirm button")


def test_datenschutz_shows_url_and_delete_button(bot):
    links.bind(USER, TenantFactory(schema_name="p1", slug="p1", name="Bäckerei Eins"))
    assert handler.handle(_msg("/datenschutz")) == "privacy_info"
    last = bot["sent"][-1]
    assert "/datenschutz/" in last["text"] and "Bäckerei Eins" in last["text"]
    assert last["markup"]["inline_keyboard"][0][0]["callback_data"] == "pd:ask"


def test_erase_command_beats_promo_pipeline_and_signup(bot, monkeypatch):
    links.bind(USER, TenantFactory(schema_name="p2", slug="p2"))
    promo = mock.Mock()
    monkeypatch.setattr("apps.promotions.telegram_promo.handle_owner_message", promo)
    assert handler.handle(_msg("/daten_loeschen")) == "erase_asked"
    promo.assert_not_called()
    assert OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()  # без подтверждения — ничего


def test_confirm_erases_all_links_and_own_traces_only(bot):
    a = TenantFactory(schema_name="p3", slug="p3")
    b = TenantFactory(schema_name="p4", slug="p4")
    own_bot = TenantFactory(schema_name="p5", slug="p5")
    links.bind(USER, a)
    links.bind(USER, b)
    links.bind(USER + 1, b)  # чужой пользователь перехватил b — его связь не трогаем
    OwnerTelegramLink.objects.create(tg_user_id=USER, tenant=own_bot, is_active=False)
    own_bot.site_config = {"notify": {"owner_chat_id": str(USER), "owner_bot": "tenant"}}
    own_bot.save()
    pending = TenantFactory(schema_name="p6", slug="p6")
    pending.site_config = {"notify": {"pending_tg_owner": {"uid": USER, "at": 10**10}}}
    pending.save()
    handler.handle(_msg("/daten_loeschen"))
    assert handler.handle(_cb(_yes(bot))) == "erased"
    assert not OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()
    assert OwnerTelegramLink.objects.filter(tg_user_id=USER + 1).exists()
    for t in (a, b, own_bot, pending):
        t.refresh_from_db()
    assert "owner_chat_id" not in a.site_config["notify"]
    assert b.site_config["notify"]["owner_chat_id"] == str(USER + 1)
    assert own_bot.site_config["notify"]["owner_bot"] == "tenant"  # свой бот бизнеса — его данные
    assert "pending_tg_owner" not in pending.site_config["notify"]
    assert links.owner_route(a) == ("", "")
    assert handler.handle(_msg("/daten_loeschen", update_id=2)) == "nothing"


def test_erase_guards(bot):
    links.bind(USER, TenantFactory(schema_name="p7", slug="p7"))
    handler.handle(_msg("/daten_loeschen"))
    yes = _yes(bot)
    assert handler.handle(_cb("pd:yes:wrong")) == "erase_expired"
    assert handler.handle(_cb(yes, chat=5)) == "skip"
    assert handler.handle(_cb("pd:no")) == "erase_cancelled"
    assert handler.handle(_cb(yes)) == "erase_expired"  # pd:no погасил кнопку
    assert OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()


def test_erase_refused_while_provisioning(bot):
    links.bind(USER, TenantFactory(schema_name="p8", slug="p8"))
    handler.handle(_msg("/daten_loeschen"))
    yes = _yes(bot)
    bot["cache"].set(signup._pending_key(USER), 1, 60)
    assert handler.handle(_cb(yes)) == "erase_busy"
    assert OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()


def test_erase_refused_while_signup_lock_held(bot, monkeypatch):
    """Регистрация держит замок (submit под ним ставит «создаётся») — удаление ждёт."""
    links.bind(USER, TenantFactory(schema_name="p9", slug="p9"))
    handler.handle(_msg("/daten_loeschen"))
    yes = _yes(bot)
    bot["cache"].set(f"tgplat:signup-lock:{USER}", 1, 60)
    monkeypatch.setattr(signup.time, "sleep", lambda s: None)
    assert handler.handle(_cb(yes)) == "erase_busy"
    assert OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()
    assert bot["cache"].get(f"tgplat:signup-lock:{USER}")  # чужой замок не снят


def test_purge_skips_unblocked_and_fresh_marker(monkeypatch):
    """Под блокировкой перепроверяем: разблокированная связь и свежая метка — не трогать."""
    now = timezone.now()
    t = TenantFactory(schema_name="pe", slug="pe")
    link = links.bind(USER + 9, t)
    OwnerTelegramLink.objects.filter(pk=link.pk).update(blocked_at=now - timedelta(days=181))
    t2 = TenantFactory(schema_name="pf", slug="pf")
    t2.site_config = {"notify": {"pending_tg_owner": {"uid": 7, "at": 1}}}
    t2.save()
    real_lock = links._lock

    def racing_lock(pk):
        # Между выборкой и блокировкой пользователь снова пишет боту / регистрация обновила метку.
        OwnerTelegramLink.objects.filter(pk=link.pk).update(blocked_at=None)
        from apps.tenants.models import Tenant

        fresh = Tenant.objects.get(pk=t2.pk)
        fresh.site_config = {"notify": {"pending_tg_owner": {"uid": 7, "at": int(now.timestamp())}}}
        fresh.save()
        return real_lock(pk)

    monkeypatch.setattr(links, "_lock", racing_lock)
    result = links.purge_stale(now)
    assert OwnerTelegramLink.objects.filter(pk=link.pk).exists()
    t.refresh_from_db()
    t2.refresh_from_db()
    assert str(t.site_config["notify"]["owner_chat_id"]) == str(USER + 9)
    assert t2.site_config["notify"]["pending_tg_owner"]["uid"] == 7
    assert result["blocked"] == 0 and result["markers"] == 0


def test_erase_drops_signup_state(bot):
    handler.handle(_msg("/neu"))
    assert signup.load(USER) is not None
    handler.handle(_msg("/daten_loeschen", update_id=2))
    handler.handle(_cb(_yes(bot)))
    assert signup.load(USER) is None


def test_erase_rate_limited(bot, monkeypatch):
    monkeypatch.setattr(privacy, "LIMIT_ERASE", 1)
    links.bind(USER, TenantFactory(schema_name="p9", slug="p9"))
    handler.handle(_msg("/daten_loeschen"))
    assert handler.handle(_msg("/daten_loeschen", update_id=2)) == "limited"


def test_cachescan_failure_does_not_break_erase(bot, monkeypatch):
    from apps.core import cachescan

    monkeypatch.setattr(cachescan, "delete_matching", mock.Mock(side_effect=RuntimeError))
    links.bind(USER, TenantFactory(schema_name="pa", slug="pa"))
    handler.handle(_msg("/daten_loeschen"))
    assert handler.handle(_cb(_yes(bot))) == "erased"
    assert not OwnerTelegramLink.objects.filter(tg_user_id=USER).exists()


def test_cachescan_helper_is_fail_safe(monkeypatch):
    from apps.core import cachescan

    assert cachescan.delete_matching("nothing:*") >= 0
    monkeypatch.setattr(cachescan.cache, "make_key", mock.Mock(side_effect=RuntimeError))
    assert cachescan.delete_matching("x:*") == 0


def test_purge_stale_retention():
    now = timezone.now()
    t = TenantFactory(schema_name="pb", slug="pb")
    keep = links.bind(USER, t)
    old_inactive = OwnerTelegramLink.objects.create(tg_user_id=USER + 2, tenant=t, is_active=False)
    young_inactive = OwnerTelegramLink.objects.create(
        tg_user_id=USER + 3, tenant=t, is_active=False
    )
    OwnerTelegramLink.objects.filter(pk=old_inactive.pk).update(updated_at=now - timedelta(days=31))
    OwnerTelegramLink.objects.filter(pk=young_inactive.pk).update(
        updated_at=now - timedelta(days=10)
    )
    t2 = TenantFactory(schema_name="pc", slug="pc")
    blocked = links.bind(USER + 4, t2)
    OwnerTelegramLink.objects.filter(pk=blocked.pk).update(blocked_at=now - timedelta(days=181))
    t3 = TenantFactory(schema_name="pd", slug="pd")
    t3.site_config = {"notify": {"pending_tg_owner": {"uid": 7, "at": 1}}}
    t3.save()
    result = links.purge_stale(now)
    ids = set(OwnerTelegramLink.objects.values_list("pk", flat=True))
    assert keep.pk in ids and young_inactive.pk in ids
    assert old_inactive.pk not in ids and blocked.pk not in ids
    t2.refresh_from_db()
    t3.refresh_from_db()
    assert "owner_chat_id" not in t2.site_config["notify"]
    assert "pending_tg_owner" not in t3.site_config["notify"]
    assert result["inactive"] == 1 and result["blocked"] == 1 and result["markers"] == 1


def test_purge_beat_registered(settings):
    tasks = {v["task"] for v in settings.CELERY_BEAT_SCHEDULE.values()}
    assert "apps.platform_bot.tasks.purge_stale_links" in tasks


def test_apply_webhook_sets_localized_commands(monkeypatch, settings):
    from apps.platform_bot import config

    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "1:t"
    config.reset_cache()
    calls = []
    monkeypatch.setattr("apps.telegram.services.set_webhook", lambda *a: None)
    monkeypatch.setattr(
        "apps.telegram.services.set_my_commands",
        lambda token, commands, language_code="": calls.append((language_code, commands)),
    )
    config.apply_webhook()
    langs = {lang for lang, _c in calls}
    assert "" in langs and set(settings.CABINET_LANGUAGES) <= langs
    names = {c["command"] for c in calls[0][1]}
    assert {"neu", "geschaeft", "daten_loeschen", "datenschutz"} <= names
    by_lang = {lang: {c["command"]: c["description"] for c in cmds} for lang, cmds in calls}
    assert by_lang["ru"]["neu"] != by_lang["de"]["neu"]  # описание действительно переведено
    monkeypatch.setattr(
        "apps.telegram.services.set_my_commands", mock.Mock(side_effect=RuntimeError)
    )
    config.apply_webhook()  # сбой меню команд не ломает вебхук


def test_platform_privacy_page_mentions_bot(client):
    from django.test import RequestFactory

    from apps.tenants import views

    req = RequestFactory().get("/datenschutz/")
    html = views.platform_legal(req, "datenschutz").content.decode()
    assert "Telegram" in html and "/daten_loeschen" in html and "Art. 6 Abs. 1 lit. b" in html


@pytest.mark.skipif(
    "redis" not in __import__("django.conf").conf.settings.CACHES["default"]["BACKEND"].lower(),
    reason="SCAN — только на Redis",
)
def test_cachescan_deletes_only_matching_keys():
    from django.core.cache import cache

    from apps.core import cachescan

    tag = uuid.uuid4().hex[:8]
    cache.set(f"tgplat:ref:{tag}1:aaa", 1, 60)
    cache.set(f"tgplat:ref:{tag}1:bbb", 1, 60)
    cache.set(f"tgplat:ref:{tag}2:ccc", 1, 60)
    assert cachescan.delete_matching(f"tgplat:ref:{tag}1:*") == 2
    assert cache.get(f"tgplat:ref:{tag}2:ccc") == 1
    cache.delete(f"tgplat:ref:{tag}2:ccc")
