"""Матрица наследования стилей: архетип × кожа/сборка × ключевые страницы.

Зачем (аудит `docs/style-inheritance-audit-2026-09-03.md` §6.4): у платформы есть
замки на КОНФИГ (golden-паритет normalize, apply_look/apply_bundle по всем
архетипам), но не было ни одного замка на РЕНДЕР — «новый сайт этого типа
вообще открывается», «после смены Look'а витрина жива и кожа доехала до тела
страницы». Из-за этого пробела дефекты класса «ось не наследуется» находились
глазами на стенде, а не тестом.

Матрица дешёвая: чистый тенант каждого из 15 архетипов + рекомендованные ему
сборки и несколько семейств Look'а. Вьюхи зовём напрямую (RequestFactory) —
как в остальных тестах витрины; Http404 от гейта модуля это законный ответ и
отличается от падения рендера.

Дефекты, найденные аудитом и НЕ починенные (их чинит отдельный инкремент, здесь
они помечены xfail, чтобы починка стала видна как XPASS, а не потерялась):
§9.2 дефект 5 (`apply_look` затирает `site_defaults` целиком) и дефект 1
(демо/сборка без ключа `design` не включают CSS-слой Look'а).
"""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.http import Http404
from django.test import RequestFactory

from apps.core import modules as module_registry
from apps.promotions import public_views
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ARCHETYPES = [key for key, _label in Tenant.BUSINESS_TYPES if key != "other"]

# Страница витрины → (вьюха, модуль-гейт). Модуль None = страница есть всегда.
STOREFRONT_PAGES = (
    ("/", public_views.storefront_home, None),
    ("/sortiment/", public_views.product_list, "catalog"),
    ("/aktionen/", public_views.promotion_list, "promotions"),
)


def _fresh_tenant(business_type: str) -> Tenant:
    """Тенант ровно такой, каким его создаёт регистрация: site_config = {},
    набор модулей — пресет архетипа (services._new_tenant + apply_business_type)."""
    return TenantFactory(
        business_type=business_type,
        disabled_modules=module_registry.default_disabled_for(business_type),
        site_config={},
    )


def _render(tenant: Tenant, path: str, view):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request)


def _render_pages(tenant: Tenant) -> dict[str, str]:
    """Отрендерить ключевые страницы. Возвращает {путь: html} по доступным.

    Http404 принимаем ТОЛЬКО от страницы, чей модуль выключен пресетом архетипа —
    иначе это регрессия гейта, а не законный ответ.
    """
    out = {}
    for path, view, module_key in STOREFRONT_PAGES:
        try:
            response = _render(tenant, path, view)
        except Http404:
            active = module_key is not None and module_registry.is_module_active(tenant, module_key)
            assert not active, f"{path} отдал 404 при ВКЛЮЧЁННОМ модуле {module_key}"
            continue
        assert response.status_code == 200, f"{path} → {response.status_code}"
        out[path] = response.content.decode()
    return out


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_fresh_tenant_of_every_archetype_renders(business_type):
    """Новый сайт каждого архетипа открывается — без единого сохранения конфига.

    Дефолт витрины у нового тенанта целиком рантаймовый (`site_config = {}`,
    достраивает `normalize`), поэтому именно этот случай ломается тише всего.
    """
    tenant = _fresh_tenant(business_type)
    pages = _render_pages(tenant)
    assert "/" in pages, "главная обязана рендериться у любого архетипа"


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_every_look_renders_and_reaches_the_page_body(business_type):
    """После apply_look витрина жива, а кожа доехала до тела страницы.

    `data-sf-look` включает фирменный CSS-слой семейства (и замену indigo на
    акцент). Если ключ `design` не записан, витрина выглядит «наполовину
    применённой» — и заметить это можно только глазами. Теперь — тестом.
    """
    tenant = _fresh_tenant(business_type)
    for family in sitetemplates.looks_for(business_type):
        assert sitetemplates.apply_look(tenant, family["key"])
        pages = _render_pages(tenant)
        assert f'data-sf-look="{family["key"]}"' in pages["/"], (
            f"{business_type}/{family['key']}: кожа не доехала до body"
        )


@pytest.mark.parametrize("business_type", ARCHETYPES)
def test_recommended_bundles_render(business_type):
    """Сборки, предлагаемые архетипу в мастере и Studio, рендерятся.

    Сборка меняет композицию главной (порядок и состав секций, стиль баннера,
    страничные пресеты) — то есть ровно тот слой, который не покрыт
    конфиг-замками.
    """
    tenant = _fresh_tenant(business_type)
    for bundle in sitetemplates.bundles_for(business_type):
        assert sitetemplates.apply_bundle(tenant, bundle["key"])
        pages = _render_pages(tenant)
        assert pages["/"], f"{business_type}/{bundle['key']}: пустая главная"
        stored = siteconfig.normalize(tenant.site_config)
        assert stored["design"]["bundle"] == bundle["key"]


@pytest.mark.parametrize("business_type", ARCHETYPES[:5])
def test_apply_is_idempotent_at_render_level(business_type):
    """Повторное применение той же кожи не меняет разметку.

    Ловит «дрейф» — когда apply читает уже применённое состояние и накапливает
    изменения (порядок секций, дубли блоков страничного пресета).
    """
    tenant = _fresh_tenant(business_type)
    family = sitetemplates.looks_for(business_type)[0]["key"]
    sitetemplates.apply_look(tenant, family)
    first = _render_pages(tenant)["/"]
    sitetemplates.apply_look(tenant, family)
    assert _render_pages(tenant)["/"] == first


@pytest.mark.xfail(
    reason="Аудит §9.2 дефект 5: apply_look заменяет site_defaults целиком",
    strict=False,
)
def test_apply_look_keeps_owner_choices_in_site_defaults():
    """Смена кожи не должна стирать выбор владельца по другим осям.

    Look — это ВИЗУАЛЬНАЯ тема (шрифт, скругления, хром карточек). Шаблон
    страницы категории, форма карточки акции, вид выбора вариантов — отдельные
    оси, владелец задаёт их сам, и смена кожи их роняет.
    """
    tenant = _fresh_tenant("shop")
    config = siteconfig.normalize(tenant.site_config)
    config["site_defaults"] = {
        **config.get("site_defaults", {}),
        "category_page_style": "schaufenster",
        "variant_style": "swatches",
        "promo_card": "preis",
    }
    tenant.site_config = siteconfig.normalize(config)
    tenant.save(update_fields=["site_config"])

    sitetemplates.apply_look(tenant, "warm")

    kept = siteconfig.normalize(tenant.site_config)["site_defaults"]
    assert kept.get("category_page_style") == "schaufenster"
    assert kept.get("variant_style") == "swatches"
    assert kept.get("promo_card") == "preis"
