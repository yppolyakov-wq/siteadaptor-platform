"""T-8.10h H-5: регистрация нового бизнеса в общем боте (план §8)."""

import logging
import uuid
from unittest import mock

import pytest
from django.core.cache.backends.locmem import LocMemCache

from apps.platform_bot import handler, links, signup, webhook
from apps.platform_bot.models import OwnerTelegramLink
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

USER = 555000111222
MAIL = "inhaber@example.com"
PHONE = "0212 123456"


@pytest.fixture
def bot(monkeypatch, settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:plat"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    store = LocMemCache(f"tgsignup-{uuid.uuid4()}", {})
    monkeypatch.setattr(signup, "cache", store)
    monkeypatch.setattr(signup, "MIN_SECONDS", 0)
    sent = []

    def _send(token, chat, text, reply_markup=None):
        sent.append({"token": token, "chat": chat, "text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr("apps.telegram.services.send_message", _send)
    monkeypatch.setattr("apps.telegram.services.answer_callback_query", lambda *a, **k: None)
    calls = []

    def fake_provision(**kw):
        calls.append(kw)
        return TenantFactory(schema_name=f"s{len(calls)}x", slug=f"neu-{len(calls)}")

    monkeypatch.setattr("apps.tenants.services.start_quick_provisioning", fake_provision)
    return {"sent": sent, "calls": calls, "cache": store}


def _msg(text="", update_id=1, uid=USER, chat=None, kind="private", **extra):
    return webhook.slim(
        {
            "update_id": update_id,
            "message": {
                "chat": {"id": chat or uid, "type": kind},
                "from": {"id": uid, "is_bot": False, "language_code": "de"},
                "text": text,
                **extra,
            },
        }
    )


def _cb(data, uid=USER):
    return webhook.slim(
        {
            "update_id": 99,
            "callback_query": {
                "id": "c",
                "from": {"id": uid, "language_code": "de"},
                "message": {"chat": {"id": uid}, "message_id": 1},
                "data": data,
            },
        }
    )


def _walk_to_summary():
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brötchen 2,50 € statt 3,90 €, diese Woche, 20 Stück"))
    handler.handle(_cb("ps:t:bakery"))
    handler.handle(_msg("Bäckerei Krume"))
    handler.handle(_msg("Musterstadt"))  # неизвестный город — без шага района
    handler.handle(_msg("Hauptstraße 5"))
    handler.handle(_msg("42651"))
    handler.handle(_msg(PHONE))
    return handler.handle(_msg(MAIL))


def test_onboarding_offers_chat_start_and_web_link(bot):
    assert handler.handle(_msg("Hallo")) == "onboarding"
    rows = bot["sent"][-1]["markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "ps:go"
    assert rows[1][0]["url"].endswith("/aktion-starten/")


def test_start_shows_privacy_notice_and_creates_state(bot):
    assert handler.handle(_cb("ps:go")) == "started"
    assert any("/datenschutz/" in m["text"] for m in bot["sent"])
    assert signup.load(USER)["step"] == "promo"


def test_group_never_starts_signup(bot, monkeypatch):
    monkeypatch.setattr("apps.telegram.services.leave_chat", lambda *a: None)
    assert handler.handle(_msg("/neu", chat=-100, kind="group")) == "skip"
    assert signup.load(USER) is None


def test_full_flow_reaches_summary_and_submits_same_provisioning(bot):
    assert _walk_to_summary() == "summary"
    summary = bot["sent"][-1]["text"]
    assert "Bäckerei Krume" in summary and MAIL in summary
    assert handler.handle(_cb("ps:ok")) == "submitted"
    kw = bot["calls"][0]
    assert kw["business_name"] == "Bäckerei Krume" and kw["business_type"] == "bakery"
    assert kw["address"] == "Hauptstraße 5, 42651 Musterstadt" and kw["phone"] == PHONE
    assert kw["email"] == MAIL and "in_city_catalog" not in kw  # KA-D5: всегда в каталоге
    assert kw["promo"]["title"] and kw["promo"]["new_price"] == "2.50"
    assert kw["telegram"] == {"tg_user_id": USER, "lang": "de"}
    assert signup.load(USER) is None


def test_invalid_postcode_and_phone_are_refused_with_form_text(bot):
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brötchen 2,50 € statt 3,90 €, diese Woche"))
    handler.handle(_cb("ps:t:bakery"))
    handler.handle(_msg("Krume"))
    handler.handle(_msg("Musterstadt"))
    handler.handle(_msg("Hauptstraße 5"))
    assert handler.handle(_msg("12")) == "postcode"
    assert "Postleitzahl" in bot["sent"][-2]["text"]
    handler.handle(_msg("42651"))
    assert handler.handle(_msg("abc")) == "phone"


def test_type_callback_accepts_only_quick_types(bot):
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brot −30 % diese Woche"))
    handler.handle(_cb("ps:t:events"))
    assert signup.load(USER)["step"] == "type"
    handler.handle(_cb("ps:t:bakery"))
    assert signup.load(USER)["step"] == "name"


def test_district_step_only_for_known_city(bot):
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brot −30 % diese Woche"))
    handler.handle(_cb("ps:t:bakery"))
    handler.handle(_msg("Krume"))
    handler.handle(_msg("Solingen"))
    assert signup.load(USER)["step"] == "district"
    rows = bot["sent"][-1]["markup"]["inline_keyboard"]
    assert all(len(r[0]["callback_data"].encode()) <= 64 for r in rows)
    handler.handle(_cb("ps:d:-"))
    assert signup.load(USER)["step"] == "street"


def test_contact_share_only_own_number(bot):
    _walk_to_summary()
    handler.handle(_cb("ps:e:phone"))
    foreign = _msg("", contact={"phone_number": "+49111", "user_id": 1})
    assert handler.handle(foreign) == "phone"
    own = _msg("", contact={"phone_number": "+49 212 555666", "user_id": USER})
    assert handler.handle(own) == "summary"
    assert signup.load(USER)["data"]["phone"] == "+49 212 555666"


def test_state_is_encrypted(bot):
    _walk_to_summary()
    raw = bot["cache"].get(signup._key(USER))
    assert MAIL not in raw and PHONE not in raw


def test_cancel_and_resume(bot):
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brot −30 % diese Woche"))
    assert handler.handle(_msg("/start")) == "resumed"
    assert handler.handle(_msg("/abbrechen")) == "cancelled"
    assert signup.load(USER) is None


def test_submit_revalidates_and_maps_error_to_step(bot):
    _walk_to_summary()
    state = signup.load(USER)
    state["data"]["email"] = "kaputt"
    signup.save(USER, state)
    assert handler.handle(_cb("ps:ok")) == "invalid_email"
    assert not bot["calls"] and signup.load(USER)["step"] == "email"


def test_double_ok_creates_one_tenant(bot, monkeypatch):
    _walk_to_summary()
    state = signup.load(USER)
    handler.handle(_cb("ps:ok"))
    signup.save(USER, state)  # повторное нажатие на то же сводное сообщение
    handler.handle(_cb("ps:ok"))
    assert len(bot["calls"]) == 1


def test_signup_limit_per_user(bot, monkeypatch):
    monkeypatch.setattr(signup, "LIMIT_SIGNUP", 0)
    monkeypatch.setattr(signup, "LIMIT_SIGNUP_UNVERIFIED", 0)
    _walk_to_summary()
    assert handler.handle(_cb("ps:ok")) == "limited"
    assert not bot["calls"]


def test_photos_downloaded_with_platform_token(bot, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "apps.promotions.telegram_promo.photos_from_telegram",
        lambda token, ids: seen.update(token=token, ids=list(ids)) or ([], True),
    )
    handler.handle(_msg("/neu"))
    handler.handle(_msg("", photo=[{"file_id": "f1"}]))
    handler.handle(_msg("Brot −30 % diese Woche", photo=[{"file_id": "f2"}]))
    handler.handle(_cb("ps:t:bakery"))
    for text in ("Krume", "Musterstadt", "Hauptstraße 5", "42651", PHONE, MAIL):
        handler.handle(_msg(text))
    handler.handle(_cb("ps:ok"))
    assert seen == {"token": "123:plat", "ids": ["f1", "f2"]}


def test_no_personal_data_in_logs(bot, caplog):
    with caplog.at_level(logging.DEBUG):
        _walk_to_summary()
        handler.handle(_cb("ps:ok"))
    text = " ".join(r.getMessage() for r in caplog.records)
    assert MAIL not in text and PHONE not in text and "Brötchen" not in text


# --- после провижининга --------------------------------------------------------------


def test_finish_awaits_email_and_does_not_bind(bot):
    """H-5b (решение владельца): чат станет владельцем только после подтверждения почты."""
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    tenant = TenantFactory(schema_name="public", slug="fin-1", name="Krume")
    tenant.provisioning_status = tenant.PROVISIONING_READY
    tenant.email_pending = True
    tenant.site_config = {"notify": {"pending_tg_owner": {"uid": USER, "lang": "de", "at": 10**10}}}
    tenant.save()
    user = get_user_model().objects.create_user(username=MAIL, email=MAIL, password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    telegram = {"tg_user_id": USER, "lang": "de"}
    pk = uuid.uuid4()
    assert signup.finish(tenant.pk, telegram, pk, True) == "awaiting_email"
    assert signup.finish(tenant.pk, telegram, pk, True) == "already"
    assert not OwnerTelegramLink.objects.filter(tenant=tenant).exists()
    last = bot["sent"][-1]
    assert "bestätigen" in last["text"] and "i***@example.com" in last["text"]
    data = [b.get("callback_data", "") for row in last["markup"]["inline_keyboard"] for b in row]
    assert f"ps:m:{tenant.pk}" in data and not any(d.startswith("ps:l:") for d in data)


def test_finish_failure_sends_message_and_no_link(bot):
    tenant = TenantFactory(schema_name="fail1", slug="fail1")
    assert signup.finish(tenant.pk, {"tg_user_id": USER}, None, False) == "failed"
    assert not OwnerTelegramLink.objects.exists()


def test_provision_quick_old_signature_does_not_call_bot(monkeypatch):
    from apps.tenants import tasks

    monkeypatch.setattr(tasks, "provision_quick_logic", lambda *a: None)
    with mock.patch("apps.platform_bot.signup.finish") as finish:
        tasks.provision_quick("1", MAIL, {})
    finish.assert_not_called()


def test_login_link_only_for_bound_owner(bot, monkeypatch):
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    tenant = TenantFactory(schema_name="public", slug="ll-1")
    user = get_user_model().objects.create_user(username="ll", email=MAIL, password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    mails = []
    monkeypatch.setattr("apps.core.owner_login.send_login_link", lambda t, e, **k: mails.append(e))
    assert handler.handle(_cb(f"ps:l:{tenant.pk}")) == "denied"
    links.bind(USER, tenant, user_pk=user.pk)
    assert handler.handle(_cb(f"ps:l:{tenant.pk}")) == "sent"
    assert mails == [MAIL]


def test_promo_payload_carries_until_time():
    from apps.tenants import quickstart

    form = quickstart.QuickStartForm(
        data={
            "title": "Brot",
            "term": "today",
            "until_time": "23:59",
            "until_time_for": "today",
            "customer_response": "reserve",
            "business_name": "X",
            "business_type": "bakery",
            "city": "Solingen",
            "street": "A 1",
            "postcode": "42651",
            "phone": PHONE,
            "email": MAIL,
        }
    )
    assert form.is_valid(), form.errors
    payload = form.promo_payload()
    assert payload["until_time"] == "23:59" and payload["until_time_for"] == "today"


def test_edit_menu_uses_field_labels(bot):
    _walk_to_summary()
    handler.handle(_cb("ps:e"))
    labels = [r[0]["text"] for r in bot["sent"][-1]["markup"]["inline_keyboard"]]
    assert any("E-Mail" in t for t in labels) and not any(t.endswith(" email") for t in labels)


def test_fast_provisioning_does_not_leave_pending_marker(bot, monkeypatch):
    """Воркер успел закончить раньше возврата из submit — метка «создаётся» не висит."""

    def instant(**kw):
        tenant = TenantFactory(schema_name="fast1", slug="fast1")
        signup.cache.delete(signup._pending_key(USER))  # как finish в задаче
        return tenant

    monkeypatch.setattr("apps.tenants.services.start_quick_provisioning", instant)
    _walk_to_summary()
    handler.handle(_cb("ps:ok"))
    assert not signup.cache.get(signup._pending_key(USER))


# --- правки ревью (2026-10-20) --------------------------------------------------------


def test_unverified_phone_gets_stricter_daily_limit(bot):
    _walk_to_summary()  # телефон введён текстом — не подтверждён
    assert handler.handle(_cb("ps:ok")) == "submitted"
    signup.cache.delete(signup._pending_key(USER))
    signup.cache.delete(f"tgplat:signup-submit:{USER}")  # защита двойного ✅ (5 мин)
    links.OwnerTelegramLink.objects.all().delete()
    _walk_to_summary()
    assert handler.handle(_cb("ps:ok")) == "limited"  # второй за сутки без номера


def test_shared_own_number_marks_verified(bot):
    _walk_to_summary()
    handler.handle(_cb("ps:e:phone"))
    handler.handle(_msg("", contact={"phone_number": "+49 212 1", "user_id": USER}))
    assert signup.load(USER)["data"]["phone_verified"] is True


def test_invalid_edit_keeps_previous_value(bot):
    _walk_to_summary()
    handler.handle(_cb("ps:e:postcode"))
    assert handler.handle(_msg("12")) == "postcode"
    assert signup.load(USER)["data"]["postcode"] == "42651"


def test_album_photos_after_promo_step_are_added_silently(bot):
    handler.handle(_msg("/neu"))
    handler.handle(_msg("Brot −30 % diese Woche", photo=[{"file_id": "a1"}], media_group_id="g"))
    before = len(bot["sent"])
    assert handler.handle(_msg("", photo=[{"file_id": "a2"}], media_group_id="g")) == "photo_added"
    assert len(bot["sent"]) == before
    assert signup.load(USER)["data"]["photo_ids"] == ["a1", "a2"]


def test_unknown_command_is_not_a_promo(bot):
    handler.handle(_msg("/neu"))
    assert handler.handle(_msg("/unbekannt")) == "promo"
    assert not signup.load(USER)["data"].get("title")
    # H-7b: «/hilfe» — команда меню, не шаг регистрации; диалог регистрации цел.
    assert handler.handle(_msg("/hilfe")) == "help"
    assert signup.load(USER)["step"] == "promo"


def test_city_edit_goes_through_district(bot):
    _walk_to_summary()
    handler.handle(_cb("ps:e:city"))
    handler.handle(_msg("Solingen"))
    assert signup.load(USER)["step"] == "district"
    handler.handle(_cb("ps:d:-"))
    assert signup.load(USER)["step"] == "summary"


def test_provisioning_crash_keeps_input_and_no_pending(bot, monkeypatch):
    def boom(**kw):
        raise RuntimeError("db")

    monkeypatch.setattr("apps.tenants.services.start_quick_provisioning", boom)
    _walk_to_summary()
    assert handler.handle(_cb("ps:ok")) == "failed"
    assert signup.load(USER)["step"] == "summary"
    assert not signup.cache.get(signup._pending_key(USER))


def test_login_link_limited_per_recipient(bot, monkeypatch):
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    monkeypatch.setattr(signup, "LIMIT_LOGIN_MAIL", 1)
    tenant = TenantFactory(schema_name="public", slug="ll-2")
    user = get_user_model().objects.create_user(username="ll2", email=MAIL, password="pw12345678")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    monkeypatch.setattr("apps.core.owner_login.send_login_link", lambda t, e, **k: None)
    links.bind(USER, tenant, user_pk=user.pk)
    assert handler.handle(_cb(f"ps:l:{tenant.pk}")) == "sent"
    assert handler.handle(_cb(f"ps:l:{tenant.pk}")) == "limited"


def test_promo_failure_with_ready_schema_still_binds(monkeypatch):
    from apps.tenants import tasks

    tenant = TenantFactory(schema_name="rdy1", slug="rdy1")
    tenant.provisioning_status = tenant.PROVISIONING_READY
    tenant.save()

    def boom(*a):
        raise RuntimeError("promo")

    monkeypatch.setattr(tasks, "provision_quick_logic", boom)
    with mock.patch("apps.platform_bot.signup.finish") as finish:
        with pytest.raises(RuntimeError):
            tasks.provision_quick(str(tenant.pk), MAIL, {}, telegram={"tg_user_id": USER})
    assert finish.call_args.args[3] is True and finish.call_args.args[2] is None
