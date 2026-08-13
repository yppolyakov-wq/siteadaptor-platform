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
                                    "target": "analytics",
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


# --- MEN-15: авто-подменю категорий с картинками -------------------------------


def _menu_with_categories(target: str = "", **cfg):
    return {
        "menus": {
            "top": {"items": [{"label": "Speisekarte", "type": "categories", "target": target}]}
        },
        **cfg,
    }


def test_categories_node_survives_normalize():
    cfg = siteconfig.normalize(_menu_with_categories())
    node = cfg["menus"]["top"]["items"][0]
    assert node["type"] == "categories" and node["children"] == []


@pytest.mark.django_db
def test_categories_node_builds_children_from_live_catalog():
    from apps.catalog.models import Category

    tenant = TenantFactory(
        schema_name="public", slug="mc", name="MC", site_config=_menu_with_categories()
    )
    # категорий нет — но сам пункт ведёт в каталог, поэтому остаётся
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"] == "/sortiment/" and items[0]["children"] == []

    Category.objects.create(name={"de": "Buffets"}, slug="mc-buffets", sort_order=1)
    Category.objects.create(name={"de": "Getränke"}, slug="mc-drinks", sort_order=2)
    Category.objects.create(name={"de": "Aus"}, slug="mc-off", is_active=False)
    tenant._menu_categories_memo = None  # мемо живёт на объекте запроса
    kids = menu.resolve_menu(tenant, "top")[0]["children"]
    assert [k["label"] for k in kids] == ["Buffets", "Getränke"]  # выключенной нет
    assert kids[0]["url"] == "/sortiment/?kategorie=mc-buffets"


@pytest.mark.django_db
def test_categories_children_are_one_query_and_memoized():
    """Риск №1 плана MEN-15: меню резолвится на каждый рендер (шапка, нижнее
    меню, контекст кабинета) — построение детей обязано быть однозапросным."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.catalog.models import Category

    for i in range(5):
        Category.objects.create(name={"de": f"Kat {i}"}, slug=f"q-kat-{i}", sort_order=i)
    tenant = TenantFactory(
        schema_name="public", slug="mq", name="MQ", site_config=_menu_with_categories()
    )
    with CaptureQueriesContext(connection) as ctx:
        menu.resolve_menu(tenant, "top")
    assert len(ctx.captured_queries) == 1, [q["sql"] for q in ctx.captured_queries]
    with CaptureQueriesContext(connection) as ctx2:
        menu.resolve_menu(tenant, "top")  # второй рендер — из мемо
    assert ctx2.captured_queries == []


@pytest.mark.django_db
def test_categories_children_follow_landing_setting_like_tiles():
    """Ссылка в меню обязана совпадать с плиткой категории (_category_tile.html):
    до MEN-15 меню всегда вело на фильтр, а плитка — на лендинг направления."""
    from apps.catalog.models import Category

    Category.objects.create(
        name={"de": "Hochzeit"},
        description={"de": "Für den großen Tag"},  # landing_ready
        slug="ml-wedding",
    )
    tenant = TenantFactory(
        schema_name="public",
        slug="ml",
        name="ML",
        site_config=_menu_with_categories(category_landings=True),
    )
    kids = menu.resolve_menu(tenant, "top")[0]["children"]
    assert kids[0]["url"] == "/bereich/ml-wedding/"

    tenant.site_config = _menu_with_categories()  # тумблер выключен
    tenant._menu_categories_memo = None
    kids = menu.resolve_menu(tenant, "top")[0]["children"]
    assert kids[0]["url"] == "/sortiment/?kategorie=ml-wedding"


@pytest.mark.django_db
def test_categories_panel_uses_photos_only_when_they_exist():
    """Фолбэк обязателен: у большинства тенантов Category.images пуст — без
    флага панель выродилась бы в серые прямоугольники."""
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Buffets"}, slug="mp-buffets")
    tenant = TenantFactory(
        schema_name="public", slug="mp", name="MP", site_config=_menu_with_categories()
    )
    assert menu.resolve_menu(tenant, "top")[0]["has_images"] is False

    cat.images = [{"id": "i1", "url": "/media/buffet.jpg", "is_primary": True}]
    cat.save(update_fields=["images"])
    tenant._menu_categories_memo = None
    item = menu.resolve_menu(tenant, "top")[0]
    assert item["has_images"] is True
    assert item["children"][0]["image"] == "/media/buffet.jpg"


@pytest.mark.django_db
def test_categories_node_can_show_subcategories_of_one_parent():
    from apps.catalog.models import Category

    parent = Category.objects.create(name={"de": "Essen"}, slug="ms-food")
    Category.objects.create(name={"de": "Suppen"}, slug="ms-soups", parent=parent)
    Category.objects.create(name={"de": "Getränke"}, slug="ms-drinks")  # корневая
    tenant = TenantFactory(
        schema_name="public",
        slug="ms",
        name="MS",
        site_config=_menu_with_categories(target="ms-food"),
    )
    kids = menu.resolve_menu(tenant, "top")[0]["children"]
    assert [k["label"] for k in kids] == ["Suppen"]
