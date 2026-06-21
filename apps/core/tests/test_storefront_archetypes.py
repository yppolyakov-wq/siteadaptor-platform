"""Тесты витринного слоя реестра модулей (S1).

`storefront_archetypes(tenant)` — источник правды для тизеров главной (S2) и
конструктора меню (S7): активные модули с публичной страницей, в порядке
реестра. Новый архетип подключается одной декларацией в реестре.
"""

from apps.core import modules
from apps.tenants.tests.factories import TenantFactory


def _tenant(**kwargs):
    return TenantFactory.build(**kwargs)


def _keys(tenant):
    return [a.key for a in modules.storefront_archetypes(tenant)]


def test_default_tenant_lists_archetypes_with_landing():
    keys = _keys(_tenant())
    # Архетипы с публичной страницей попадают в список…
    for expected in ("catalog", "orders", "booking", "stays", "events", "jobs", "loyalty"):
        assert expected in keys  # loyalty получил публичную /treue/ в S5
    # …а модули без публичной «главной» — нет.
    assert "promotions" not in keys  # инлайн на главной, своей страницы нет
    assert "analytics" not in keys  # чисто кабинетный
    assert "finance" not in keys


def test_disabled_module_drops_out():
    tenant = _tenant(disabled_modules=["booking", "events"])
    keys = _keys(tenant)
    assert "booking" not in keys
    assert "events" not in keys
    assert "catalog" in keys  # core — остаётся


def test_order_follows_registry():
    keys = _keys(_tenant())
    registry_order = [s.key for s in modules.REGISTRY if s.storefront_landing and s.key in keys]
    assert keys == registry_order


def test_presentation_fields_filled():
    by_key = {a.key: a for a in modules.storefront_archetypes(_tenant())}
    catalog = by_key["catalog"]
    assert catalog.label  # не пустой (фолбэк на label_de если не задан)
    assert catalog.url_name == "storefront-products"
    assert catalog.icon
    # teaser-флаг: catalog показывается в сетке, ЛК/контакт — нет.
    assert catalog.teaser is True
    assert by_key["inbox"].teaser is False
    assert by_key["customer_account"].teaser is False


def test_label_falls_back_to_label_de():
    # Гарантия инварианта: label непуст даже если storefront_label не задан.
    for arch in modules.storefront_archetypes(_tenant()):
        assert arch.label
