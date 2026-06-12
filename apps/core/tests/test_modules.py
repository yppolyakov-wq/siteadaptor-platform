"""Тесты реестра модулей, навигации и гейтинга (Track D / D0a).

Формула: Активно = (entitlement ∩ реестр) − disabled; core — всегда активны;
зависимости (loyalty/analytics → promotions) — рекурсивно; путь кабинета
матчится на модуль по самому длинному префиксу.
"""

import pytest
from django.http import Http404, HttpResponse
from django.test import RequestFactory

from apps.core import modules
from apps.core.context import modules_nav
from apps.core.middleware import ModuleGatingMiddleware
from apps.tenants.tests.factories import TenantFactory


def _tenant(**kwargs):
    return TenantFactory.build(**kwargs)


# --- формула активности -----------------------------------------------------


def test_all_modules_active_by_default():
    tenant = _tenant()
    assert [s.key for s in modules.active_modules(tenant)] == [s.key for s in modules.REGISTRY]


def test_disabled_module_is_inactive():
    tenant = _tenant(disabled_modules=["crm"])
    assert not modules.is_module_active(tenant, "crm")
    assert modules.is_module_active(tenant, "promotions")


def test_core_modules_cannot_be_disabled():
    tenant = _tenant(disabled_modules=["catalog", "settings", "billing", "dashboard"])
    for key in ("catalog", "settings", "billing", "dashboard"):
        assert modules.is_module_active(tenant, key)


def test_unknown_module_is_inactive():
    assert not modules.is_module_active(_tenant(), "warehouse")


def test_depends_on_promotions():
    tenant = _tenant(disabled_modules=["promotions"])
    assert not modules.is_module_active(tenant, "loyalty")
    assert not modules.is_module_active(tenant, "analytics")
    # Обратно: loyalty выключен сам по себе — promotions живёт.
    tenant2 = _tenant(disabled_modules=["loyalty"])
    assert modules.is_module_active(tenant2, "promotions")
    assert not modules.is_module_active(tenant2, "loyalty")


def test_entitlement_applies_only_to_premium():
    spec = modules.ModuleSpec(
        key="warehouse", label_de="Lager", icon="", nav_items=(), url_prefixes=(), premium=True
    )
    free = modules.ModuleSpec(
        key="freebie", label_de="Frei", icon="", nav_items=(), url_prefixes=()
    )
    tenant = _tenant(enabled_modules=["catalog", "promotions", "publishing"])
    assert not modules.is_entitled(tenant, spec)  # premium без тарифа — нет
    assert modules.is_entitled(tenant, free)  # не-premium — всегда
    tenant_paid = _tenant(enabled_modules=["warehouse"])
    assert modules.is_entitled(tenant_paid, spec)


# --- матчинг путей (самый длинный префикс) ----------------------------------


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("/promotions/", "promotions"),
        ("/promotions/reservations/", "promotions"),
        ("/promotions/vouchers/", "loyalty"),
        ("/promotions/loyalty/", "loyalty"),
        ("/promotions/analytics/", "analytics"),
        ("/dashboard/", "dashboard"),
        ("/dashboard/channels/", "publishing"),
        ("/dashboard/billing/checkout/", "billing"),
        ("/dashboard/settings/", "settings"),
        ("/crm/", "crm"),
        ("/imports/", "catalog"),
    ],
)
def test_module_for_path_longest_prefix(path, key):
    spec = modules.module_for_path(path)
    assert spec is not None and spec.key == key


def test_module_for_path_skips_storefront():
    for path in ("/", "/sortiment/", "/p/abc/", "/accounts/login/", "/health/"):
        assert modules.module_for_path(path) is None


# --- context processor навигации --------------------------------------------


def _request(tenant):
    request = RequestFactory().get("/dashboard/")
    request.tenant = tenant
    return request


def test_nav_hides_disabled_modules():
    nav = modules_nav(_request(_tenant(disabled_modules=["crm", "publishing"])))
    keys = [s.key for s in nav["nav_modules"]]
    assert "crm" not in keys and "publishing" not in keys
    assert {"dashboard", "catalog", "promotions", "settings", "billing"} <= set(keys)


def test_nav_empty_on_public_schema():
    public = _tenant()
    public.schema_name = "public"
    assert modules_nav(_request(public)) == {}
    request = RequestFactory().get("/")
    assert modules_nav(request) == {}  # без tenant вовсе


# --- middleware --------------------------------------------------------------


def _mw_response(tenant, path):
    middleware = ModuleGatingMiddleware(lambda request: HttpResponse("ok"))
    request = RequestFactory().get(path)
    request.tenant = tenant
    return middleware(request)


def test_gating_404_for_disabled_module():
    tenant = _tenant(disabled_modules=["crm"])
    with pytest.raises(Http404):
        _mw_response(tenant, "/crm/")
    assert _mw_response(tenant, "/promotions/").status_code == 200


def test_gating_longest_prefix_inside_promotions():
    tenant = _tenant(disabled_modules=["loyalty"])
    with pytest.raises(Http404):
        _mw_response(tenant, "/promotions/vouchers/")
    assert _mw_response(tenant, "/promotions/").status_code == 200


def test_gating_never_blocks_core_or_unmatched():
    tenant = _tenant(disabled_modules=["catalog", "billing"])
    assert _mw_response(tenant, "/catalog/").status_code == 200
    assert _mw_response(tenant, "/dashboard/billing/").status_code == 200
    assert _mw_response(tenant, "/sortiment/").status_code == 200  # витрина вне реестра


def test_gating_skips_public_schema():
    public = _tenant(disabled_modules=["crm"])
    public.schema_name = "public"
    assert _mw_response(public, "/crm/").status_code == 200
