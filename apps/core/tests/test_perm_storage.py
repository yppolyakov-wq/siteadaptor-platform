"""KA-12 E6.7c-1: дельта прав на участнике — нормализация, расчёт, мемо, fail-closed."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from apps.core import permissions as P
from apps.core.models import Membership

pytestmark = pytest.mark.django_db

STAFF, ADMIN, OWNER = Membership.ROLE_STAFF, Membership.ROLE_ADMIN, Membership.ROLE_OWNER

# Р-c4: чувствительные ключи в пресетах заморожены — расширение пресета чувствительным
# ключом должно быть осознанной правкой этой константы (§15.7).
FROZEN_SENSITIVE_IN_PRESETS = {
    ADMIN: frozenset(
        {
            "domains.edit",
            "finanzen.export",
            "finanzen.korrektur",
            "funktionen.edit",
            "geld.bezahlt",
            "geld.einloesen",
            "geld.erstatten",
            "geld.preis",
            "geld.rabatt",
            "geld.zahlungslink",
        }
    ),
    STAFF: frozenset(
        {
            "domains.edit",
            "funktionen.edit",
            "geld.bezahlt",
            "geld.einloesen",
            "geld.preis",
            "geld.rabatt",
            "geld.zahlungslink",
        }
    ),
}


def _user(role, perms=None):
    user = get_user_model().objects.create_user(username=f"ps-{uuid4().hex[:8]}")
    Membership.objects.create(user=user, role=role, permissions=perms or {})
    return user


def test_sensitive_keys_in_presets_are_frozen():
    for role, frozen in FROZEN_SENSITIVE_IN_PRESETS.items():
        assert P.SENSITIVE & P.PRESETS[role] == frozen, role


@pytest.mark.parametrize("role", [STAFF, ADMIN])
def test_empty_delta_is_exactly_the_preset(role):
    assert P.effective_from(role, {}) == P.for_role(role)
    assert P.effective(_user(role)) == P.for_role(role)


def test_owner_has_everything_whatever_is_stored():
    assert P.effective_from(OWNER, {"remove": ["verkaeufe.view"]}) == frozenset(P.PERMS)


def test_add_and_remove_apply_with_closure():
    eff = P.effective_from(STAFF, {"add": ["kunden.export"], "remove": ["verkaeufe.view"]})
    assert "kunden.export" in eff
    assert "verkaeufe.view" not in eff
    assert "verkaeufe.edit" not in eff  # нет view → нет edit
    assert "verkaeufe.storno" not in eff


def test_granting_edit_without_view_is_a_no_op():
    eff = P.effective_from(STAFF, {"remove": ["preise.view"], "add": ["preise.edit"]})
    assert "preise.edit" not in eff


def test_staff_never_gets_team_write_even_if_stored():
    eff = P.effective_from(STAFF, {"add": ["team.view", "team.edit", "team.delete"]})
    assert "team.view" in eff
    assert not {"team.edit", "team.delete"} & eff
    assert P.effective_from(ADMIN, {"add": ["team.view", "team.edit"]}) >= {"team.edit"}


@pytest.mark.parametrize(
    "raw",
    ["x", [], 5, {"add": "x"}, {"add": [5]}, {"remove": None}, {"add": ["x"] * 500}],
)
def test_corrupt_delta_is_fail_closed(raw):
    eff = P.effective_from(STAFF, raw)
    assert eff == P._closure(P.PRESETS[STAFF] - P.SENSITIVE)
    assert not eff & P.SENSITIVE
    assert P.effective(_user(STAFF, perms=raw if isinstance(raw, dict) else {"add": "x"})) <= (
        P.for_role(STAFF)
    )


def test_unknown_keys_are_dropped_not_corrupt():
    eff = P.effective_from(STAFF, {"add": ["gone.key", "kunden.export"]})
    assert "kunden.export" in eff


def test_normalize_is_minimal_and_idempotent():
    raw = {
        "add": ["kunden.export", "verkaeufe.view", "team.edit", "nope"],
        "remove": ["verkaeufe.edit", "kunden.export"],
        "template": "rezeption",
    }
    once = P.normalize_permissions(STAFF, raw)
    # add: уже в пресете (verkaeufe.view) и запрещённое роли (team.edit) — выброшены;
    # remove: не в пресете (kunden.export) — выброшен
    assert once == {"add": ["kunden.export"], "remove": ["verkaeufe.edit"], "template": "rezeption"}
    assert P.normalize_permissions(STAFF, once) == once


@pytest.mark.parametrize("raw", ["x", None, {"add": [1]}, {"template": 5}])
def test_normalize_never_raises(raw):
    assert P.normalize_permissions(STAFF, raw) == {}


def test_effective_is_one_query_per_request(django_assert_num_queries):
    user = _user(STAFF)
    with django_assert_num_queries(1):
        for key in ("verkaeufe.view", "kunden.view", "preise.edit"):
            P.has_perm(user, key)


def test_forget_rereads_after_a_change():
    user = _user(STAFF)
    assert P.has_perm(user, "verkaeufe.view")
    Membership.objects.filter(user=user).update(permissions={"remove": ["verkaeufe.view"]})
    assert P.has_perm(user, "verkaeufe.view")  # мемо этого запроса
    P.forget(user)
    assert not P.has_perm(user, "verkaeufe.view")


def test_memo_is_keyed_by_schema(monkeypatch):
    user = _user(STAFF)
    assert P.has_perm(user, "verkaeufe.view")
    Membership.objects.filter(user=user).update(permissions={"remove": ["verkaeufe.view"]})
    monkeypatch.setattr(P, "_schema", lambda: "other_schema")
    assert not P.has_perm(user, "verkaeufe.view")  # другая схема — мемо не переиспользуется


def test_next_request_rereads():
    """Новый объект пользователя (как request.user каждого запроса) читает заново."""
    user = _user(STAFF)
    assert P.has_perm(user, "verkaeufe.view")
    Membership.objects.filter(user=user).update(permissions={"remove": ["verkaeufe.view"]})
    fresh = get_user_model().objects.get(pk=user.pk)
    assert not P.has_perm(fresh, "verkaeufe.view")
