"""Инвариант достижимости навигации (пост-программная сверка X0–X8, 2026-08-19).

Класс дефектов, который программа ловила стендом вручную: пункт ВИДЕН владельцу,
но ведёт в 404 — потому что модульный гейт мидлвари (`url_prefixes`) не совпадает
с гейтом показа (`module_key` записи реестра). Стенд-обход по семи демо-тенантам
подтвердил чистоту; здесь тот же инвариант закреплён в CI и на ВСЕХ типах бизнеса.

Проверяем ровно то, что видит владелец: якоря сайдбара, их подпункты и вкладки
хабов — каждая ссылка обязана резолвиться И проходить модульный гейт мидлвари.
"""

from uuid import uuid4

import pytest
from django.urls import reverse

from apps.core import modules, nav_registry
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BUSINESS_TYPES = [code for code, _label in Tenant.BUSINESS_TYPES]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type):
    return TenantFactory(
        slug=f"nr-{business_type[:8]}-{uuid4().hex[:4]}",
        name="NR",
        business_type=business_type,
        disabled_modules=modules.default_disabled_for(business_type),
    )


def _gate_ok(tenant, path: str) -> bool:
    """Пропустит ли путь модульный гейт мидлвари (CabinetModuleMiddleware)."""
    spec = modules.module_for_path(path)
    return spec is None or modules.is_module_active(tenant, spec.key)


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
def test_sidebar_entries_are_reachable(business_type):
    """Каждый видимый якорь и подпункт сайдбара резолвится и не заперт гейтом."""
    tenant = _tenant(business_type)
    for item in modules.sidebar_nav(tenant):
        path = reverse(item["url_name"])
        assert _gate_ok(tenant, path), f"{business_type}: якорь {item['url_name']} → 404 по гейту"
        for child in item["children"]:
            child_path = reverse(child["url_name"])
            assert _gate_ok(tenant, child_path), (
                f"{business_type}: подпункт {child['url_name']} виден, но заперт гейтом"
            )


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
def test_hub_tabs_are_reachable(business_type):
    """Вкладка хаба, прошедшая гейт показа (module_key), обязана пройти и гейт пути:
    иначе владелец видит вкладку, а на ней 404."""
    tenant = _tenant(business_type)
    for hub, entries in nav_registry.legacy_hub_tabs().items():
        for url_name, _label, _nav, module_key, _adv in entries:
            if module_key is not None and not modules.is_module_active(tenant, module_key):
                continue  # вкладка скрыта — гейт показа отработал
            if not nav_registry.allowed_for_business(url_name, tenant):
                continue  # X4: гастро-экраны у негастро скрыты
            path = reverse(url_name)
            assert _gate_ok(tenant, path), (
                f"{business_type}/{hub}: вкладка {url_name} видна, но заперта гейтом пути"
            )


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
def test_palette_entries_are_reachable(business_type):
    """То же для палитры Ctrl+K: показанная запись обязана открываться."""
    tenant = _tenant(business_type)
    for entry in nav_registry.palette_entries():
        mod = entry["module_key"]
        if mod is not None and not modules.is_module_active(tenant, mod):
            continue
        if not nav_registry.allowed_for_business(entry["url_name"], tenant):
            continue
        path = reverse(entry["url_name"])
        assert _gate_ok(tenant, path), (
            f"{business_type}: запись палитры {entry['url_name']} видна, но заперта гейтом"
        )


# --- ссылки ВНУТРИ страниц (не навигация) -------------------------------------


def test_order_detail_hides_customer_card_when_crm_off():
    """Пост-программная сверка (серверный обход 2026-08-19): «Kundenkarte öffnen»
    рисовалась всегда, а CRM выключен у большинства архетипов по умолчанию →
    клик давал 404 гейта путей. Ссылка обязана появляться только с модулем."""
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import services, views

    def _render(tenant):
        order = services.create_order(
            items=[(ProductFactory(name={"de": "Brot"}), 1)], name="Kunde", email="k@t.de"
        )
        req = RequestFactory().get(f"/dashboard/orders/{order.pk}/")
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.tenant = tenant
        req.user = get_user_model().objects.create_user(
            username=f"o-{uuid4().hex[:8]}",
            email=f"o-{uuid4().hex[:8]}@t.de",
            password="pw12345678",
        )
        return views.order_detail(req, pk=order.pk).content.decode()

    off = _tenant("retail")  # пресет ритейла: crm выключен
    assert not modules.is_module_active(off, "crm")
    assert "/crm/" not in _render(off)

    on = TenantFactory(
        slug=f"nr-crm-{uuid4().hex[:4]}",
        name="NRcrm",
        business_type="retail",
        disabled_modules=[m for m in modules.default_disabled_for("retail") if m != "crm"],
    )
    assert modules.is_module_active(on, "crm")
    assert "/crm/" in _render(on)
