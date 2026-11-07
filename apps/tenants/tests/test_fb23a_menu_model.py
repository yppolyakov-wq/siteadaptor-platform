"""FB-23a: меню сайта — 3 уровня, фото/подпись/авто-подкатегории/вид панели, цели на
конкретные записи, переводы всех языков, колонки подвала. Всё presence-minimal."""

import pytest

from apps.tenants import menu, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _top(*items, **extra):
    return {"menus": {"top": {"items": list(items)}, **extra}}


def _norm(cfg):
    return siteconfig.normalize(cfg)["menus"]


def test_new_node_fields_are_presence_minimal():
    top = _norm(_top({"label": "Brot", "type": "page", "target": "home"}))["top"]["items"][0]
    assert set(top) == {"label", "type", "target", "enabled", "icon", "children"}
    rich = _norm(
        _top(
            {
                "label": "Brot",
                "type": "category",
                "target": "brot",
                "auto": True,
                "layout": "mega",
                "image": "/media/brot.webp",
                "desc": "Frisch aus dem Ofen",
                "label_i18n": {"ru": "Хлеб", "xx": "?"},
                "children": [{"label": "Kind", "type": "page", "target": "home", "layout": "mega"}],
            }
        )
    )["top"]["items"][0]
    assert rich["auto"] is True and rich["layout"] == "mega"
    assert rich["image"] == "/media/brot.webp" and rich["desc"] == "Frisch aus dem Ofen"
    assert rich["label_i18n"] == {"ru": "Хлеб"}  # все языки сайта, мусорный код — нет
    assert "layout" not in rich["children"][0]  # вид панели — только у верхнего уровня


def test_unsafe_links_never_reach_the_header():
    cfg = _top(
        {"label": "X", "type": "url", "target": "javascript:alert(1)"},
        {"label": "Y", "type": "url", "target": "//evil.example"},
        {"label": "Z", "type": "url", "target": "https://example.org"},
        {"label": "P", "type": "page", "target": "home", "image": "data:image/png;base64,AA"},
    )
    items = _norm(cfg)["top"]["items"]
    assert [i["target"] for i in items[:3]] == ["", "", "https://example.org"]
    assert "image" not in items[3]
    resolved = menu.resolve_menu(TenantFactory.build(site_config=cfg), "top")
    assert [r["label"] for r in resolved if r["label"] in "XYZ"] == ["Z"]


def test_layout_default_matches_old_behaviour():
    tenant = TenantFactory.build(
        site_config=_top({"label": "Start", "type": "page", "target": "home"})
    )
    assert menu.resolve_menu(tenant, "top")[0]["layout"] == "list"


def test_category_with_auto_children_and_mega_third_level():
    from apps.catalog.models import Category

    root = Category.objects.create(name={"de": "Backwaren"}, slug="fb-back", sort_order=1)
    brot = Category.objects.create(name={"de": "Brot"}, slug="fb-brot", parent=root, sort_order=1)
    Category.objects.create(name={"de": "Roggen"}, slug="fb-roggen", parent=brot)
    cfg = _top(
        {"label": "Backwaren", "type": "category", "target": "fb-back", "auto": True},
        {"label": "Alles", "type": "categories", "target": "", "layout": "mega"},
    )
    tenant = TenantFactory(schema_name="public", slug="fb23a", name="FB", site_config=cfg)
    back, alles = menu.resolve_menu(tenant, "top")
    assert [c["label"] for c in back["children"]] == ["Brot"]
    assert back["children"][0]["children"] == []  # 3-й уровень — только для mega/columns
    level2 = next(c for c in alles["children"] if c["label"] == "Backwaren")
    assert [c["label"] for c in level2["children"]] == ["Brot"]
    assert alles["layout"] == "mega"


def test_entity_targets_link_only_to_visible_records():
    from apps.catalog.models import Product

    live = Product.objects.create(name={"de": "Brezel"}, base_price="1.00", is_active=True)
    hidden = Product.objects.create(name={"de": "Alt"}, base_price="1.00", is_active=False)
    cfg = _top(
        {"label": "Brezel", "type": "product", "target": str(live.pk)},
        {"label": "Alt", "type": "product", "target": str(hidden.pk)},
        {"label": "Kaputt", "type": "product", "target": "kein-uuid"},
    )
    tenant = TenantFactory(schema_name="public", slug="fb23b", name="FB", site_config=cfg)
    items = menu.resolve_menu(tenant, "top")
    assert [i["label"] for i in items] == ["Brezel"]
    assert items[0]["url"] == live.get_absolute_url()
    options = menu.target_options(tenant)
    assert any(o["value"] == f"product:{live.pk}" for o in options)
    assert not any(o["value"] == f"product:{hidden.pk}" for o in options)


def test_footer_columns_presence_minimal_and_resolved():
    assert "footer" not in _norm({})
    assert "footer" not in _norm(_top(footer={"columns": [{"label": "", "items": []}]}))
    cfg = _top(
        footer={
            "columns": [
                {
                    "label": "Service",
                    "label_i18n": {"en": "Service"},
                    "items": [
                        {"label": "Kontakt", "type": "page", "target": "contact"},
                        {"label": "Böse", "type": "url", "target": "javascript:x"},
                        {
                            "label": "Tief",
                            "type": "page",
                            "target": "home",
                            "children": [{"label": "x"}],
                        },
                    ],
                },
                "kaputt",
            ]
        }
    )
    cols = _norm(cfg)["footer"]["columns"]
    assert len(cols) == 1 and cols[0]["items"][2]["children"] == []  # ссылка подвала — лист
    resolved = menu.resolve_footer(TenantFactory.build(site_config=cfg))
    assert [c["label"] for c in resolved] == ["Service"]
    assert [i["label"] for i in resolved[0]["items"]] == ["Kontakt", "Tief"]
