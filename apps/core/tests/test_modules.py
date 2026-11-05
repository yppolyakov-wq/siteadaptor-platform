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
    # W-CL: nav_modules/nav_groups снесены — гейт по модулям проверяем на якорях
    # компакт-сайдбара. X0 (cabinet-cleanup-2026-08-19, осознанная переписка):
    # без promotions якорь Marketing ОСТАЁТСЯ, пока жив любой модуль его хаба
    # (inbox/reviews/…) — прежний гейт отбирал у отеля вход к сообщениям.
    # Полное скрытие требует выключить ВСЕ модули хаба.
    nav = modules_nav(_request(_tenant(disabled_modules=["promotions"])))
    urls = [it["url_name"] for it in nav["nav_compact"]]
    assert "marketing-home" in urls
    all_marketing = [
        "promotions",
        "reviews",
        "crm",
        "loyalty",
        "inbox",
        "telegram",
        "publishing",
        "blog",
    ]
    nav2 = modules_nav(_request(_tenant(disabled_modules=all_marketing)))
    urls2 = [it["url_name"] for it in nav2["nav_compact"]]
    assert "marketing-home" not in urls2
    assert "dashboard" in urls2 and "einstellungen-home" in urls2


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
        # jobs — primary только для handwerker/werkstatt (S6); у остальных вертикалей выкл.
        (
            "bakery",
            {
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
            # GK-1: кейтеринг — jobs-primary; promotions/crm вкл, продажи-движки выкл.
            "catering",
            {
                "orders",
                "booking",
                "stays",
                "events",
                "loyalty",
                "analytics",
                "publishing",
                "finance",
                "telegram",
            },
        ),
        (
            "restaurant",
            {
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
                "customer_account",
            },
        ),
        # S6: реальные архетипы. Primary-модуль вертикали НЕ выключен по умолчанию.
        # friseur: booking (Termin) primary; loyalty/promotions вкл.
        (
            "friseur",
            {
                "orders",
                "stays",
                "analytics",
                "publishing",
                "jobs",
                "events",
                "finance",
                "telegram",
            },
        ),
        # handwerker: jobs (Angebote) primary; booking/promotions выкл (suited, не rec).
        (
            "handwerker",
            {
                "promotions",
                "orders",
                "booking",
                "stays",
                "loyalty",
                "analytics",
                "publishing",
                "events",
                "finance",
                "telegram",
            },
        ),
        # werkstatt: jobs + booking (Termin) primary.
        (
            "werkstatt",
            {
                "promotions",
                "orders",
                "stays",
                "loyalty",
                "analytics",
                "publishing",
                "events",
                "finance",
                "telegram",
            },
        ),
        # events (Veranstalter): events (Tickets) primary; promotions вкл; jobs выкл.
        (
            "events",
            {
                "orders",
                "booking",
                "stays",
                "loyalty",
                "analytics",
                "publishing",
                "jobs",
                "finance",
                "telegram",
            },
        ),
    ],
)
def test_default_disabled_for_vertical(business_type, disabled):
    # KA-12 E8.7 (решение владельца): блог выключен из коробки у всех типов;
    # E8.11: отелю запись по времени не включается (спа/прокат — по выбору).
    expected = set(disabled) | {"blog"}
    if business_type == "hotel":
        expected |= {"booking"}
    assert set(modules.default_disabled_for(business_type)) == expected


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
        """AIS-M M-1c (переписан осознанно): выключенный базовый модуль — в блоке
        «Ausgeschaltete Grundfunktionen», дополнения — тумблерами; core не показан."""
        settings.ROOT_URLCONF = "config.urls_tenant"
        from apps.core.views import modules_view

        tenant = TenantFactory(disabled_modules=["crm"])
        html = modules_view(self._request(tenant)).content.decode()
        assert "Kunden (CRM)" in html and "Stempelkarten" in html
        assert 'data-module="catalog"' not in html

    def test_get_shows_task_sections(self, settings):
        """AIS-M M-1c: язык задач — «Ihre Richtungen» / «Zusatzfunktionen» (было AB2)."""
        settings.ROOT_URLCONF = "config.urls_tenant"
        from apps.core.views import modules_view

        html = modules_view(self._request(TenantFactory())).content.decode()
        assert "Ihre Richtungen" in html and "Zusatzfunktionen" in html
        # POST-протокол (одна карточка — один ключ) — apps/core/tests/test_m1_screen.py.


# --- гибрид: suited_for + предупреждение (решение владельца 2026-06-12) -------


def test_is_suited_for_union_and_universal():
    booking = modules.get_module("booking")
    assert modules.is_suited_for(booking, "cafe")  # пресет
    assert modules.is_suited_for(booking, "retail")  # suited_for (Beratungstermin)
    assert not modules.is_suited_for(booking, "bakery")  # неподходящий
    analytics = modules.get_module("analytics")
    assert modules.is_suited_for(analytics, "bakery")  # универсальный


def test_suited_label_lists_and_universal():
    from apps.tenants.models import Tenant

    label = modules.suited_label(modules.get_module("booking"))
    # I18N-1: метки типов бизнеса переведены — сверяемся с реестром.
    assert label.startswith("Geeignet für:")
    assert str(dict(Tenant.BUSINESS_TYPES)["cafe"]) in label
    # promotions: пресет(8) + suited(2) = все типы → универсальная подпись
    assert modules.suited_label(modules.get_module("promotions")) == "Für alle Geschäftstypen"
    assert modules.suited_label(modules.get_module("analytics")) == "Für alle Geschäftstypen"


def test_default_disabled_unchanged_by_suited_for():
    # suited_for НЕ влияет на пресет: у пекарни booking по-прежнему выключен.
    assert "booking" in modules.default_disabled_for("bakery")
    assert "booking" not in modules.default_disabled_for("cafe")


# AIS-M M-1c: предупреждение «untypisch» снято — чужие модули больше не показываются
# списком; неподходящее направление добавляется осознанно карточкой «Weitere Richtung».
