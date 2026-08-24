"""W8-1/W8-2: единый реестр навигации — производные, карта подсветки, достижимость.

Главный инвариант (класс ошибок «care»/«сирота» невозможен молча):
- каждый nav-литерал из вьюх имеет якорь в карте подсветки;
- каждая запись реестра reverse'ится (нет табов в 404/NoReverseMatch).
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core import nav_registry
from apps.core.templatetags.cabinet import HUB_TABS

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- производные сохраняют легаси-форму ---------------------------------------
def test_hub_tabs_is_derived_with_legacy_shape():
    assert set(HUB_TABS) == set(nav_registry.HUBS)
    first = HUB_TABS["settings"][0]
    assert first[0] == "settings" and str(first[1]) == "Mein Geschäft"  # W9-1
    assert first[2] == "settings" and first[3] is None and first[4] is False
    # SR-1: страница товаров умерла — записей «Produkte» в реестре больше нет,
    # обзор Sortiment есть в обоих хабах (catalog-страницы и раздел sellables).
    assert not any(t[0] == "catalog:product-list" for t in HUB_TABS["catalog"])
    assert not any(t[0] == "catalog:product-list" for t in HUB_TABS["sellables"])
    assert any(t[0] == "sellable-manage" for t in HUB_TABS["catalog"])


def test_sidebar_anchors_from_registry():
    from types import SimpleNamespace

    from apps.core import modules

    t = SimpleNamespace(site_config={}, disabled_modules=[], enabled_modules=[], business_type="")
    items = modules.sidebar_nav(t)
    assert [it["nav_key"] for it in items] == [a.nav_key for a in nav_registry.ANCHORS]
    marketing = next(it for it in items if it["nav_key"] == "promotions")
    assert marketing["badge"] == "inbox"
    # X0 (cabinet-cleanup-2026-08-19, осознанная переписка): без promotions якорь
    # Marketing ОСТАЁТСЯ, пока жив любой модуль его хаба (inbox/reviews/…) —
    # прежний гейт отбирал у отеля вход к сообщениям клиентов. Полное скрытие
    # (все модули хаба выключены) — замок в test_sidebar_st4b.
    t2 = SimpleNamespace(
        site_config={}, disabled_modules=["promotions"], enabled_modules=[], business_type=""
    )
    assert "promotions" in [it["nav_key"] for it in modules.sidebar_nav(t2)]


# --- W8-2: достижимость -------------------------------------------------------
def test_every_registry_url_reverses():
    for e in nav_registry.ENTRIES:
        assert reverse(e.url_name), e.url_name
    for a in nav_registry.ANCHORS:
        assert reverse(a.url_name), a.url_name


def _nav_literals():
    root = Path(__file__).resolve().parents[3] / "apps"
    seen = set()
    pat = re.compile(r'"nav":\s*"([a-z_-]+)"|nav="([a-z_-]+)"')
    for path in root.rglob("*.py"):
        if "/tests/" in str(path) or "/migrations/" in str(path):
            continue
        for m in pat.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            seen.add(m.group(1) or m.group(2))
    return seen


def test_every_view_nav_key_has_sidebar_anchor():
    """Каждый экран кабинета (литерал "nav" во вьюхах) подсвечивает какой-то якорь.
    Новый экран без записи в реестре/карте ломает этот тест — сироты невозможны."""
    missing = {k for k in _nav_literals() if not nav_registry.anchor_for(k)}
    assert not missing, f"nav без якоря в nav_registry: {sorted(missing)}"


def test_anchor_for_identity_and_unknown():
    for a in nav_registry.ANCHORS:
        assert nav_registry.anchor_for(a.nav_key) == a.nav_key
    assert nav_registry.anchor_for("definitely-unknown") == ""
    assert nav_registry.anchor_for("") == ""


# --- подсветка end-to-end: под-страница хаба подсвечивает якорь ---------------
def test_settings_subpage_highlights_settings_anchor():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    class _User:
        is_authenticated = True
        is_active = True
        username = "owner"

    req = RequestFactory().get("/dashboard/settings/notifications/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory(business_type="restaurant")
    html = views.notifications_settings(req).content.decode()
    # nav="notifications" → раздел «Einstellungen» активен (раньше — ничего).
    # R7-1: раздел с подменю — кнопка-тумблер [data-nav-toggle], не ссылка;
    # подсветка та же (залитая индиго-пилюля стиля B).
    m = re.search(r'data-nav-toggle="settings"[^>]*class="nav-link[^"]*"', html, re.S)
    assert m and "bg-indigo-600" in m.group(0), m.group(0) if m else html[:200]


def test_palette_rendered_on_cabinet_pages():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    class _User:
        is_authenticated = True
        is_active = True
        username = "owner"

    req = RequestFactory().get("/dashboard/settings/notifications/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory(business_type="restaurant")
    html = views.notifications_settings(req).content.decode()
    assert 'id="navpal"' in html and 'id="navpal-open"' in html
    assert "Abo &amp; Rechnung" in html  # запись реестра в палитре (раньше — сирота)


def test_palette_entries_unique_and_complete():
    entries = nav_registry.palette_entries()
    urls = [e["url_name"] for e in entries]
    assert len(urls) == len(set(urls))  # без дублей (Sortiment-дубль схлопнут)
    assert "billing" in urls and "verkaeufe" in urls and "finder-settings" in urls
