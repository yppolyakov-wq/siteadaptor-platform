"""H2-7 (мультиархетип-меню): свежий сайт БЕЗ кастомного меню авто-строит верхнее меню
из активных архетипов (фолбэк _normalize_menus → nav). Кастомное меню (как у pranasy)
переопределяет. Подтверждает, что «категории в меню на архетип» работают из коробки."""

import pytest
from django.urls import reverse

from apps.tenants import menu as menu_mod
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_fresh_multiarchetype_auto_menu_includes_archetype_landings():
    # Сборный сайт: catalog (core) + events + booking активны, кастомного меню нет.
    tenant = TenantFactory(
        schema_name="public", slug="amenu", name="AMenu", disabled_modules=[], site_config={}
    )
    urls = {i["url"] for i in menu_mod.resolve_menu(tenant, "top")}
    # авто-меню ведёт на лендинги активных архетипов (магазин/события/запись)
    assert reverse("storefront-products") in urls  # catalog
    assert reverse("storefront-events") in urls  # events


def test_disabled_archetype_absent_from_auto_menu():
    tenant = TenantFactory(
        schema_name="public",
        slug="amenu2",
        name="AMenu2",
        disabled_modules=["events", "booking", "stays"],
        site_config={},
    )
    urls = {i["url"] for i in menu_mod.resolve_menu(tenant, "top")}
    assert reverse("storefront-events") not in urls  # events выключен → нет в меню
