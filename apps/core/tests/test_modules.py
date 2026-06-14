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
        ("/dashboard/stays/", "stays"),
        ("/dashboard/stays/units/", "stays"),
        ("/dashboard/auftraege/", "jobs"),
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


# --- D0b: дефолты по вертикали + страница «Module» ---------------------------


@pytest.mark.parametrize(
    ("business_type", "disabled"),
    [
        # jobs — universal opt-in (recommended_for=()) → disabled у всех вертикалей.
        (
            "bakery",
            {
                "crm",
                "booking",
                "stays",
                "jobs",
                "analytics",
                "publishing",
                "finance",
                "telegram",
                "events",
            },
        ),
        (
            "restaurant",
            {
                "crm",
                "orders",
                "stays",
                "jobs",
                "analytics",
                "publishing",
                "finance",
                "telegram",
                "events",
            },
        ),
        (
            "retail",
            {
                "crm",
                "booking",
                "stays",
                "jobs",
                "loyalty",
                "analytics",
                "publishing",
                "finance",
                "telegram",
                "events",
            },
        ),
        # hotel: stays рекомендован вертикали → НЕ в дефолтном disabled (jobs — да).
        (
            "hotel",
            {
                "promotions",
                "orders",
                "jobs",
                "loyalty",
                "analytics",
                "publishing",
                "finance",
                "telegram",
                "events",
            },
        ),
        (
            "other",
            {
                "crm",
                "orders",
                "booking",
                "stays",
                "jobs",
                "loyalty",
                "analytics",
                "publishing",
                "finance",
                "telegram",
                "events",
            },
        ),
    ],
)
def test_default_disabled_for_vertical(business_type, disabled):
    assert set(modules.default_disabled_for(business_type)) == disabled


def test_default_disabled_never_touches_core():
    for business_type, _label in [("bakery", ""), ("hotel", ""), ("other", "")]:
        core = {s.key for s in modules.REGISTRY if s.core}
        assert core.isdisjoint(modules.default_disabled_for(business_type))


@pytest.mark.django_db
class TestModulesView:
    def _request(self, tenant, method="get", data=None):
        from django.contrib.auth import get_user_model
        from django.contrib.messages.middleware import MessageMiddleware
        from django.contrib.sessions.middleware import SessionMiddleware

        request = getattr(RequestFactory(), method)("/dashboard/modules/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        import uuid

        request.tenant = tenant
        owner = uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
        )
        return request

    def test_get_lists_registry_with_states(self, settings):
        settings.ROOT_URLCONF = "config.urls_tenant"
        from apps.core.views import modules_view

        tenant = TenantFactory(disabled_modules=["crm"])
        response = modules_view(self._request(tenant))
        html = response.content.decode()
        assert "Kunden (CRM)" in html and "Stempelkarten" in html
        # Core-чекбокс задизейблен, выключенный crm — без checked.
        assert html.count("disabled") >= 4

    def test_post_writes_disabled_modules(self, settings):
        settings.ROOT_URLCONF = "config.urls_tenant"
        from apps.core.views import modules_view

        tenant = TenantFactory(disabled_modules=["crm"])
        # Владелец оставил только promotions и loyalty.
        response = modules_view(
            self._request(tenant, "post", {"modules": ["promotions", "loyalty"]})
        )
        assert response.status_code == 302
        tenant.refresh_from_db()
        assert set(tenant.disabled_modules) == {
            "crm",
            "orders",
            "booking",
            "stays",
            "jobs",
            "analytics",
            "publishing",
            "finance",
            "inbox",
            "telegram",
            "events",
        }
        # Core нельзя выключить отсутствием галки, мусорный ключ игнорируется.
        response = modules_view(self._request(tenant, "post", {"modules": ["warehouse"]}))
        tenant.refresh_from_db()
        assert set(tenant.disabled_modules) == {
            "promotions",
            "crm",
            "orders",
            "booking",
            "stays",
            "jobs",
            "loyalty",
            "analytics",
            "publishing",
            "finance",
            "inbox",
            "telegram",
            "events",
        }
        assert modules.is_module_active(tenant, "catalog")  # core живёт


# --- гибрид: suited_for + предупреждение (решение владельца 2026-06-12) -------


def test_is_suited_for_union_and_universal():
    booking = modules.get_module("booking")
    assert modules.is_suited_for(booking, "cafe")  # пресет
    assert modules.is_suited_for(booking, "retail")  # suited_for (Beratungstermin)
    assert not modules.is_suited_for(booking, "bakery")  # неподходящий
    analytics = modules.get_module("analytics")
    assert modules.is_suited_for(analytics, "bakery")  # универсальный


def test_suited_label_lists_and_universal():
    label = modules.suited_label(modules.get_module("booking"))
    assert label.startswith("Geeignet für:") and "Cafe" in label
    # promotions: пресет(8) + suited(2) = все типы → универсальная подпись
    assert modules.suited_label(modules.get_module("promotions")) == "Für alle Geschäftstypen"
    assert modules.suited_label(modules.get_module("analytics")) == "Für alle Geschäftstypen"


def test_default_disabled_unchanged_by_suited_for():
    # suited_for НЕ влияет на пресет: у пекарни booking по-прежнему выключен.
    assert "booking" in modules.default_disabled_for("bakery")
    assert "booking" not in modules.default_disabled_for("cafe")


@pytest.mark.django_db
def test_modules_view_warns_on_untypical_enable(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages import get_messages
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core.views import modules_view

    def _request(tenant, data):
        request = RequestFactory().post("/dashboard/modules/", data)
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.tenant = tenant
        owner = _uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw")
        return request

    # Пекарня включает Booking (untypical) — сохраняется, но с предупреждением.
    tenant = TenantFactory(business_type="bakery", disabled_modules=["booking"])
    request = _request(
        tenant,
        {
            "modules": [
                "promotions",
                "crm",
                "orders",
                "booking",
                "loyalty",
                "analytics",
                "publishing",
            ]
        },
    )
    modules_view(request)
    tenant.refresh_from_db()
    assert "booking" not in tenant.disabled_modules
    texts = [str(m) for m in get_messages(request)]
    assert any("Booking" in t and "untypical" in t.lower() for t in texts)

    # GET: untypical-блок ушёл в other_rows с подписью «Geeignet für…»
    get_request = RequestFactory().get("/dashboard/modules/")
    SessionMiddleware(lambda r: None).process_request(get_request)
    MessageMiddleware(lambda r: None).process_request(get_request)
    get_request.tenant = tenant
    get_request.user = request.user
    body = modules_view(get_request).content.decode()
    assert "Weitere Bausteine" in body and "Geeignet für:" in body
