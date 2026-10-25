"""KA-12 E6.7d: экран выдачи прав — подписи, форма участника, инвайт с правами.

Замки плана: подписи на каждый ключ/группу; форма только там, где актор вправе
править (owner — admin/staff; admin с team.edit — только staff; себя и владельца — нет);
недоступный чекбокс отключён и объясняет почему; снятый чекбокс отзывает право, а
отключённые ключи (их браузер не шлёт) сервер сохраняет; инвайт берёт блок своей роли.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from apps.core import perm_grants as G
from apps.core import perm_ui, team
from apps.core import permissions as P
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
        username=f"pu-{o}@t.de", email=f"pu-{o}@t.de", password="pw12345678"
    )
    return Membership.objects.create(user=user, role=role, permissions=perms or {})


def _admin_with_team():
    return _member(ADMIN, {"add": ["team.view", "team.edit", "team.delete"]})


def _req(user, method="get", data=None):
    req = getattr(RequestFactory(), method)(
        "/dashboard/settings/team/", data or {}, REMOTE_ADDR=f"10.8.{uuid4().int % 250}.1"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = TenantFactory(business_type="restaurant")
    return req


def _items(form):
    return {it["key"]: it for g in form["groups"] for it in g["items"]}


def _eff(m):
    m.refresh_from_db()
    return P.effective_from(m.role, m.permissions)


def test_every_key_and_group_has_a_label():
    assert set(perm_ui.LABELS) == set(P.PERMS)
    assert set(perm_ui.GROUP_LABELS) == set(P.GROUPS)


def test_owner_gets_forms_for_admin_and_staff_but_not_owner_or_self():
    owner, other_owner = _member(OWNER), _member(OWNER)
    admin, staff = _member(ADMIN), _member(STAFF)
    assert perm_ui.perm_form(owner, admin) is not None
    form = perm_ui.perm_form(owner, staff)
    assert form["state"] == G.state_token(P.for_role(STAFF))
    items = _items(form)
    assert items["team.edit"]["disabled"] and items["team.edit"]["reason"]  # role_limit
    assert not items["kunden.export"]["disabled"]  # владелец выдаёт и чувствительное
    assert perm_ui.perm_form(owner, other_owner) is None
    assert perm_ui.perm_form(owner, owner) is None


def test_admin_form_only_for_staff_and_sensitive_unchecked_is_disabled():
    admin, staff, other_admin = _admin_with_team(), _member(STAFF), _member(ADMIN)
    assert perm_ui.perm_form(admin, other_admin) is None
    items = _items(perm_ui.perm_form(admin, staff))
    assert items["kunden.export"]["disabled"] and not items["kunden.export"]["checked"]
    assert items["kunden.export"]["sensitive"]
    assert not items["kunden.view"]["disabled"]
    # admin без team.edit — формы нет вовсе
    assert perm_ui.perm_form(_member(ADMIN), staff) is None


def test_admin_cannot_revoke_sensitive_preset_key_it_lacks():
    """geld.bezahlt (🔒) есть в пресете staff; admin вправе снять только то, что имеет сам."""
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["geld.bezahlt"]})
    staff = _member(STAFF)
    item = _items(perm_ui.perm_form(admin, staff))["geld.bezahlt"]
    assert item["checked"] and item["disabled"]


def test_screen_renders_checkboxes_with_reasons():
    owner, _staff = _member(OWNER), _member(STAFF)
    html = team.team_view(_req(owner.user)).content.decode()
    assert 'name="perms_present" value="1"' in html
    assert 'name="perm" value="kunden.view"' in html
    assert "aria-describedby=" in html  # team.edit у staff — недоступен с причиной
    assert 'name="perm_staff"' in html and 'name="perms_present_staff"' in html


def test_staff_without_team_edit_sees_no_forms():
    staff = _member(STAFF, {"add": ["team.view"]})
    _member(STAFF)
    html = team.team_view(_req(staff.user)).content.decode()
    assert 'name="perms_present"' not in html
    assert 'name="perm_staff"' not in html


def _post_perms(actor, target, keys, state=None):
    form = perm_ui.perm_form(actor, target)
    data = {
        "action": "perms",
        "membership_id": str(target.pk),
        "perms_present": "1",
        "perms_state": state or form["state"],
        "perm": keys,
    }
    req = _req(actor.user, "post", data)
    resp = team.team_view(req)
    return resp, [str(m) for m in get_messages(req)]


def test_unchecked_box_revokes_and_disabled_keys_survive():
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["geld.bezahlt"]})
    staff = _member(STAFF)
    # браузер шлёт только активные отмеченные: всё из формы минус disabled минус kunden.edit
    items = _items(perm_ui.perm_form(admin, staff))
    sent = [k for k, it in items.items() if it["checked"] and not it["disabled"]]
    sent.remove("kunden.edit")
    resp, msgs = _post_perms(admin, staff, sent)
    assert resp.status_code == 302 and resp["Location"].endswith(f"#m-{staff.pk}")
    eff = _eff(staff)
    assert "kunden.edit" not in eff
    assert "geld.bezahlt" in eff  # disabled-отмеченный (вне области admin) сохранён


def test_stale_state_is_rejected_with_message():
    owner, staff = _member(OWNER), _member(STAFF)
    before = _eff(staff)
    _resp, msgs = _post_perms(owner, staff, ["verkaeufe.view"], state="0" * 16)
    assert _eff(staff) == before
    assert any("inzwischen" in m for m in msgs)


def test_forged_key_outside_scope_is_rejected():
    admin, staff = _admin_with_team(), _member(STAFF)
    before = _eff(staff)
    items = _items(perm_ui.perm_form(admin, staff))
    sent = [k for k, it in items.items() if it["checked"] and not it["disabled"]]
    _resp, msgs = _post_perms(admin, staff, sent + ["kunden.export"])
    assert _eff(staff) == before
    assert any("außerhalb" in m for m in msgs)


def _invite(actor, data):
    req = _req(actor.user, "post", {"action": "invite", **data})
    team.team_view(req)
    return [str(m) for m in get_messages(req)]


def _token_from(msgs):
    link = next(m for m in msgs if "/team/beitreten/" in m)
    return link.rstrip("/").split("/")[-1]


def test_invite_takes_only_the_block_of_the_chosen_role():
    owner = _member(OWNER)
    msgs = _invite(
        owner,
        {
            "email": "neu-pu@t.de",
            "role": STAFF,
            "perms_present_staff": "1",
            "perm_staff": ["kunden.view", "verkaeufe.edit"],
            "perms_present_admin": "1",
            "perm_admin": ["finanzen.bank"],
        },
    )
    payload = team.peek_invite(_token_from(msgs))
    assert set(payload["perms"]) == {"kunden.view", "verkaeufe.view", "verkaeufe.edit"}


def test_invite_untouched_form_equals_preset_default():
    admin = _admin_with_team()
    block = next(f for f in perm_ui.invite_forms(admin) if f["role"] == STAFF)
    sent = [
        it["key"]
        for g in block["groups"]
        for it in g["items"]
        if it["checked"] and not it["disabled"]
    ]
    msgs = _invite(
        admin,
        {"email": "neu-pu2@t.de", "role": STAFF, "perms_present_staff": "1", "perm_staff": sent},
    )
    payload = team.peek_invite(_token_from(msgs))
    assert set(payload["perms"]) == set(G.invite_defaults(admin, STAFF))
    assert [f["role"] for f in perm_ui.invite_forms(admin)] == [STAFF]


def test_requirement_of_locked_key_is_locked_and_untouched_save_succeeds():
    """geld.bezahlt заперт для admin → verkaeufe.edit/view, которые он требует, тоже
    заперты; сохранение формы «как есть» проходит без отказа."""
    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["geld.bezahlt"]})
    staff = _member(STAFF)
    items = _items(perm_ui.perm_form(admin, staff))
    assert items["verkaeufe.edit"]["disabled"] and items["verkaeufe.view"]["disabled"]
    before = _eff(staff)
    sent = [k for k, it in items.items() if it["checked"] and not it["disabled"]]
    _resp, msgs = _post_perms(admin, staff, sent)
    assert _eff(staff) == before
    assert not any("außerhalb" in m for m in msgs)


def _dependents(key, keys):
    """key + все ключи из keys, которые (транзитивно) его требуют — как снимает JS."""
    out, changed = {key}, True
    while changed:
        changed = False
        for k in keys:
            if k not in out and set(P.PERMS[k].requires) & out:
                out.add(k)
                changed = True
    return out


class _Rollback(Exception):
    pass


def test_every_enabled_box_can_be_unchecked_without_scope_denial():
    """Адверсариально: снять любой активный отмеченный ключ (с зависимыми, как JS) —
    сервер не отвечает отказом: форма не предлагает невыполнимого."""
    from django.db import transaction

    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["geld.bezahlt"]})
    staff = _member(STAFF)
    items = _items(perm_ui.perm_form(admin, staff))
    enabled = [k for k, it in items.items() if it["checked"] and not it["disabled"]]
    assert enabled
    for key in enabled:
        sent = [k for k in enabled if k not in _dependents(key, enabled)]
        try:
            with transaction.atomic():
                G.set_member_permissions(admin.user, staff.pk, sent)
                raise _Rollback
        except _Rollback:
            pass


def test_no_plain_permission_requires_a_sensitive_one():
    """Инвариант для admin-формы: отметить обычное право не тянет 🔒 (вне области admin)."""
    for perm in P.PERMS.values():
        if not perm.sensitive:
            assert not set(perm.requires) & P.SENSITIVE, perm.key


def test_every_enabled_unchecked_box_can_be_checked_without_scope_denial():
    from django.db import transaction

    admin = _member(ADMIN, {"add": ["team.view", "team.edit"], "remove": ["kunden.edit"]})
    staff = _member(STAFF, {"remove": ["kunden.edit", "sortiment.delete"]})
    items = _items(perm_ui.perm_form(admin, staff))
    current = [k for k, it in items.items() if it["checked"] and not it["disabled"]]
    to_check = [k for k, it in items.items() if not it["checked"] and not it["disabled"]]
    assert "sortiment.delete" in to_check and "kunden.edit" not in to_check
    for key in to_check:
        try:
            with transaction.atomic():
                G.set_member_permissions(admin.user, staff.pk, current + [key])
                raise _Rollback
        except _Rollback:
            pass


def test_invite_with_all_boxes_unchecked_carries_no_permissions():
    owner = _member(OWNER)
    msgs = _invite(owner, {"email": "leer-pu@t.de", "role": STAFF, "perms_present_staff": "1"})
    assert team.peek_invite(_token_from(msgs))["perms"] == []


def test_page_query_count_does_not_grow_with_members(django_assert_max_num_queries):
    owner = _member(OWNER)
    for _ in range(3):
        _member(STAFF)
    with django_assert_max_num_queries(40) as ctx:
        team.team_view(_req(owner.user))
    few = len(ctx.captured_queries)
    for _ in range(7):
        _member(STAFF)
    with django_assert_max_num_queries(few):
        team.team_view(_req(owner.user))


def test_admin_sees_note_on_other_admin_and_no_invite_without_rights():
    admin, _other = _admin_with_team(), _member(ADMIN)
    html = team.team_view(_req(admin.user)).content.decode()
    assert "Rechte dieser Person ändert nur der Inhaber." in html
    staff = _member(STAFF, {"add": ["team.view"]})
    html = team.team_view(_req(staff.user)).content.decode()
    assert 'name="email"' not in html
