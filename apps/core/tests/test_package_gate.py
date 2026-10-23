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
        if entry.endswith("-*"):
            assert any(n.startswith(entry[:-1]) for n in names), entry
        else:
            assert entry in names, entry


_ROOT = Path(dj_settings.BASE_DIR) / "templates"
#: Шаблоны экранов, открытых пакету «Aktionen», + хром кабинета.
_REACHABLE = sorted(
    [
        *TEMPLATES.glob("lite_*.html"),
        TEMPLATES / "_base_dashboard.html",
        TEMPLATES / "notifications.html",
        TEMPLATES / "package_not_included.html",
        _ROOT / "jobs" / "detail.html",
        _ROOT / "jobs" / "new.html",
        _ROOT / "catalog" / "product_form.html",
        *(_ROOT / "inbox").glob("*.html"),
        *(
            _ROOT / "promotions" / f"{n}.html"
            for n in (
                "promotion_form",
                "promotion_quick",
                "promotion_quick_done",
                "promotion_share",
                "promotion_preview",
                "reservation_list",
                "redeem",
                "redeem_detail",
            )
        ),
    ]
)
#: Осознанные исключения: ссылка видна только при условии, которого у пакета нет.
_KNOWN = {
    "detail.html": {"finance:invoice-detail"},  # {% if finance_active %} — finance вне пакета
    "redeem.html": {"promotions:voucher-redeem"},  # префикс ваучеров loyalty/gift для сканера
}


def _cabinet_name(name):
    """Ссылка ведёт в кабинет (а не на витрину)? Аргументы подставляем пробно."""
    from django.urls import NoReverseMatch, reverse

    from apps.core.i18n_cabinet import CABINET_PREFIXES

    for args in ((), ["00000000-0000-0000-0000-000000000000"], [1]):
        try:
            return reverse(name, args=args, urlconf=URLCONF).startswith(CABINET_PREFIXES)
        except NoReverseMatch:
            continue
    return not name.startswith("storefront")


@pytest.mark.parametrize("path", [p for p in _REACHABLE if p.exists()], ids=lambda p: p.name)
def test_reachable_template_links_stay_inside_the_package(path):
    """Кнопка внутри доступного экрана не ведёт в «nicht enthalten»: либо экран открыт
    пакету «Aktionen», либо ссылка спрятана за `|pkg_allowed`."""
    tenant = _tenant(LITE)
    body = path.read_text()
    known = _KNOWN.get(path.name, set())
    for name in set(re.findall(r"{% url '([^']+)'", body)):
        if name in known or not _cabinet_name(name):
            continue
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


def test_template_look_and_bundle_keep_the_package():
    """Ревью T-8.32b: пакет выведен из `profile` — шаблон/Look/сборка не должны его
    стирать (иначе лёгкий бизнес молча получил бы весь кабинет)."""
    from apps.tenants import sitetemplates

    t = TenantFactory(schema_name="public", slug="t832b-keep", site_config=dict(LITE))
    sitetemplates.apply_template(t, sitetemplates.TEMPLATES[0]["key"])
    assert packages.package_of(t).key == "aktionen"
    sitetemplates.apply_look(t, sitetemplates.LOOK_FAMILIES[0]["key"])
    assert packages.package_of(t).key == "aktionen"
    sitetemplates.apply_bundle(t, sitetemplates.BUNDLES[0]["key"])
    assert packages.package_of(t).key == "aktionen"


def test_offer_composer_is_outside_aktionen():
    """Sofort-Angebot создаёт заказ — продажа вне пакета «Aktionen»."""
    tenant = _tenant(LITE)
    assert not packages.view_allowed(tenant, "inbox:offer-compose")
    assert not packages.view_allowed(tenant, "gbp-merchant")
    assert not packages.view_allowed(tenant, "")
