"""KA-12 E6.7c-3: инвайт v2 + team_view через единственный писатель perm_grants.

Замки плана B1/B2/B4: приглашающий перепроверяется при принятии (удалён/понижен →
инвайт мёртв, членства нет); лишние права срезаются; легаси-инвайт = пресет роли;
admin приглашает только staff и только из своей области; e-mail коллег — маской для
того, кто не правит команду; каждое действие team_view само проверяет право.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from apps.audit.models import AuditEvent
from apps.core import perm_grants as G
from apps.core import permissions as P
from apps.core import team
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
OWNER, ADMIN, STAFF = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF


@pytest.fixture(autouse=True)
def _env(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    for key in cache.keys("*rl:team-*") if hasattr(cache, "keys") else []:
        cache.delete(key)


def _member(role, perms=None):
    o = uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"ti-{o}@t.de", email=f"ti-{o}@t.de", password="pw12345678"
    )
    return Membership.objects.create(user=user, role=role, permissions=perms or {})


def _admin_with_team():
    return _member(ADMIN, {"add": ["team.view", "team.edit", "team.delete"]})


def _req(user, method="get", data=None, path="/dashboard/settings/team/"):
    req = getattr(RequestFactory(), method)(
        path, data or {}, REMOTE_ADDR=f"10.9.{uuid4().int % 250}.1"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = TenantFactory(business_type="restaurant")
    return req


def _join(token, email):
    return team.team_join(
        _req(
            get_user_model()(),
            "post",
            {"password1": "geheim123", "password2": "geheim123"},
            path=f"/team/beitreten/{token}/",
        ),
        token,
    ), get_user_model().objects.filter(username=email).first()


def _eff(user):
    m = Membership.objects.get(user=user)
    return P.effective_from(m.role, m.permissions)


# --- выпуск ------------------------------------------------------------------
def test_admin_cannot_invite_admin_or_beyond_scope():
    admin = _admin_with_team()
    assert team.issue_invite("x@t.de", ADMIN, inviter=admin.user) is None
    assert team.issue_invite("x@t.de", STAFF, inviter=admin.user, perms=["kunden.export"]) is None
    assert team.issue_invite("x@t.de", STAFF, inviter=admin.user) is not None


def test_admin_without_team_edit_cannot_invite():
    plain = _member(ADMIN)
    assert team.issue_invite("x@t.de", STAFF, inviter=plain.user) is None


# --- принятие ----------------------------------------------------------------
def test_owner_invite_carries_extra_permission():
    owner = _member(OWNER)
    perms = sorted(P.for_role(STAFF) | {"kunden.export"})
    token = team.issue_invite("p1@t.de", STAFF, inviter=owner.user, perms=perms)
    resp, user = _join(token, "p1@t.de")
    assert resp.status_code == 302
    assert "kunden.export" in _eff(user)
    assert AuditEvent.objects.filter(action="team.join").exists()


def test_removed_inviter_kills_invite_without_membership():
    admin = _admin_with_team()
    owner = _member(OWNER)
    token = team.issue_invite("p2@t.de", STAFF, inviter=admin.user)
    G.revoke_member(owner.user, admin.pk)
    resp, user = _join(token, "p2@t.de")
    assert resp.status_code == 404
    assert user is None  # откат: «пустого» пользователя тоже нет


def test_demoted_inviter_scope_is_stripped_at_join():
    owner = _member(OWNER)
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"]})
    perms = sorted((P.for_role(STAFF) - P.SENSITIVE) | {"preise.edit"})
    token = team.issue_invite("p3@t.de", STAFF, inviter=admin.user, perms=perms)
    G.set_member_permissions(
        owner.user,
        admin.pk,
        (P.for_role(ADMIN) | {"team.view", "team.edit"}) - {"preise.edit"},
    )
    resp, user = _join(token, "p3@t.de")
    assert resp.status_code == 302
    assert "preise.edit" not in _eff(user)
    event = AuditEvent.objects.filter(action="team.join").latest("pk")
    assert "preise.edit" in event.changes["stripped"]


def test_legacy_invite_gets_plain_preset():
    token = team.issue_invite("p4@t.de", ADMIN)
    resp, user = _join(token, "p4@t.de")
    assert resp.status_code == 302
    assert Membership.objects.get(user=user).permissions == {}
    assert AuditEvent.objects.filter(action="team.join").latest("pk").changes["legacy"] is True


# --- team_view ---------------------------------------------------------------
def test_actions_require_team_edit_inside_view():
    staff = _member(STAFF)
    other = _member(STAFF)
    team.team_view(_req(staff.user, "post", {"action": "revoke", "membership_id": str(other.pk)}))
    assert Membership.objects.filter(pk=other.pk).exists()


def test_admin_revokes_staff_but_not_admin():
    admin = _admin_with_team()
    staff, peer = _member(STAFF), _member(ADMIN)
    team.team_view(_req(admin.user, "post", {"action": "revoke", "membership_id": str(peer.pk)}))
    assert Membership.objects.filter(pk=peer.pk).exists()
    team.team_view(_req(admin.user, "post", {"action": "revoke", "membership_id": str(staff.pk)}))
    assert not Membership.objects.filter(pk=staff.pk).exists()


def test_perms_action_needs_sentinel_and_uses_writer():
    owner = _member(OWNER)
    staff = _member(STAFF)
    base = {"action": "perms", "membership_id": str(staff.pk), "perm": ["verkaeufe.view"]}
    team.team_view(_req(owner.user, "post", base))  # без сентинела — ничего
    assert _eff(staff.user) == P.for_role(STAFF)
    team.team_view(_req(owner.user, "post", {**base, "perms_present": "1"}))
    assert _eff(staff.user) == P._closure({"verkaeufe.view"})


def test_emails_masked_for_viewer_without_team_edit():
    owner = _member(OWNER)
    viewer = _member(STAFF, {"add": ["team.view"]})
    body = team.team_view(_req(viewer.user)).content.decode()
    assert owner.user.email not in body and "***@t.de" in body
    body = team.team_view(_req(owner.user)).content.decode()
    assert viewer.user.email in body


# --- ревью безопасности c-3 --------------------------------------------------
def test_existing_account_needs_its_own_login_no_password_takeover():
    owner = _member(OWNER)
    victim = get_user_model().objects.create_user(username="v1@t.de", email="v1@t.de")
    victim.set_unusable_password()
    victim.save()
    token = team.issue_invite("V1@t.de", STAFF, inviter=owner.user)
    resp, _user = _join(token, "v1@t.de")
    assert b"bereits ein Konto" in resp.content
    victim.refresh_from_db()
    assert not victim.has_usable_password()
    assert not Membership.objects.filter(user=victim).exists()
    # тот же аккаунт, вошедший сам, — присоединяется без смены пароля
    req = _req(victim, "post", {}, path=f"/team/beitreten/{token}/")
    resp = team.team_join(req, token)
    assert resp.status_code == 302
    assert Membership.objects.filter(user=victim, role=STAFF).exists()


def test_default_preset_is_cut_to_inviter_scope():
    owner = _member(OWNER)
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"]})
    token = team.issue_invite("p5@t.de", STAFF, inviter=admin.user)
    G.set_member_permissions(
        owner.user,
        admin.pk,
        (P.for_role(ADMIN) | {"team.view", "team.edit"}) - {"lager.edit", "lager.export"},
    )
    _resp, user = _join(token, "p5@t.de")
    eff = _eff(user)
    assert "lager.edit" not in eff  # приглашающий урезан после выпуска
    assert not (eff & P.SENSITIVE)  # admin чувствительное не вкладывает


def test_unknown_payload_version_is_rejected():
    owner = _member(OWNER)
    token = team.issue_invite("p6@t.de", STAFF, inviter=owner.user)
    payload = cache.get(team._token_key(token))
    cache.set(team._token_key(token), {**payload, "v": 3}, 60)
    resp, user = _join(token, "p6@t.de")
    assert resp.status_code == 404 and user is None
    assert AuditEvent.objects.filter(action="team.join_denied").exists()
