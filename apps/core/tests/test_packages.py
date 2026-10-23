"""T-8.32a: пакет бизнеса — потолок модулей и лёгкая витрина.

План docs/t8-32ab-package-gate-plan-2026-10-23.md.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve

from apps.core import modules, packages
from apps.tenants import menu, siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

AKTIONEN = {"profile": "aktionen"}
OUTSIDE = ("blog", "customer_account", "crm", "loyalty", "gift", "orders", "booking", "reviews")


def _request(path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return request


@pytest.mark.parametrize(
    ("config", "key"),
    [
        ({"profile": "aktionen"}, "aktionen"),
        ({"profile": "eintrag"}, "eintrag"),
        ({}, "laden"),
        ({"profile": "shop"}, "laden"),
        ("garbage", "laden"),
    ],
)
def test_package_is_derived_from_profile(config, key):
    assert packages.package_of(TenantFactory.build(site_config=config)).key == key
    assert packages.package_of(None).key == "laden"


@pytest.mark.parametrize("business_type", [code for code, _ in Tenant.BUSINESS_TYPES])
def test_full_package_keeps_every_module_as_before(business_type, monkeypatch):
    """Паритет Laden: без профиля потолок ничего не меняет ни у одного типа бизнеса."""
    tenant = TenantFactory.build(
        site_config={},
        business_type=business_type,
        disabled_modules=modules.default_disabled_for(business_type),
    )
    after = {s.key: modules.is_module_active(tenant, s.key) for s in modules.REGISTRY}
    monkeypatch.setattr(packages, "module_allowed", lambda *a: True)
    before = {s.key: modules.is_module_active(tenant, s.key) for s in modules.REGISTRY}
    assert after == before


def test_aktionen_package_caps_modules_without_writing():
    tenant = TenantFactory.build(site_config=dict(AKTIONEN), disabled_modules=[])
    for key in OUTSIDE:
        assert not modules.is_module_active(tenant, key), key
    for key in ("promotions", "inbox", "jobs", "publishing", "telegram", "catalog", "dashboard"):
        assert modules.is_module_active(tenant, key), key
    # Потолок вычисляется, а не пишется: выбор владельца цел для будущего подъёма пакета.
    assert tenant.disabled_modules == []


def test_lite_storefront_header_has_no_blog_and_no_duplicate_offers():
    """Без своего меню шапка выводится из легаси-nav: «Neuigkeiten» (блог включён
    пресетом), «Angebote» → главная, «Angebot anfordern» и «Eine Frage stellen» у лёгкой
    витрины не появляются (фидбэк 2026-10-23: чат уже в плавающей кнопке, заявка — у
    акции); акции и «Über uns» — да."""
    tenant = TenantFactory.build(site_config=dict(AKTIONEN), disabled_modules=[])
    urls = {n["url"] for n in menu.resolve_menu(tenant, "top")}
    # Витрина зовёт с нормализованным конфигом (context.py) — там `menus` есть всегда.
    cfg_urls = {
        n["url"] for n in menu.resolve_menu(tenant, "top", siteconfig.normalize({**AKTIONEN}))
    }
    assert cfg_urls == urls
    assert "/blog/" not in urls
    assert "/" not in urls
    assert "/aktionen/" in urls and "/ueber-uns/" in urls
    assert not any(u and u.startswith(("/nachricht", "/anfrage")) for u in urls)
    # чат никуда не делся: плавающая кнопка — при том же гейте модуля, что и пункт
    src = open("templates/storefront/_base.html").read()
    assert "{% if storefront_inbox_enabled %}" in src.split("data-chat-fab", 1)[0][-600:]


def test_lite_header_filtered_even_after_config_was_saved_normalized():
    """Фидбэк 2026-10-23 (бизнес из бота): мастер/дизайн/регистрация сохраняют конфиг
    через normalize, а он кладёт выведенное автоменю в `menus`. Это меню — НЕ собранное
    владельцем: лишние пункты должны уйти и здесь."""
    saved = siteconfig.normalize({**AKTIONEN})
    assert isinstance(saved.get("menus"), dict)
    tenant = TenantFactory.build(site_config=saved, disabled_modules=[])
    for cfg in (None, siteconfig.normalize(saved)):
        urls = {n["url"] for n in menu.resolve_menu(tenant, "top", cfg)}
        assert "/" not in urls
        assert not any(u and u.startswith(("/nachricht", "/anfrage")) for u in urls), urls
        assert "/aktionen/" in urls and "/ueber-uns/" in urls


def test_full_storefront_header_unchanged():
    tenant = TenantFactory.build(site_config={}, disabled_modules=[])
    urls = {n["url"] for n in menu.resolve_menu(tenant, "top")}
    assert "/" in urls and "/blog/" in urls


def test_owner_menu_with_start_is_kept_on_lite_storefront():
    """Меню, собранное владельцем, не трогаем: «Start» там мог стоять осознанно."""
    cfg = {
        "profile": "aktionen",
        "menus": {"top": {"items": [{"label": "Start", "type": "page", "target": "home"}]}},
    }
    tenant = TenantFactory.build(site_config=cfg, disabled_modules=[])
    assert [n["url"] for n in menu.resolve_menu(tenant, "top")] == ["/"]


def test_blog_address_is_gone_for_lite_business():
    tenant = TenantFactory.build(
        schema_name="t832a_blog", slug="t832a-blog", site_config=dict(AKTIONEN), disabled_modules=[]
    )
    from apps.core.middleware import ModuleGatingMiddleware

    request = _request("/blog/", tenant)
    with pytest.raises(Http404):
        ModuleGatingMiddleware(lambda r: None)(request)
    assert resolve("/blog/", urlconf="config.urls_tenant")


def test_modules_page_save_does_not_write_the_package_ceiling():
    """Тумблер вне пакета заперт, но Save не записывает потолок в disabled_modules:
    при подъёме пакета блог владельца снова на месте."""
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware

    from apps.core import views

    tenant = TenantFactory(
        schema_name="t832a_mod",
        slug="t832a-mod",
        site_config=dict(AKTIONEN),
        disabled_modules=["gift"],
    )
    user = get_user_model().objects.create_user(username="t832a", password="pw12345678")
    get = _request("/dashboard/modules/", tenant)
    get.user = user
    MessageMiddleware(lambda r: None).process_request(get)
    html = views.modules_view(get).content.decode()
    assert "Nicht im Paket" in html or "Not in your package" in html

    # Подделанный POST: включить gift и выключить blog — оба вне пакета, выбор из БД цел.
    keys = [s.key for s in modules.optional_modules() if s.key != "blog"]
    post = RequestFactory().post("/dashboard/modules/", {"modules": keys})
    post.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    post.tenant, post.user = tenant, user
    MessageMiddleware(lambda r: None).process_request(post)
    views.modules_view(post)
    tenant.refresh_from_db()
    assert tenant.disabled_modules == ["gift"]


def test_package_report_lists_lost_modules_without_touching_the_tenant():
    from apps.tenants.management.commands.package_report import report_for

    lite = TenantFactory.build(
        schema_name="public", site_config=dict(AKTIONEN), disabled_modules=["gift"]
    )
    row = report_for(lite)
    assert row["package"] == "aktionen"
    assert "blog" in row["modules_lost"] and "gift" not in row["modules_lost"]
    assert "promotions" not in row["modules_lost"]
    full = report_for(TenantFactory.build(schema_name="public", site_config={}))
    assert full["package"] == "laden" and full["modules_lost"] == []
    assert lite.disabled_modules == ["gift"]
