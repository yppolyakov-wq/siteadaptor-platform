"""KA-12 E6.7e: навигация по правам — скрываем ровно то, что middleware отдал бы 403.

План — docs/ka-12-e6-7e-nav-by-perms-plan-2026-10-25.md. Источник один — ``view_perms``
(+ ``QUERY_RULES`` для вкладок-адресов). Замки: каждая ссылка кабинета, которую видит
сотрудник с урезанными правами, открывается (адверсариально по дельтам); раздел без
разрешённых экранов скрыт; вкладка «Kunden» без ``kunden.view`` не отдаёт список.
"""

import re
from urllib.parse import urlsplit

import pytest
from django.urls import Resolver404, resolve

from apps.core import modules, nav_registry, sales_page, view_perms
from apps.core import permissions as P
from apps.core.models import Membership
from apps.core.tests.test_staff_walk import _open, _tenant, _user

pytestmark = pytest.mark.django_db

ROLE_KEYS = sorted(P.for_role(Membership.ROLE_STAFF))
PAGES = ("/dashboard/", "/dashboard/verkaeufe/", "/dashboard/settings/")
HREF = re.compile(r'href="(/(?:dashboard|crm|catalog|promotions|finance|imports)[^"#]*)"')


def _staff(remove=()):
    user = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=user).update(permissions={"remove": sorted(remove)})
    return user


def _assert_links_allowed(tenant, user, label):
    bad = []
    for page in PAGES:
        resp = _open(page, tenant, user)
        if resp.status_code != 200:
            continue  # сам экран закрыт — его ссылки в меню и так не показаны (проверено ниже)
        html = resp.content.decode()
        for href in set(HREF.findall(html)):
            parts = urlsplit(href.replace("&amp;", "&"))
            try:
                match = resolve(parts.path)
            except Resolver404:
                continue
            name = match.view_name
            if view_perms.rule_for(name) is None:
                continue  # не экран кабинета (витрина/статика) — не наша зона
            query = f"?{parts.query}" if parts.query else ""
            if not view_perms.allowed(user, name, "GET") or not view_perms.query_allowed(
                user, name, query
            ):
                bad.append((page, href))
    assert not bad, f"{label}: ссылки на запрещённые экраны {bad[:8]}"


@pytest.mark.parametrize("kind", ["bakery", "hotel", "friseur", "catering"])
def test_staff_preset_sees_only_allowed_links(kind):
    tenant = _tenant(kind)
    _assert_links_allowed(tenant, _staff(), f"{kind}/staff")


@pytest.mark.parametrize("key", ROLE_KEYS)
def test_staff_without_one_key_sees_only_allowed_links(key):
    """Адверсариально: снять по одному каждый ключ пресета (с зависимыми)."""
    tenant = _tenant("bakery")
    _assert_links_allowed(tenant, _staff([key]), f"-{key}")


def test_sidebar_items_all_allowed_and_empty_section_hidden():
    tenant = _tenant("hotel")
    user = _staff([k for k in ROLE_KEYS if k.startswith(("verkaeufe", "rezeption", "ablaeufe"))])
    items = modules.sidebar_nav(tenant, user)
    for it in items:
        for name in [it["target"]] + [c["url_name"] for c in it["children"]]:
            assert view_perms.allowed(user, name, "GET"), (it["nav_key"], name)
    assert "board" not in {it["nav_key"] for it in items}  # «Verkäufe» без права — скрыт


def test_owner_sidebar_unchanged_by_permissions():
    tenant = _tenant("hotel")
    owner = _user(Membership.ROLE_OWNER)
    assert nav_registry.hidden_for(owner) == frozenset()
    assert any(it["nav_key"] == "board" for it in modules.sidebar_nav(tenant, owner))


def test_customers_tab_requires_kunden_view():
    tenant = _tenant("bakery")
    staff = _staff(["kunden.view"])
    assert sales_page.customers_tab(tenant, "", staff) is None
    resp = _open("/dashboard/verkaeufe/?tab=kunden", tenant, staff)
    html = resp.content.decode()
    assert "data-kunden-tab" not in html
    allowed = _staff()
    assert sales_page.customers_tab(tenant, "", allowed) is not None
    assert "data-kunden-tab" in _open("/dashboard/verkaeufe/", tenant, allowed).content.decode()


def test_query_rules_point_to_registered_screens():
    for (name, query), key in view_perms.QUERY_RULES.items():
        assert view_perms.rule_for(name) is not None, name
        assert query.startswith("?") and key in P.PERMS


def test_mobile_tabbar_keeps_mehr_without_sales_section():
    from apps.core.context import _cabinet_tabbar

    tenant = _tenant("hotel")
    user = _staff([k for k in ROLE_KEYS if k.startswith(("verkaeufe", "rezeption", "ablaeufe"))])
    bar = _cabinet_tabbar(tenant, modules.sidebar_nav(tenant, user), user)
    keys = [b["nav_key"] for b in bar]
    assert "dashboard" in keys and "board" not in keys


def test_home_shows_sales_loop_and_widgets_only_with_section_rights(monkeypatch):
    """Ревью безопасности E6.7e: главная открыта всем, но данные разделов — по праву."""
    from apps.core import dashboard as dash

    tenant = _tenant("bakery")
    tenant.site_config = {**(tenant.site_config or {}), "onboarding": {"completed": True}}
    tenant.save(update_fields=["site_config"])
    owner = _user(Membership.ROLE_OWNER)
    staff = _staff([k for k in ROLE_KEYS if k.startswith(("verkaeufe", "rezeption", "ablaeufe"))])
    sample = [{"key": k} for k in dash.WIDGET_PERMS] + [{"key": "unbekannt"}]
    assert {w["key"] for w in dash.widgets_for(owner, sample)} == set(dash.WIDGET_PERMS)
    sample.append({"key": "orders_new"})
    assert not {"ready", "stays_today", "orders_new"} & {
        w["key"] for w in dash.widgets_for(staff, sample)
    }
    seen = []
    real = sales_page.body_context

    def _spy(req, kind, view):
        seen.append(kind)
        return real(req, kind, view)

    monkeypatch.setattr(sales_page, "body_context", _spy)
    _open("/dashboard/", tenant, staff)
    assert seen == []  # петля продаж без verkaeufe.view не собирается
    _open("/dashboard/", tenant, owner)
    assert seen  # у владельца — собирается
