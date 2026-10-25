"""KA-12 E6.7b: у каждого экрана кабинета есть право, и оно равно сегодняшнему доступу."""

from importlib import import_module
from uuid import uuid4

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from django.urls import URLPattern, URLResolver, get_resolver

from apps.core import permissions, view_perms
from apps.core.i18n_cabinet import CABINET_PREFIXES
from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership
from apps.core.tests import legacy_role_gates as LG
from apps.tenants.tests.factories import TenantFactory

OWNER_ONLY_KEYS = frozenset(permissions.PERMS) - permissions.PRESETS["admin"]
ADMIN_ONLY_KEYS = permissions.PRESETS["admin"] - permissions.PRESETS["staff"]
# E6.7f: «сегодня у staff» = пресет E6.7a; ключи, снятые В-2/В-3, — осознанно admin-дефолт.
STAFF_KEYS = permissions.PRESETS["staff"] | permissions._ADMIN_BY_DEFAULT

# Сегодня открыты по префиксу, но всё действие закрыто проверкой ВНУТРИ вьюхи
# (отказ тем же 403/сообщением) — правило честно называет это право.
INLINE_GATED = {
    "deal-advance-invoice": "finanzen.korrektur — PermissionDenied во вьюхе",
    "deal-refund": "geld.korrektur — owner-only префикс /dashboard/erstattung/",
    "stays:price-calendar-apply": "preise.edit — _can_edit во вьюхе",
    "stays:price-day": "preise.edit на запись — _can_edit во вьюхе",
    "stays:price-calendar": "preise.edit на запись — _can_edit во вьюхе",
    # KA-12 Z-6: экран новее эталона ролей — сразу по праву выгрузки (kunden.export).
    "stays:meldescheine-export": "kunden.export — новый экран, правило в view_perms",
}


def _walk(patterns, prefix="", ns=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            sub = ns + (f"{p.namespace}:" if p.namespace else "")
            yield from _walk(p.url_patterns, prefix + str(p.pattern), sub)
        elif isinstance(p, URLPattern):
            yield "/" + prefix + str(p.pattern), p.callback, (ns + p.name) if p.name else ""


def _cabinet_views():
    return [
        (route, cb, name)
        for route, cb, name in _walk(get_resolver("config.urls_tenant").url_patterns)
        if route.startswith(CABINET_PREFIXES)
    ]


def test_every_cabinet_view_has_a_rule():
    missing = [f"{name or '?'} {route}" for route, _cb, name in _cabinet_views() if not name]
    missing += [
        f"{name} {route}"
        for route, _cb, name in _cabinet_views()
        if view_perms.rule_for(name) is None
    ]
    assert missing == [], "Новый экран кабинета без права (apps/core/view_perms.py): " + ", ".join(
        missing
    )


def test_every_rule_names_a_real_view():
    names = {name for _r, _c, name in _cabinet_views()}
    stale = sorted(set(view_perms.RULES) - names)
    assert stale == [], f"Правила для несуществующих экранов: {stale}"


def _today_gate(route, callback, name=""):
    """Сегодняшний ролевой гейт экрана: 'owner' / 'finance' / ''."""
    static = route.split("<", 1)[0]
    role = LG.LEGACY_DECORATED.get(name, "")
    if role:
        return role
    if "<" not in route:
        return LG.legacy_role_for_path(route)
    return (
        LG.legacy_role_for_path(static)
        if static.startswith(LG.LEGACY_OWNER_ONLY_PREFIXES + LG.LEGACY_FINANCE_EXPORT_PREFIXES)
        else ""
    )


def _keys(rule):
    return {k for k in (rule.read, rule.write) if k not in (view_perms.OPEN, view_perms.FLOOR)}


def test_rules_match_todays_access():
    """Паритет E6.7b: owner-only экран → только owner-ключи или пол; финансовая выгрузка →
    ключ admin; всё прочее → ключи, которые сегодня есть у staff."""
    bad = []
    for route, cb, name in _cabinet_views():
        rule = view_perms.rule_for(name)
        gate = _today_gate(route, cb, name)
        keys = _keys(rule)
        if gate == LG.ROLE_OWNER_ONLY:
            floor_both = rule.read == rule.write == view_perms.FLOOR
            if (
                not keys <= OWNER_ONLY_KEYS
                or (not keys and not floor_both)
                or (keys and view_perms.OPEN in (rule.read, rule.write))
            ):
                bad.append(f"{name}: сегодня только владелец, правило {rule}")
        elif gate == LG.ROLE_FINANCE:
            if not keys or not keys <= ADMIN_ONLY_KEYS:
                bad.append(f"{name}: сегодня owner+admin, правило {rule}")
        elif name in INLINE_GATED:
            continue
        else:
            if view_perms.FLOOR in (rule.read, rule.write) or not keys <= STAFF_KEYS:
                bad.append(f"{name}: сегодня открыт сотрудникам, правило {rule}")
    assert bad == []


def test_inline_gated_list_is_honest():
    """Исключения паритета обязаны требовать ключ СТРОЖЕ staff (на чтение или запись)."""
    for name in INLINE_GATED:
        rule = view_perms.rule_for(name)
        assert rule is not None, name
        assert _keys(rule) - STAFF_KEYS, f"{name}: исключение без более строгого ключа"


@pytest.mark.django_db
def test_palette_sections_follow_rights(monkeypatch):
    from apps.core import palette_search as ps

    called = []
    for key in ps.SECTION_PERMS:
        fn_name = {"deals": "_deals", "customers": "_customers", "sellables": "_sellables"}[key]
        monkeypatch.setattr(ps, fn_name, lambda t, q, owner=False, k=key: called.append(k) or [])
    ps.search(None, "anna", perms=frozenset({"kunden.view"}))
    assert called == ["customers"]
    called.clear()
    ps.search(None, "anna", perms=frozenset())
    assert called == []


# --- поведение middleware ------------------------------------------------------------

pytestmark_db = pytest.mark.django_db


def _user(role):
    user = get_user_model().objects.create_user(username=f"vp-{role}-{uuid4().hex[:6]}")
    Membership.objects.create(user=user, role=role)
    return user


def _call(path, user, method="get", view_name=None):
    tenant = TenantFactory.build(schema_name=f"vp_{uuid4().hex[:6]}")
    request = getattr(RequestFactory(), method)(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.user = user
    request.tenant = tenant

    class Match:
        pass

    request.resolver_match = Match()
    request.resolver_match.view_name = view_name
    mw = CabinetOwnerAccessMiddleware(lambda r: None)
    return mw.process_view(request, lambda r: None, (), {})


@pytest.mark.django_db
def test_staff_without_key_gets_403(monkeypatch):
    user = _user(Membership.ROLE_STAFF)
    assert _call("/dashboard/verkaeufe/", user, view_name="verkaeufe") is None
    # E6.7f: финансы у staff по умолчанию закрыты
    assert _call("/dashboard/finance/", user, view_name="finance:journal").status_code == 403
    monkeypatch.setattr("apps.core.permissions.effective", lambda u: frozenset())
    resp = _call("/dashboard/finance/", user, view_name="finance:journal")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_write_key_checked_on_post(monkeypatch):
    user = _user(Membership.ROLE_STAFF)
    monkeypatch.setattr(
        "apps.core.permissions.effective", lambda u: frozenset({"finanzen.journal"})
    )
    assert _call("/dashboard/finance/", user, view_name="finance:journal") is None
    resp = _call("/dashboard/finance/", user, "post", view_name="finance:journal")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_floor_is_owner_only_even_with_every_key(monkeypatch):
    admin = _user(Membership.ROLE_ADMIN)
    monkeypatch.setattr("apps.core.permissions.effective", lambda u: frozenset(permissions.PERMS))
    resp = _call("/dashboard/recht/", admin, view_name="legal-docs")
    assert resp.status_code == 403
    assert _call("/dashboard/recht/", _user(Membership.ROLE_OWNER), view_name="legal-docs") is None


@pytest.mark.django_db
def test_unknown_view_is_an_error_in_tests_and_403_in_prod():
    user = _user(Membership.ROLE_OWNER)
    with pytest.raises(ImproperlyConfigured):
        _call("/dashboard/x/", user, view_name="nope-view")
    with override_settings(PERMS_STRICT=False):
        assert _call("/dashboard/x/", user, view_name="nope-view").status_code == 403


@pytest.mark.django_db
def test_storefront_paths_are_untouched():
    user = _user(Membership.ROLE_STAFF)
    assert _call("/sortiment/", user, view_name="nope-view") is None


def test_registry_keys_are_known():
    for rule in view_perms.RULES.values():
        for key in (rule.read, rule.write):
            assert key in (view_perms.OPEN, view_perms.FLOOR) or key in permissions.PERMS


def test_legacy_role_gates_are_gone_from_code():
    """E6.7c-4: ролевые префиксы и декораторы сняты — доступ только из view_perms."""
    import pathlib
    import re

    root = pathlib.Path(dj_settings.BASE_DIR) / "apps"
    banned = re.compile(
        r"\b(OWNER_ONLY_PREFIXES|FINANCE_EXPORT_PREFIXES|required_role_for_path|"
        r"owner_required|finance_export_required)\b"
    )
    hits = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if "tests" not in p.parts and "migrations" not in p.parts and banned.search(p.read_text())
    ]
    assert hits == []
