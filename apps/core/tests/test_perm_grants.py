"""KA-12 E6.7c-2: сервис выдачи прав — запрет эскалации, роли, отзыв, журнал, письмо."""

from unittest import mock
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from apps.audit.models import AuditEvent
from apps.core import perm_grants as G
from apps.core import permissions as P
from apps.core.models import Membership

pytestmark = pytest.mark.django_db

OWNER, ADMIN, STAFF = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF


def _member(role, perms=None):
    user = get_user_model().objects.create_user(
        username=f"pg-{uuid4().hex[:8]}", email=f"{uuid4().hex[:6]}@t.de"
    )
    return Membership.objects.create(user=user, role=role, permissions=perms or {})


def _eff(m):
    m.refresh_from_db()
    return P.effective_from(m.role, m.permissions)


@pytest.fixture
def no_mail():
    with mock.patch.object(G, "_alert_owner") as alert:
        yield alert


def _admin_with_team():
    return _member(ADMIN, {"add": ["team.view", "team.edit", "team.delete"]})


def test_owner_grants_sensitive_key_to_staff(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    new = G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) | {"kunden.export"})
    assert "kunden.export" in new
    assert "kunden.export" in _eff(staff)
    no_mail.assert_not_called()  # выдал владелец — письма нет


def test_owner_grants_team_edit_to_admin(no_mail):
    owner, admin = _member(OWNER), _member(ADMIN)
    G.set_member_permissions(owner.user, admin.pk, P.for_role(ADMIN) | {"team.view", "team.edit"})
    assert "team.edit" in _eff(admin)


def test_admin_without_team_edit_is_denied(no_mail):
    admin, staff = _member(ADMIN), _member(STAFF)
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF))
    assert AuditEvent.objects.filter(action="team.perms_denied").exists()


@pytest.mark.parametrize("target_role", [ADMIN, OWNER])
def test_admin_cannot_edit_admin_or_owner(no_mail, target_role):
    admin, other = _admin_with_team(), _member(target_role)
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, other.pk, set())


def test_nobody_edits_own_rights(no_mail):
    for member in (_member(OWNER), _admin_with_team()):
        with pytest.raises(G.PermsDenied) as exc:
            G.set_member_permissions(member.user, member.pk, set())
        assert exc.value.reason == "self"


def test_admin_cannot_grant_a_key_he_lacks(no_mail):
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["preise.edit"]})
    staff = _member(STAFF)
    before = staff.permissions
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF) | {"preise.edit"})
    staff.refresh_from_db()
    assert staff.permissions == before


def test_admin_cannot_grant_sensitive_even_if_he_has_it(no_mail):
    admin, staff = _admin_with_team(), _member(STAFF)
    with pytest.raises(G.PermsDenied):  # geld.erstatten есть у admin, но выдаёт только владелец
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF) | {"geld.erstatten"})


def test_admin_cannot_restore_sensitive_preset_key_revoked_by_owner(no_mail):
    owner, admin, staff = _member(OWNER), _admin_with_team(), _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) - {"geld.rabatt"})
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF))
    assert "geld.rabatt" not in _eff(staff)


def test_admin_may_revoke_within_his_scope(no_mail):
    admin, staff = _admin_with_team(), _member(STAFF)
    new = G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF) - {"geld.rabatt"})
    assert "geld.rabatt" not in new


def test_keys_outside_admin_scope_survive_his_save(no_mail):
    owner = _member(OWNER)
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["finanzen.journal"]})
    staff = _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF))  # без изменений
    # у staff есть finanzen.journal (пресет); admin его не держит → не может ни снять, ни выдать
    G.set_member_permissions(admin.user, staff.pk, (P.for_role(STAFF) - {"finanzen.journal"}))
    assert "finanzen.journal" in _eff(staff)


def test_edit_pulls_view(no_mail):
    owner, staff = _member(OWNER), _member(STAFF, {"remove": ["preise.view"]})
    new = G.set_member_permissions(
        owner.user, staff.pk, (P.for_role(STAFF) - {"preise.view"}) | {"preise.edit"}
    )
    assert {"preise.view", "preise.edit"} <= new


def test_staff_can_never_hold_team_write(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    new = G.set_member_permissions(
        owner.user, staff.pk, P.for_role(STAFF) | {"team.view", "team.edit"}
    )
    assert "team.view" in new and "team.edit" not in new


def test_demoted_actor_is_denied(no_mail):
    admin, staff = _admin_with_team(), _member(STAFF)
    Membership.objects.filter(pk=admin.pk).update(role=STAFF)
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF))


def test_target_promoted_meanwhile_is_denied(no_mail):
    admin, staff = _admin_with_team(), _member(STAFF)
    Membership.objects.filter(pk=staff.pk).update(role=ADMIN)
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, set())


@pytest.mark.parametrize("bad", ["", "x", "1; drop", "00000000-0000-4000-8000-000000000000"])
def test_garbage_or_unknown_member_is_one_answer(no_mail, bad):
    owner = _member(OWNER)
    with pytest.raises(G.PermsDenied) as exc:
        G.set_member_permissions(owner.user, bad, set())
    assert exc.value.reason == "not_found"


def test_save_writes_only_permissions_and_audit(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) | {"kunden.export"})
    staff.refresh_from_db()
    assert staff.role == STAFF
    event = AuditEvent.objects.filter(action="team.perms").latest("created_at")
    assert event.changes["added"] == ["kunden.export"]
    assert "@" not in str(event.changes)  # без e-mail


def test_unchanged_save_writes_nothing(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF))
    assert not AuditEvent.objects.filter(action="team.perms").exists()


def test_audit_failure_rolls_back(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    with mock.patch("apps.audit.models.AuditEvent.objects.create", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) | {"kunden.export"})
    staff.refresh_from_db()
    assert staff.permissions == {}


def test_admin_sensitive_grant_alerts_owner(django_capture_on_commit_callbacks):
    owner = _member(OWNER)
    admin = _member(ADMIN, {"add": ["team.view", "team.edit", "kunden.edit"]})
    staff = _member(STAFF, {"remove": ["kunden.edit"]})
    with mock.patch.object(G, "_alert_owner") as alert:
        with django_capture_on_commit_callbacks(execute=True):
            G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF))
    alert.assert_called_once()
    assert alert.call_args.args[2] == {"kunden.edit"}
    assert owner  # владелец существует


def test_alert_has_no_customer_or_member_email(monkeypatch):
    owner, admin, staff = _member(OWNER), _admin_with_team(), _member(STAFF)
    sent = []
    monkeypatch.setattr("apps.notifications.services.notify", lambda **kw: sent.append(kw))
    G._alert_owner(admin.user, staff, {"kunden.edit"}, P.for_role(STAFF))
    assert sent and staff.user.email not in sent[0]["body"]
    assert sent[0]["recipient"] == owner.user.email or sent[0]["recipient"]


def test_corrupt_stored_delta_is_repaired_by_a_save(no_mail):
    owner, staff = _member(OWNER), _member(STAFF, {"add": "not-a-list"})
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF))
    staff.refresh_from_db()
    assert staff.permissions == {}  # чистая дельта, а не мусор


def test_denial_audit_failure_keeps_the_denial(no_mail, monkeypatch):
    admin, staff = _member(ADMIN), _member(STAFF)

    def boom(**kw):
        raise RuntimeError("audit down")

    monkeypatch.setattr("apps.audit.services.audit_event", boom)
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(admin.user, staff.pk, P.for_role(STAFF))


def test_admin_revoke_cannot_drop_out_of_scope_key_via_requires(no_mail):
    owner, admin = _member(OWNER), _admin_with_team()
    staff = _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) | {"kunden.export"})
    assert "kunden.export" in _eff(staff)
    with pytest.raises(G.PermsDenied):  # kunden.view снять — уронило бы kunden.export
        G.set_member_permissions(
            admin.user, staff.pk, P.for_role(STAFF) - {"kunden.view", "kunden.edit"}
        )
    assert "kunden.export" in _eff(staff)


def test_stale_form_is_denied(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    token = G.state_token(_eff(staff))
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) | {"kunden.export"})
    with pytest.raises(G.PermsDenied):
        G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF), expected=token)


def test_unknown_template_is_not_stored(no_mail):
    owner, staff = _member(OWNER), _member(STAFF)
    G.set_member_permissions(owner.user, staff.pk, P.for_role(STAFF) - {"lager.edit"}, template="x")
    staff.refresh_from_db()
    assert "template" not in staff.permissions


def test_demoted_owner_gets_plain_preset(no_mail):
    owner, other = _member(OWNER), _member(OWNER)
    G.set_member_role(owner.user, other.pk, ADMIN)
    other.refresh_from_db()
    assert other.permissions == {}
    assert _eff(other) == P.for_role(ADMIN)


def test_role_change_only_by_owner_and_last_owner_protected(no_mail):
    owner, admin, staff = _member(OWNER), _admin_with_team(), _member(STAFF)
    with pytest.raises(G.PermsDenied):
        G.set_member_role(admin.user, staff.pk, ADMIN)
    other_owner = _member(OWNER)
    G.set_member_role(owner.user, other_owner.pk, STAFF)  # владельцев было двое
    with pytest.raises(G.PermsDenied):
        G.set_member_role(other_owner.user, owner.pk, STAFF)  # у staff нет права


def test_demotion_drops_what_the_new_role_cannot_hold(no_mail):
    owner = _member(OWNER)
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"]})
    G.set_member_role(owner.user, admin.pk, STAFF)
    admin.refresh_from_db()
    eff = P.effective_from(admin.role, admin.permissions)
    assert "team.edit" not in eff
    assert "team.view" in eff  # видимость команды сохраняется — staff её может держать


def test_revoke_rules(no_mail):
    owner, admin, staff = (
        _member(OWNER),
        _member(ADMIN, {"add": ["team.view", "team.edit"]}),
        _member(STAFF),
    )
    with pytest.raises(G.PermsDenied):  # без team.delete
        G.revoke_member(admin.user, staff.pk)
    Membership.objects.filter(pk=admin.pk).update(
        permissions={"add": ["team.view", "team.edit", "team.delete"]}
    )
    G.revoke_member(admin.user, staff.pk)
    assert not Membership.objects.filter(pk=staff.pk).exists()
    with pytest.raises(G.PermsDenied):
        G.revoke_member(admin.user, owner.pk)
    with pytest.raises(G.PermsDenied):
        G.revoke_member(owner.user, owner.pk)  # себя — нет


def test_single_writer():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3]
    bad = []
    for path in (root / "apps").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel == "apps/core/perm_grants.py":
            continue
        text = path.read_text()
        if re.search(r"\.permissions\s*=(?!=)|update\(\s*permissions\s*=", text):
            bad.append(rel)
    assert bad == [], f"Писать Membership.permissions может только perm_grants: {bad}"
