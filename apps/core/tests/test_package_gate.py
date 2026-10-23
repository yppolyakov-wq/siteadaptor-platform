"""T-8.32b: лёгкий пакет видит только свои экраны кабинета.

План docs/t8-32ab-package-gate-plan-2026-10-23.md §3 (b).
"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import get_resolver

from apps.core import lite_cabinet, packages, tg_login
from apps.core.middleware import PackageScopeMiddleware
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LITE = {"profile": "aktionen"}
URLCONF = "config.urls_tenant"
TEMPLATES = Path(dj_settings.BASE_DIR) / "templates" / "tenant"


def _tenant(cfg):
    return TenantFactory.build(schema_name="t832b", site_config=cfg, disabled_modules=[])


def _request(path, tenant, name, *, method="get", user=True, **headers):
    rf = RequestFactory()
    req = rf.post(path, **headers) if method == "post" else rf.get(path, **headers)
    req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    req.tenant = tenant
    req.user = SimpleNamespace(is_authenticated=True, pk=1) if user else AnonymousUser()
    req.resolver_match = SimpleNamespace(view_name=name)
    return req


def _cabinet_view_names():
    """Все именованные экраны tenant-urlconf под кабинетными префиксами."""
    from apps.core.i18n_cabinet import CABINET_PREFIXES

    out = set()

    def walk(patterns, prefix="", ns=""):
        for p in patterns:
            route = prefix + str(p.pattern)
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns, route, f"{ns}{p.namespace}:" if p.namespace else ns)
            elif p.name and ("/" + route).startswith(CABINET_PREFIXES):
                out.add(ns + p.name)

    walk(get_resolver(URLCONF).url_patterns)
    return out


def test_middleware_lets_allowed_screens_through():
    tenant = _tenant(LITE)
    mw = PackageScopeMiddleware(lambda r: None)
    for name in ("dashboard", "promotions:promotion-quick", "inbox:thread", "lite-visibility"):
        assert mw.process_view(_request("/dashboard/x/", tenant, name), None, (), {}) is None, name


def test_outside_screen_shows_not_included_page():
    tenant = _tenant(LITE)
    resp = PackageScopeMiddleware(lambda r: None).process_view(
        _request("/dashboard/settings/", tenant, "settings"), None, (), {}
    )
    assert resp.status_code == 403
    body = resp.content.decode()
    assert "data-package-not-included" in body and 'href="/dashboard/"' in body


def test_outside_post_and_fetch_get_json_403():
    tenant = _tenant(LITE)
    mw = PackageScopeMiddleware(lambda r: None)
    post = mw.process_view(
        _request("/dashboard/blog/", tenant, "blog-create", method="post"), None, (), {}
    )
    assert post.status_code == 403 and post["Content-Type"].startswith("application/json")
    fetch = mw.process_view(
        _request("/dashboard/x/", tenant, "board-action", HTTP_SEC_FETCH_MODE="cors"), None, (), {}
    )
    assert fetch.status_code == 403 and fetch["Content-Type"].startswith("application/json")


def test_storefront_and_anonymous_untouched():
    tenant = _tenant(LITE)
    mw = PackageScopeMiddleware(lambda r: None)
    assert (
        mw.process_view(_request("/aktionen/", tenant, "storefront-aktionen"), None, (), {}) is None
    )
    anon = _request("/dashboard/settings/", tenant, "settings", user=False)
    assert mw.process_view(anon, None, (), {}) is None  # вход — дело @login_required


def test_full_package_never_blocked():
    tenant = _tenant({})
    names = _cabinet_view_names()
    assert len(names) > 100
    assert all(packages.view_allowed(tenant, n) for n in names)


def test_aktionen_closes_most_of_the_cabinet():
    tenant = _tenant(LITE)
    names = _cabinet_view_names()
    closed = {n for n in names if not packages.view_allowed(tenant, n)}
    for name in ("settings", "sellable-manage", "verkaeufe", "crm:list", "finance:journal"):
        if name in names:
            assert name in closed, name
    assert len(closed) > len(names) / 2


def test_every_allow_entry_matches_a_real_screen():
    """Опечатка в белом списке = закрытый экран: каждая запись обязана что-то открывать."""
    names = _cabinet_view_names() | {
        "account_logout",
        "tg-start",
        "tg-lite-info",
        "owner-confirm-resend",
    }
    for entry in packages.PACKAGES["eintrag"].cabinet_allow:
        if entry.endswith("*"):
            assert any(n.startswith(entry[:-1]) for n in names), entry
        else:
            assert entry in names, entry


@pytest.mark.parametrize("path", sorted(TEMPLATES.glob("lite_*.html")))
def test_lite_template_links_stay_inside_the_package(path):
    """Кнопка внутри лёгкого экрана не ведёт в «nicht enthalten»: либо экран открыт
    пакету «Aktionen», либо ссылка спрятана за `|pkg_allowed`."""
    tenant = _tenant(LITE)
    body = path.read_text()
    for name in set(re.findall(r"{% url '([^']+)'", body)):
        assert packages.view_allowed(tenant, name) or f"'{name}'|pkg_allowed" in body, name


def test_lite_menu_has_messages_not_offer():
    items = [i["url_name"] for i in lite_cabinet.sidebar_items(_tenant(LITE))]
    assert "inbox:list" in items and "sellable-manage" not in items
    assert all(packages.view_allowed(_tenant(LITE), i) for i in items)
    eintrag = [i["url_name"] for i in lite_cabinet.sidebar_items(_tenant({"profile": "eintrag"}))]
    assert "sellable-manage" in eintrag


def test_mini_app_lite_set_is_cut_by_the_package():
    tenant = _tenant(LITE)
    reachable = {n for n in tg_login.TG_LITE_VIEWS if packages.view_allowed(tenant, n)}
    assert "inbox:list" in reachable
    assert "sellable-manage" not in reachable and "catalog:product-create" not in reachable
    assert "promotions:voucher-redeem" not in reachable
