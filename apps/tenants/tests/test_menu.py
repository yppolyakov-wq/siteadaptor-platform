"""S7: многоуровневое меню витрины — normalize схемы + резолв дерева."""

import pytest

from apps.tenants import menu, siteconfig
from apps.tenants.tests.factories import TenantFactory


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse storefront-* в резолвере


# --- normalize схемы меню ------------------------------------------------------


def test_legacy_config_derives_top_menu_from_nav():
    cfg = siteconfig.normalize({})  # легаси без menus
    top = cfg["menus"]["top"]
    assert top["style"] == "classic" and top["sticky"] is True
    types = {n["target"]: n["type"] for n in top["items"]}
    assert types["catalog"] == "archetype"
    assert types["home"] == "page"  # «offers» → home
    assert cfg["menus"]["bottom"]["enabled"] is False


def test_custom_menu_normalized_with_depth_and_type_guard():
    cfg = siteconfig.normalize(
        {
            "menus": {
                "top": {
                    "style": "centered",
                    "sticky": False,
                    "items": [
                        {
                            "label": "Speisekarte",
                            "type": "weird",  # неизвестный → url
                            "children": [
                                {"label": "Fastfood", "type": "category", "target": "ff"},
                                {"label": ""},  # без подписи → отброшен
                                {
                                    "label": "Tief",
                                    "children": [{"label": "Zu tief"}],  # глубина >2 → дети режутся
                                },
                            ],
                        },
                        {"type": "url", "target": "x"},  # без label → отброшен
                    ],
                },
                "bottom": {
                    "enabled": True,
                    "items": [{"label": "Korb", "type": "archetype", "target": "orders"}],
                },
            }
        }
    )
    top = cfg["menus"]["top"]
    assert top["style"] == "centered" and top["sticky"] is False
    assert len(top["items"]) == 1  # пункт без label выброшен
    parent = top["items"][0]
    assert parent["type"] == "url"  # неизвестный тип → url
    child_labels = [c["label"] for c in parent["children"]]
    assert child_labels == ["Fastfood", "Tief"]  # пустой выброшен
    deep = next(c for c in parent["children"] if c["label"] == "Tief")
    assert deep["children"] == []  # глубже 2 уровней не разбираем
    assert cfg["menus"]["bottom"]["enabled"] is True


# --- резолв ссылок -------------------------------------------------------------


def test_resolve_archetype_respects_module_gating():
    active = menu.resolve_menu(
        TenantFactory.build(
            site_config={
                "menus": {
                    "top": {
                        "items": [
                            {"label": "Tisch", "type": "archetype", "target": "booking"},
                        ]
                    }
                }
            }
        ),
        "top",
    )
    assert active and active[0]["url"]  # booking активен → ссылка есть

    gated = menu.resolve_menu(
        TenantFactory.build(
            disabled_modules=["booking"],
            site_config={
                "menus": {
                    "top": {
                        "items": [
                            {"label": "Tisch", "type": "archetype", "target": "booking"},
                        ]
                    }
                }
            },
        ),
        "top",
    )
    assert gated == []  # модуль выключен → пункт отброшен


def test_resolve_url_anchor_and_group():
    tenant = TenantFactory.build(
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "Extern", "type": "url", "target": "https://x.de"},
                        {"label": "Aktionen", "type": "anchor", "target": "aktionen"},
                        {
                            "label": "Mehr",
                            "type": "group",
                            "children": [
                                {"label": "Kontakt", "type": "url", "target": "/kontakt/"},
                            ],
                        },
                        {
                            "label": "Leer",
                            "type": "group",
                            "children": [
                                {
                                    "label": "Tot",
                                    "type": "archetype",
                                    "target": "loyalty",
                                },  # без landing → нет
                            ],
                        },
                    ]
                }
            }
        }
    )
    items = menu.resolve_menu(tenant, "top")
    by = {i["label"]: i for i in items}
    assert by["Extern"]["url"] == "https://x.de"
    assert by["Aktionen"]["url"] == "/#aktionen"
    assert by["Mehr"]["url"] is None and len(by["Mehr"]["children"]) == 1
    assert "Leer" not in by  # group без резолвимых детей отброшен


def test_disabled_node_dropped():
    items = menu.resolve_menu(
        TenantFactory.build(
            site_config={
                "menus": {
                    "top": {
                        "items": [
                            {"label": "Hidden", "type": "url", "target": "/x/", "enabled": False},
                        ]
                    }
                }
            }
        ),
        "top",
    )
    assert items == []


@pytest.mark.django_db
def test_resolve_category_requires_existing_category():
    from apps.catalog.models import Category

    tenant = TenantFactory(
        schema_name="public",
        slug="cm",
        name="CM",
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "Fastfood", "type": "category", "target": "fastfood"},
                    ]
                }
            }
        },
    )
    assert menu.resolve_menu(tenant, "top") == []  # категории нет → отброшен
    Category.objects.create(name="Fastfood", slug="fastfood", is_active=True)
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"] == "/sortiment/?kategorie=fastfood"
