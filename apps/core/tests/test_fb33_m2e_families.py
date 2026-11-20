"""FB-33 M2e: семьи блоков в меню «+ Block» и смена вида в панели без потери данных."""

import pytest
from django.utils import translation

from apps.core import block_catalog, site_schema
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def test_menu_labels_show_the_family_and_the_view():
    with translation.override("de"):
        labels = dict(site_schema.add_options("text"))
    assert labels["text"] == "Text · Nur Text"
    assert labels["image_text"] == "Text · Foto + Text"
    assert labels["textpage"] == "Text · Von einer Seite"
    assert labels["button"].endswith("· Nur Button")
    assert labels["contact_card"].endswith("· Karte")
    assert labels["newsletter"] == str(
        siteconfig.CBLOCK_LABELS["newsletter"]
    )  # один вид — как было


def test_menu_keeps_its_items_and_order():
    keys = [k for g in site_schema.add_groups("text") for k, _ in g["options"]]
    assert sorted(keys) == sorted(k for k, _ in site_schema.add_options("text"))


def test_text_remembers_the_photo():
    """Решение владельца: «Фото + текст» → «Только текст» — фото помнится, обратно на месте."""
    it = {"url": "/m/a.jpg", "title": "T", "body": "B", "side": "right", "rounded": "3xl"}
    as_text = siteconfig._clean_cblock_data("text", it)
    assert as_text == {
        "title": "T",
        "body": "B",
        "url": "/m/a.jpg",
        "side": "right",
        "rounded": "3xl",
    }
    back = siteconfig._clean_cblock_data("image_text", as_text)
    assert back["url"] == "/m/a.jpg" and back["side"] == "right" and back["rounded"] == "3xl"
    # текст без фото — прежние ключи (старые конфиги байт-в-байт)
    assert siteconfig._clean_cblock_data("text", {"title": "T", "body": "B"}) == {
        "title": "T",
        "body": "B",
    }


def _items():
    return [{"key": "image_text", "id": "b1", "enabled": True, "width": "w12",
             "data": {"url": "/m/a.jpg", "title": "T", "body": "B", "side": "left"}}]  # fmt: skip


def test_switch_keeps_id_width_and_texts():
    items = _items()
    site_schema.mutate(items, "text", "switch", ref="b1", value="text")
    assert items[0]["key"] == "text" and items[0]["id"] == "b1" and items[0]["width"] == "w12"
    assert items[0]["data"]["title"] == "T" and items[0]["data"]["url"] == "/m/a.jpg"
    site_schema.mutate(items, "text", "switch", ref="b1", value="image_text")
    assert items[0]["key"] == "image_text" and items[0]["data"]["url"] == "/m/a.jpg"


@pytest.mark.parametrize("target", ("button", "image_text_x", "image_text", "contact_card"))
def test_switch_refuses_lossy_or_unknown_views(target):
    items = _items()
    if target == "image_text":  # тот же вид — ничего не меняется (без ошибки)
        site_schema.mutate(items, "text", "switch", ref="b1", value=target)
        assert items[0]["key"] == "image_text"
        return
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "text", "switch", ref="b1", value=target)
    assert items[0]["key"] == "image_text"


def test_switch_options_only_for_lossless_pairs():
    # FB-33 M3-3d: «Von einer Seite» — тоже вид текста (оба источника помнятся)
    assert {k for k, _ in block_catalog.switch_options("text")} == {
        "text",
        "image_text",
        "textpage",
    }
    assert block_catalog.switch_options("button") == []
    assert {k for k, _ in block_catalog.switch_options("textpage")} == {
        "text",
        "image_text",
        "textpage",
    }


def test_translations_survive_a_switch():
    """Переводы данных блока лежат в оверлее по месту блока — смена вида их не теряет."""
    cfg = siteconfig.normalize({"page_blocks": {"catalog": _items()}})
    siteconfig.set_overlay_value(cfg, "ru", ("page_blocks", "catalog", 0, "data", "title"), "Т")
    cfg = siteconfig.normalize(cfg)
    assert siteconfig.localize(cfg, "ru")["page_blocks"]["catalog"][0]["data"]["title"] == "Т"
    site_schema.mutate(cfg["page_blocks"]["catalog"], "catalog", "switch", ref="b1", value="text")
    cfg = siteconfig.normalize(cfg)
    assert siteconfig.localize(cfg, "ru")["page_blocks"]["catalog"][0]["data"]["title"] == "Т"


def test_panel_shows_family_and_view_switch(settings):
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    ref = site_schema.apply(tenant, "catalog", "add", block_type="image_text")
    html = Browser(tenant).get(f"?seite=catalog&block={ref}")
    assert "data-schema-family" in html and "data-schema-switch" in html
    assert 'value="switch"' in html and 'value="text"' in html
    site_schema.apply(tenant, "catalog", "switch", ref=ref, value="text")
    from apps.tenants.models import Tenant

    rows = Tenant.objects.get(pk=tenant.pk).site_config["page_blocks"]["catalog"]
    assert next(r for r in rows if r["id"] == ref)["key"] == "text"


def test_studio_save_keeps_the_remembered_photo():
    saved = [
        {
            "key": "text",
            "id": "b1",
            "data": {"title": "T", "body": "B", "url": "/m/a.jpg", "side": "right"},
        }
    ]
    posted = [{"key": "text", "id": "b1", "data": {"title": "Neu", "body": "B"}}]
    merged = site_schema.merge_structure(saved, posted)[0]["data"]
    assert merged == {"title": "Neu", "body": "B", "url": "/m/a.jpg", "side": "right"}


def test_view_switch_counts_as_a_draft_change():
    from apps.core import aufbau_draft

    saved = {"items": _items()}
    draft = {"items": _items()}
    site_schema.mutate(draft["items"], "text", "switch", ref="b1", value="text")
    assert aufbau_draft.changes(saved, draft) == 1


def test_switch_to_the_current_view_is_a_no_op():
    items = _items()
    assert site_schema.mutate(items, "text", "switch", ref="b1", value="image_text") == "b1"
    assert items[0]["key"] == "image_text"
