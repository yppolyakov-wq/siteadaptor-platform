"""Волна L / L2 — кабинет «Sprachen»: включение языков витрины + дефолт.

Владелец включает подмножество языков реестра `settings.LANGUAGES` и выбирает
дефолт → пишется `Tenant.enabled_locales`/`default_locale`. Инварианты: минимум один
язык; дефолт ∈ включённые. UI генерик по реестру (N локалей).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LANG_PATH = "/dashboard/settings/languages/"


def _attach(request, user=None):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if user is not None:
        request.user = user
    return request


def _user():
    return get_user_model().objects.create_user(
        username="owner", email="owner@test.de", password="pw12345678"
    )


def _post(tenant, data):
    req = _attach(RequestFactory().post(LANG_PATH, data), _user())
    req.tenant = tenant
    return core_views.languages_view(req)


def test_languages_view_get_renders():
    tenant = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    req = _attach(RequestFactory().get(LANG_PATH), _user())
    req.tenant = tenant
    resp = core_views.languages_view(req)
    assert resp.status_code == 200
    assert b"Deutsch" in resp.content and b"English" in resp.content


def test_languages_view_saves_subset():
    tenant = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    resp = _post(tenant, {"locales": ["de"], "default_locale": "de"})
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de"]
    assert tenant.default_locale == "de"


def test_languages_view_saves_both_and_default_en():
    tenant = TenantFactory(enabled_locales=["de"], default_locale="de")
    resp = _post(tenant, {"locales": ["de", "en"], "default_locale": "en"})
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de", "en"]
    assert tenant.default_locale == "en"


def test_default_forced_into_enabled_when_not_selected():
    """Дефолт вне включённых → авто-коррекция на первый включённый (инвариант)."""
    tenant = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    resp = _post(tenant, {"locales": ["en"], "default_locale": "de"})  # de больше не включён
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["en"]
    assert tenant.default_locale == "en"


def test_empty_selection_rejected_no_save():
    tenant = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    resp = _post(tenant, {"locales": [], "default_locale": "de"})
    assert resp.status_code == 200  # ре-рендер, не редирект
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de", "en"]  # не тронуто


def test_unknown_locale_filtered_out():
    tenant = TenantFactory(enabled_locales=["de", "en"], default_locale="de")
    resp = _post(tenant, {"locales": ["de", "zz"], "default_locale": "de"})
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de"]  # zz не в реестре → выброшен


def test_enabled_order_follows_registry_not_post():
    """Порядок включённых — как в settings.LANGUAGES (стабильно), не как в POST."""
    tenant = TenantFactory(enabled_locales=["de"], default_locale="de")
    resp = _post(tenant, {"locales": ["en", "de"], "default_locale": "de"})
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de", "en"]
