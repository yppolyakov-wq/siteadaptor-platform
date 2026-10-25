"""KA-12 E6.7f: шаблоны ролей + новые дефолты сотрудника.

План — docs/ka-12-e6-7f-role-templates-plan-2026-10-25.md. Замки: шаблон — ключи реестра,
в лимите роли и замкнуты по requires; применение = обычная выдача (области, stale) и
даёт ровно ключи шаблона с подписью; после правки — «angepasst»; шаблон чужой роли и
вне области актора — отказ; у staff по умолчанию нет финансов/процессов/доменов/функций.
"""

import pytest

from apps.core import perm_grants as G
from apps.core import perm_ui, team
from apps.core import permissions as P
from apps.core import role_templates as RT
from apps.core.models import Membership
from apps.core.tests.test_team_perms_ui import _admin_with_team, _eff, _member, _post_perms, _req

pytestmark = pytest.mark.django_db
OWNER, ADMIN, STAFF = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF


@pytest.mark.parametrize("key", sorted(RT.TEMPLATES))
def test_template_is_valid_for_its_role(key):
    t = RT.TEMPLATES[key]
    assert t.keys <= set(P.PERMS)
    assert t.keys <= P.ROLE_LIMIT[t.role]
    assert P._closure(t.keys) == t.keys, "шаблон не замкнут по requires"
    assert G.with_requires(t.keys) == set(t.keys)


def test_staff_default_has_no_finance_processes_domains_functions():
    staff = P.for_role(STAFF)
    for key in P._ADMIN_BY_DEFAULT:
        assert key not in staff, key
        assert key in P.for_role(ADMIN), key


def test_templates_for_business_type():
    from types import SimpleNamespace

    hotel = {t.key for t in RT.templates_for(SimpleNamespace(business_type="hotel"), STAFF)}
    shop = {t.key for t in RT.templates_for(SimpleNamespace(business_type="shop"), STAFF)}
    assert {"rezeption", "housekeeping", "mitarbeiter"} <= hotel
    assert "rezeption" not in shop and "kueche" not in shop


def _apply(actor, target, key):
    form = perm_ui.perm_form(actor, target)
    req = _req(
        actor.user,
        "post",
        {
            "action": "perms",
            "membership_id": str(target.pk),
            "perms_state": form["state"],
            "apply_template": key,
        },
    )
    team.team_view(req)
    from django.contrib.messages import get_messages

    return [str(m) for m in get_messages(req)]


def test_owner_applies_template_exactly_and_label_shows():
    owner, staff = _member(OWNER), _member(STAFF)
    _apply(owner, staff, "aushilfe")
    assert _eff(staff) == RT.TEMPLATES["aushilfe"].keys
    staff.refresh_from_db()
    assert staff.permissions.get("template") == "aushilfe"
    assert perm_ui.perm_form(owner, staff)["template_label"] == "Aushilfe / Kasse"


def test_manual_edit_after_template_marks_adjusted():
    owner, staff = _member(OWNER), _member(STAFF)
    _apply(owner, staff, "aushilfe")
    staff.refresh_from_db()
    form = perm_ui.perm_form(owner, staff)
    keys = sorted(RT.TEMPLATES["aushilfe"].keys | {"sortiment.view"})
    _post_perms(owner, staff, keys, state=form["state"])
    staff.refresh_from_db()
    assert "angepasst" in perm_ui.perm_form(owner, staff)["template_label"]


def test_template_of_other_role_is_rejected():
    owner, staff = _member(OWNER), _member(STAFF)
    before = _eff(staff)
    msgs = _apply(owner, staff, "leitung")  # admin-шаблон на staff — подделка
    assert _eff(staff) == before
    assert any("Rolle" in m for m in msgs)


def test_admin_cannot_apply_template_beyond_scope():
    admin = _admin_with_team()
    staff = _member(STAFF, {"remove": ["geld.bezahlt"]})
    form = perm_ui.perm_form(admin, staff)
    cards = {t["key"]: t for t in form["templates"]}
    # «Mitarbeiter» вернул бы 🔒 geld.bezahlt — admin его выдать не может → недоступно
    assert cards["mitarbeiter"]["disabled"] and cards["mitarbeiter"]["reason"]
    before = _eff(staff)
    _apply(admin, staff, "mitarbeiter")
    assert _eff(staff) == before


def test_admin_template_cards_for_admin_member():
    owner, admin = _member(OWNER), _member(ADMIN)
    keys = {t["key"] for t in perm_ui.perm_form(owner, admin)["templates"]}
    assert keys == {"leitung", "buchhaltung"}
    _apply(owner, admin, "buchhaltung")
    assert _eff(admin) == RT.TEMPLATES["buchhaltung"].keys
