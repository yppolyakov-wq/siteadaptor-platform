"""SR-5 (R5c A+B): живые подписи настроек + страница-обзор Einstellungen."""

import pytest
from django.test import RequestFactory

from apps.core import modules, settings_hints
from apps.core.settings_home import einstellungen_home
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    return TenantFactory(slug=kw.pop("slug", "sr5"), name="SR5", business_type="bakery", **kw)


def _user():
    return type("U", (), {"is_authenticated": True, "username": "o"})()


# --- слой подписей ------------------------------------------------------------


def test_hints_cheap_sources_and_failsafe():
    t = _tenant(enabled_locales=["de", "en", "ru"])
    hints = settings_hints.hints_for(t)
    assert "weitere" in hints["languages"]  # Deutsch + 2 weitere
    assert "Module" in hints["modules"]
    assert "E-Mail" in hints["notifications-settings"]
    # None-тенант и упавший источник не роняют слой
    assert settings_hints.hints_for(None) == {}


def test_hint_single_locale_and_payments():
    t = _tenant(enabled_locales=["de"])
    hints = settings_hints.hints_for(t)
    assert hints["languages"]  # «Nur Deutsch»
    assert hints["payment-settings"]  # хотя бы «Zahlung vor Ort»


# --- вариант А: подпись в подменю сайдбара ------------------------------------


def test_sidebar_settings_children_carry_hints():
    t = _tenant(enabled_locales=["de", "en"])
    nav = modules.sidebar_nav(t)
    settings_item = next(i for i in nav if i["nav_key"] == "settings")
    by_url = {c["url_name"]: c for c in settings_item["children"]}
    assert by_url["languages"]["hint"]
    # обзор — первым подпунктом (авто-вставка якоря)
    assert settings_item["children"][0]["url_name"] == "einstellungen-home"
    # у других разделов hint не появляется
    other = next(i for i in nav if i["nav_key"] == "sellables")
    assert all("hint" not in c or not c["hint"] for c in other["children"])


# --- вариант Б: страница-обзор ------------------------------------------------


def _get(tenant, user=None):
    req = RequestFactory().get("/dashboard/einstellungen/")
    req.tenant = tenant
    req.user = user or _user()
    return einstellungen_home(req)


def test_overview_renders_groups_with_hints():
    t = _tenant(enabled_locales=["de", "en"])
    body = _get(t).content.decode()
    assert "Geschäft" in body and "Verkauf" in body and "System" in body
    assert "/dashboard/settings/" in body  # Mein Geschäft
    assert "weitere" in body  # живая подпись Sprachen
    assert "Abläufe" in body


def test_overview_hides_owner_only_for_staff(monkeypatch):
    t = _tenant()
    owner_body = _get(t).content.decode()
    assert "/dashboard/billing/" in owner_body
    from apps.core import roles
    from apps.core.models import Membership

    monkeypatch.setattr(roles, "role_of", lambda u: Membership.ROLE_STAFF)
    staff_body = _get(t).content.decode()
    assert "/dashboard/billing/" not in staff_body
    assert "/dashboard/settings/" in staff_body  # обычные строки на месте
