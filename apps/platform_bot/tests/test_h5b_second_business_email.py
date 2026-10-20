"""T-8.10h H-5b: второй бизнес из бота + привязка чата только после подтверждения почты."""

import uuid
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory

from apps.core import owner_login
from apps.core.models import Membership
from apps.platform_bot import handler, links, signup, webhook
from apps.platform_bot.models import OwnerTelegramLink
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

USER = 555000999888
MAIL = "inhaber@example.com"


@pytest.fixture
def bot(monkeypatch, settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:plat"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    store = LocMemCache(f"h5b-{uuid.uuid4()}", {})
    monkeypatch.setattr(signup, "cache", store)
    monkeypatch.setattr(signup, "MIN_SECONDS", 0)
    sent = []

    def _send(token, chat, text, reply_markup=None):
        sent.append({"chat": chat, "text": text, "markup": reply_markup})
        return {}

    monkeypatch.setattr("apps.telegram.services.send_message", _send)
    monkeypatch.setattr("apps.telegram.services.answer_callback_query", lambda *a, **k: None)
    return {"sent": sent}


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


def _cb(data):
    return webhook.slim(
        {
            "update_id": 9,
            "callback_query": {
                "id": "c",
                "from": {"id": USER, "language_code": "de"},
                "message": {"chat": {"id": USER}, "message_id": 1},
                "data": data,
            },
        }
    )


def _pending_tenant(slug="pend-1", uid=USER, schema="public"):
    tenant = TenantFactory(schema_name=schema, slug=slug, name=f"Laden {slug}")
    tenant.email_pending = True
    tenant.provisioning_status = tenant.PROVISIONING_READY
    tenant.site_config = {"notify": {"pending_tg_owner": {"uid": uid, "lang": "de"}}}
    tenant.save()
    user = get_user_model().objects.create_user(
        username=f"o-{slug}", email=MAIL, password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return tenant, user


def _confirm(tenant, method="post"):
    token = owner_login.confirm_token(tenant, MAIL)
    req = getattr(RequestFactory(), method)(f"/start/bestaetigen/{token}/")
    req.tenant = tenant
    req._dont_enforce_csrf_checks = True
    return owner_login.owner_confirm_email(req, token)


# --- второй бизнес ----------------------------------------------------------------------


def test_linked_user_can_start_second_business(bot):
    first = TenantFactory(schema_name="sb1", slug="sb1", name="Erstes")
    links.bind(USER, first)
    assert handler.handle(_msg("/neu")) == "started"
    assert any("Erstes" in m["text"] for m in bot["sent"])


def test_signup_state_beats_promo_pipeline_for_linked_user(bot, monkeypatch):
    first = TenantFactory(schema_name="sb2", slug="sb2")
    links.bind(USER, first)
    handler.handle(_msg("/neu"))
    promo = mock.Mock()
    monkeypatch.setattr("apps.promotions.telegram_promo.handle_owner_message", promo)
    assert handler.handle(_msg("Brot −30 % diese Woche", update_id=2)) == "type"
    promo.assert_not_called()
    assert handler.handle(_msg("/abbrechen", update_id=3)) == "cancelled"
    handler.handle(_msg("Brot −30 % diese Woche", update_id=4))
    promo.assert_called_once()


def test_choose_offers_new_business_button(bot):
    links.bind(USER, TenantFactory(schema_name="sb3", slug="sb3"))
    handler.handle(_msg("/geschaeft"))
    rows = bot["sent"][-1]["markup"]["inline_keyboard"]
    assert rows[-1][0]["callback_data"] == "ps:go"


def test_bot_business_cap(bot, monkeypatch):
    monkeypatch.setattr(signup, "MAX_BOT_BUSINESSES", 1)
    links.bind(USER, TenantFactory(schema_name="sb4", slug="sb4"))
    assert handler.handle(_msg("/neu")) == "has_business"


# --- метка при создании ------------------------------------------------------------------


def test_quick_provisioning_with_telegram_writes_marker(monkeypatch, settings):
    from apps.tenants import services

    monkeypatch.setattr("apps.tenants.tasks.provision_quick.delay", lambda *a, **k: None)
    tenant = services.start_quick_provisioning(
        business_name="Mark",
        slug="mark-h5b",
        business_type="bakery",
        city="Solingen",
        district="",
        email=MAIL,
        promo={},
        telegram={"tg_user_id": USER, "lang": "ru"},
    )
    marker = tenant.site_config["notify"]["pending_tg_owner"]
    assert marker["uid"] == USER and marker["lang"] == "ru"
    web = services.start_quick_provisioning(
        business_name="Web",
        slug="web-h5b",
        business_type="bakery",
        city="Solingen",
        district="",
        email=MAIL,
        promo={},
    )
    assert "notify" not in web.site_config


# --- подтверждение почты ----------------------------------------------------------------


def test_confirm_get_with_marker_changes_nothing(bot):
    tenant, _u = _pending_tenant()
    resp = _confirm(tenant, "get")
    assert b"data-owner-confirm-form" in resp.content
    tenant.refresh_from_db()
    assert tenant.email_pending and not OwnerTelegramLink.objects.exists()


def test_confirm_post_binds_marker_uid_and_messages_once(bot, django_capture_on_commit_callbacks):
    tenant, user = _pending_tenant()
    with mock.patch("apps.platform_bot.tasks.notify_signup_bound.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            resp = _confirm(tenant)
    assert resp.status_code == 200
    tenant.refresh_from_db()
    link = OwnerTelegramLink.objects.get(tenant=tenant)
    assert link.via == OwnerTelegramLink.VIA_SIGNUP and link.tg_user_id == USER
    node = tenant.site_config["notify"]
    assert "pending_tg_owner" not in node and node["owner_user_pk"] == user.pk
    assert not tenant.email_pending
    assert delay.call_args.kwargs["result"] == "bound"
    signup.bound_message(tenant, USER, "bound", "de")
    signup.bound_message(tenant, USER, "bound", "de")
    assert sum("bestätigt" in m["text"] for m in bot["sent"]) == 1


def test_confirm_does_not_override_cabinet_choice(bot):
    tenant, _u = _pending_tenant()
    links.bind(USER + 1, tenant)  # владелец подключил другой чат в кабинете
    tenant.refresh_from_db()
    tenant.site_config["notify"]["pending_tg_owner"] = {"uid": USER}
    tenant.save()
    result, uid, _lang = links.complete_pending(tenant)
    assert (
        result == "taken" and links.is_owner(USER + 1, tenant) and not links.is_owner(USER, tenant)
    )


def test_new_business_becomes_current_after_confirm(bot):
    links.bind(USER, TenantFactory(schema_name="cur1", slug="cur1"))
    tenant, _u = _pending_tenant()
    links.complete_pending(tenant)
    assert links.active_links(USER).first().tenant == tenant


def test_finish_binds_if_confirmed_before_finish(bot):
    tenant, _u = _pending_tenant()
    tenant.email_pending = False
    tenant.save()
    assert signup.finish(tenant.pk, {"tg_user_id": USER, "lang": "de"}, None, True) == "bound"
    assert links.is_owner(USER, tenant)


# --- пока почта не подтверждена ---------------------------------------------------------


def test_pending_chat_cannot_send_promos_and_gets_reminder(bot, monkeypatch):
    tenant, _u = _pending_tenant()
    promo = mock.Mock()
    monkeypatch.setattr("apps.promotions.telegram_promo.handle_owner_message", promo)
    assert handler.handle(_msg("Brot −30 % heute")) == "awaiting_email"
    promo.assert_not_called()
    rows = bot["sent"][-1]["markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == f"ps:m:{tenant.pk}"


def test_login_link_denied_while_pending(bot):
    tenant, _u = _pending_tenant()
    assert handler.handle(_cb(f"ps:l:{tenant.pk}")) == "denied"


def test_resend_only_for_registering_chat(bot, monkeypatch):
    tenant, _u = _pending_tenant()
    other, _o = _pending_tenant(slug="pend-2", uid=USER + 5, schema="pend2")
    mails = []
    monkeypatch.setattr(owner_login, "send_confirmation", lambda t, e: mails.append(e))
    assert handler.handle(_cb(f"ps:m:{other.pk}")) == "denied"
    assert handler.handle(_cb(f"ps:m:{tenant.pk}")) == "sent"
    assert mails == [MAIL]


def test_bot_failure_does_not_break_confirm_page(bot, monkeypatch):
    tenant, _u = _pending_tenant()
    monkeypatch.setattr(links, "complete_pending", mock.Mock(side_effect=RuntimeError("x")))
    assert _confirm(tenant).status_code == 200


def test_second_signup_right_after_first_is_not_blocked(bot, monkeypatch):
    """Стенд: защита двойного ✅ держалась 5 мин и молча блокировала следующий бизнес."""
    calls = []

    def fake(**kw):
        calls.append(kw)
        return TenantFactory(schema_name=f"two{len(calls)}", slug=f"two{len(calls)}")

    monkeypatch.setattr("apps.tenants.services.start_quick_provisioning", fake)
    monkeypatch.setattr(signup, "LIMIT_SIGNUP_UNVERIFIED", 5)
    for round_ in range(2):
        handler.handle(_cb("ps:go"))
        handler.handle(_msg("Brot −30 % diese Woche", update_id=10 + round_))
        handler.handle(_cb("ps:t:bakery"))
        for text in ("Krume", "Musterstadt", "Hauptstraße 5", "42651", "0212 123456", MAIL):
            handler.handle(_msg(text))
        assert handler.handle(_cb("ps:ok")) == "submitted"
        signup.cache.delete(signup._pending_key(USER))  # как finish задачи провижининга
    assert len(calls) == 2


def test_owner_of_confirmed_business_gets_verified_limits(bot, monkeypatch):
    """Стенд: второй бизнес в тот же день упирался в лимит «без подтверждённого номера»."""
    monkeypatch.setattr(
        "apps.tenants.services.start_quick_provisioning",
        lambda **kw: TenantFactory(schema_name="vt1", slug="vt1"),
    )
    monkeypatch.setattr(signup, "LIMIT_SIGNUP_UNVERIFIED", 0)
    links.bind(USER, TenantFactory(schema_name="vt0", slug="vt0"))
    handler.handle(_cb("ps:go"))
    handler.handle(_msg("Brot −30 % diese Woche", update_id=31))
    handler.handle(_cb("ps:t:bakery"))
    for text in ("Krume", "Musterstadt", "Hauptstraße 5", "42651", "0212 123456", MAIL):
        handler.handle(_msg(text))
    assert handler.handle(_cb("ps:ok")) == "submitted"
