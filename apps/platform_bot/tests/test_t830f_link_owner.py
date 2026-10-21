"""T-8.30f-2: владелец Mini App — в самой связи (OwnerTelegramLink.user_pk), а не в зеркале."""

import importlib

import pytest
from django.apps import apps as global_apps

from apps.core import tg_login
from apps.core.models import Membership
from apps.platform_bot import links, rights
from apps.platform_bot.models import OwnerTelegramLink
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    UID,
    _auth,
    _owner,
    _tenant,
    on,
)

pytestmark = pytest.mark.django_db


def _link(t):
    return OwnerTelegramLink.objects.get(tenant=t, is_active=True)


def test_bind_writes_and_overwrites_user_pk():
    t = _tenant()
    a, b = _owner(), _owner()
    links.bind(UID, t, user_pk=a.pk)
    assert _link(t).user_pk == a.pk
    links.bind(UID, t, user_pk=b.pk)
    assert _link(t).user_pk == b.pk
    links.bind(UID, t)
    assert _link(t).user_pk is None


def test_stale_mirror_does_not_change_who_logs_in():
    """Устаревший Save кабинета перезаписал зеркало — вход идёт за закреплённым в связи."""
    t = _tenant()
    a, b = _owner(), _owner()
    links.bind(UID, t, user_pk=a.pk)
    t.refresh_from_db()
    t.site_config = {"notify": {"owner_user_pk": b.pk}}
    t.save()
    body = _auth()[1]
    token = body["next"].rstrip("/").rsplit("/", 1)[-1]
    assert tg_login.peek(t.schema_name, token)["user_pk"] == a.pk


def test_cabinet_link_without_user_refused_signup_link_single_owner_ok():
    t = _tenant()
    owner = _owner()
    links.bind(UID, t)  # кабинет, без пользователя
    assert _auth()[1]["error"] == "no_owner"
    links.bind(UID, t, via=OwnerTelegramLink.VIA_SIGNUP)
    body = _auth()[1]
    token = body["next"].rstrip("/").rsplit("/", 1)[-1]
    assert tg_login.peek(t.schema_name, token)["user_pk"] == owner.pk


def test_still_owner_uses_link_user():
    t = _tenant()
    a = _owner()
    links.bind(UID, t, user_pk=a.pk)
    t.refresh_from_db()
    t.site_config = {}
    assert links.still_owner(t) is True
    Membership.objects.filter(user=a).update(role=Membership.ROLE_STAFF)
    assert links.still_owner(t) is False


def test_claim_for_tenant_bot_keeps_link_user():
    t = _tenant()
    a = _owner()
    links.bind(UID, t, user_pk=a.pk)
    links.claim_for_tenant_bot(t, UID, rotate_token="tok")
    assert OwnerTelegramLink.objects.get(tenant=t, tg_user_id=UID).user_pk == a.pk
    t.refresh_from_db()
    assert links.still_owner(t) is True


def test_session_ends_when_link_rebound_to_other_user():
    t = _tenant()
    a, b = _owner(), _owner()
    links.bind(UID, t, user_pk=a.pk)
    assert tg_login.telegram_allowed(UID, t, a.pk)
    links.bind(UID, t, user_pk=b.pk)
    assert not tg_login.telegram_allowed(UID, t, a.pk)
    assert tg_login.telegram_allowed(UID, t, b.pk)
    links.bind(UID, t)  # легаси: никого — не ограничивает
    assert tg_login.telegram_allowed(UID, t, a.pk)


def test_tg_start_refuses_token_issued_before_rebind(settings):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.http import Http404
    from django.test import RequestFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    t = _tenant()
    a, b = _owner(), _owner()
    links.bind(UID, t, user_pk=a.pk)
    token = tg_login.issue(t.schema_name, a.pk, UID)
    links.bind(UID, t, user_pk=b.pk)
    req = RequestFactory().post(f"/tg/start/{token}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    from django.contrib.auth.models import AnonymousUser

    req.user = AnonymousUser()
    with pytest.raises(Http404):
        tg_login.tg_start(req, token)


def test_export_shows_cabinet_user_and_erase_removes_rows():
    t = _tenant()
    a = _owner()
    links.bind(UID, t, user_pk=a.pk)
    data = rights.export_data(UID)
    assert data["businesses"][0]["cabinet_user_id"] == a.pk
    links.erase_user(UID)
    assert not OwnerTelegramLink.objects.filter(tg_user_id=UID).exists()


def test_backfill_only_matching_mirror():
    mig = importlib.import_module("apps.platform_bot.migrations.0004_backfill_link_user_pk")
    ok, foreign_chat, own_bot, junk = (_tenant(n) for n in ("ok", "fc", "ob", "junk"))
    cases = {
        ok: ({"owner_bot": "platform", "owner_chat_id": "101", "owner_user_pk": 7}, 101),
        foreign_chat: ({"owner_bot": "platform", "owner_chat_id": "999", "owner_user_pk": 7}, 102),
        own_bot: ({"owner_bot": "tenant", "owner_chat_id": "103", "owner_user_pk": 7}, 103),
        junk: ({"owner_bot": "platform", "owner_chat_id": "104", "owner_user_pk": "x"}, 104),
    }
    for tenant, (node, uid) in cases.items():
        OwnerTelegramLink.objects.create(tg_user_id=uid, tenant=tenant)
        tenant.site_config = {"notify": node}
        tenant.save()
    mig.forward(global_apps, None)
    got = {t: OwnerTelegramLink.objects.get(tenant=t).user_pk for t in cases}
    assert got == {ok: 7, foreign_chat: None, own_bot: None, junk: None}
