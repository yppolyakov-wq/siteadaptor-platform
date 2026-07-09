"""S5 (упрощение кабинета): режим «Простой/Эксперт» — хелперы, скрытие продвинутого,
сохранение ui_mode в normalize, тумблер на странице «Funktionen»."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core import modules
from apps.tenants.siteconfig import normalize


def _t(cfg=None, disabled=(), business_type=""):
    return SimpleNamespace(
        site_config=cfg or {},
        disabled_modules=list(disabled),
        enabled_modules=[],
        business_type=business_type,
    )


# --- хелперы режима ----------------------------------------------------------
def test_ui_mode_default_expert():
    assert modules.ui_mode(_t()) == "expert"
    assert modules.is_simple(_t()) is False


def test_ui_mode_simple_from_config():
    t = _t({"ui_mode": "simple"})
    assert modules.ui_mode(t) == "simple"
    assert modules.is_simple(t) is True


# --- скрытие продвинутого в Простом -----------------------------------------
def _module_keys(tenant):
    return {m.key for g in modules.grouped_active_modules(tenant) for m in g["modules"]}


def test_grouped_shows_advanced_in_expert():
    keys = _module_keys(_t())
    assert "finance" in keys and "analytics" in keys


def test_grouped_hides_advanced_in_simple():
    keys = _module_keys(_t({"ui_mode": "simple"}))
    assert "finance" not in keys
    assert "analytics" not in keys
    # неадвансовые остаются (напр. dashboard/catalog — core)
    assert "catalog" in keys


# --- S6b: скрытие нерелевантных хабов по архетипу в Простом ------------------
def test_simple_hides_catalog_for_service_archetype():
    # Friseur в Простом: Sortiment (catalog, core) скрыт — салон продаёт услуги, не товары.
    keys = _module_keys(_t({"ui_mode": "simple"}, business_type="friseur"))
    assert "catalog" not in keys
    assert "dashboard" in keys and "settings" in keys  # прочие core живы


def test_expert_keeps_catalog_for_service_archetype():
    # В Эксперт-режиме архетип-скрытие не действует (всё видно).
    keys = _module_keys(_t(business_type="friseur"))
    assert "catalog" in keys


def test_simple_keeps_catalog_for_werkstatt():
    # Werkstatt продаёт Teile → catalog остаётся даже в Простом.
    keys = _module_keys(_t({"ui_mode": "simple"}, business_type="werkstatt"))
    assert "catalog" in keys


def test_simple_hidden_modules_helper():
    assert modules.simple_hidden_modules(_t(business_type="friseur")) == frozenset()  # expert
    simple_friseur = modules.simple_hidden_modules(
        _t({"ui_mode": "simple"}, business_type="friseur")
    )
    assert {"finance", "analytics", "catalog"} <= simple_friseur
    # тип без записи — только универсальные продвинутые
    assert modules.simple_hidden_modules(
        _t({"ui_mode": "simple"}, business_type="bakery")
    ) == frozenset({"finance", "analytics"})


# --- сохранение ui_mode при нормализации (иначе билдер сотрёт) ---------------
def test_normalize_keeps_ui_mode_simple():
    assert normalize({"ui_mode": "simple"}).get("ui_mode") == "simple"


def test_normalize_drops_ui_mode_expert_and_absent():
    assert "ui_mode" not in normalize({"ui_mode": "expert"})
    assert "ui_mode" not in normalize({})


# --- тумблер на странице «Funktionen» ---------------------------------------
def _req(rf, user, tenant, data):
    request = rf.post("/dashboard/modules/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


@pytest.mark.django_db
def test_modules_toggle_sets_and_clears_ui_mode(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import modules_view
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="t_ui", name="UI Co", site_config={"notify": {"x": 1}})
    user = get_user_model().objects.create_user("u", "u@test.de", "pw12345678")

    # → simple
    modules_view(_req(rf, user, tenant, {"ui_mode": "simple"}))
    tenant.refresh_from_db()
    assert tenant.site_config.get("ui_mode") == "simple"
    assert tenant.site_config.get("notify") == {"x": 1}  # прочие ключи целы

    # → expert (ключ убран)
    modules_view(_req(rf, user, tenant, {"ui_mode": "expert"}))
    tenant.refresh_from_db()
    assert "ui_mode" not in tenant.site_config
    assert tenant.site_config.get("notify") == {"x": 1}
