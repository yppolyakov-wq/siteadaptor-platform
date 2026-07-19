"""Страховка редизайна (владелец 2026-07-18): тумблер «Klassische Ansicht».

Пер-тенантный флаг site_config["classic_ui"] (паттерн ui_mode S5): True — прежний
интерфейс там, где вышел новый (сегодня: главная кабинета без плиток/канбана AB7);
каждый ST-инкремент обязан уважать флаг. Normalize сохраняет ключ (только при True)."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import modules
from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Мастер тронут → dashboard не редиректит в setup (AB5).
_TOUCHED = {"v": 2, "step": "language", "done": ["start"], "skipped": [], "completed": False}


def _req(method="get", data=None, tenant=None, path="/dashboard/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    o = uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return request


def test_normalize_preserves_classic_ui_only_when_true():
    assert siteconfig.normalize({"classic_ui": True})["classic_ui"] is True
    assert "classic_ui" not in siteconfig.normalize({"classic_ui": False})
    assert "classic_ui" not in siteconfig.normalize({})


def test_toggle_endpoint_sets_and_clears_flag():
    tenant = TenantFactory(schema_name="public", slug="cls", name="Cls", business_type="bakery")
    resp = core_views.set_classic_ui_view(
        _req("post", {"classic_ui": "1"}, tenant, path="/dashboard/classic-ui/")
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert modules.classic_ui(tenant) is True

    core_views.set_classic_ui_view(_req("post", {}, tenant, path="/dashboard/classic-ui/"))
    tenant.refresh_from_db()
    assert modules.classic_ui(tenant) is False
    assert "classic_ui" not in tenant.site_config


def test_dashboard_classic_hides_tiles_and_kanban():
    tenant = TenantFactory(
        schema_name="public",
        slug="clsd",
        name="ClsD",
        business_type="bakery",
        site_config={"onboarding": dict(_TOUCHED), "classic_ui": True},
    )
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Klassische Ansicht ist aktiv" in html
    assert "kanban" not in html.lower()  # AB7-доска скрыта
    assert 'href="/dashboard/board/"' in html  # быстрые ссылки классического вида


def test_dashboard_new_view_keeps_tiles():
    tenant = TenantFactory(
        schema_name="public",
        slug="clsn",
        name="ClsN",
        business_type="bakery",
        site_config={"onboarding": dict(_TOUCHED)},
    )
    html = core_views.dashboard(_req(tenant=tenant)).content.decode()
    assert "Klassische Ansicht ist aktiv" not in html
    # AB7-плитки на месте (хоть одна плитка задач рендерится).
    assert "Nicht ausgefüllt" in html or "tile" in html.lower() or "🏠" in html
