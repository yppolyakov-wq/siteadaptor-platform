"""Спринт D.2b: билдер C-блоков — добавление, правка, порядок, удаление, round-trip."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data, tenant):
    request = RequestFactory().post("/dashboard/site/home/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    return request


def _cblocks(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [s for s in cfg["sections"] if s["key"] in siteconfig.REPEATABLE_BLOCKS]


def test_add_block_appends_empty_cblock():
    tenant = TenantFactory(slug="cb1", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    blocks = _cblocks(tenant)
    assert len(blocks) == 1 and blocks[0]["key"] == "text"


def test_add_block_after_inserts_at_position():
    """E.3: инсертер «+» — add_after вставляет C-блок сразу после указанной секции."""
    tenant = TenantFactory(
        slug="cbins",
        name="X",
        site_config={
            "sections": [{"key": "hero", "enabled": True}, {"key": "products", "enabled": True}]
        },
    )
    core_views.home_builder_view(
        _req({"action": "add_block", "block_type": "text", "add_after": "hero"}, tenant)
    )
    tenant.refresh_from_db()
    keys = [s["key"] for s in siteconfig.normalize(tenant.site_config)["sections"]]
    assert keys[keys.index("hero") + 1] == "text"  # вставлен сразу после hero, не в конец


def test_use_block_template_inserts_at_position():
    """SE-4c: вставка сохранённого блок-шаблона в позицию (insert_after) — не в конец."""
    tenant = TenantFactory(
        slug="cbtplpos",
        name="X",
        site_config={
            "sections": [{"key": "hero", "enabled": True}, {"key": "products", "enabled": True}],
            "block_templates": {"tplA": {"key": "text", "label": "G", "data": {"title": "Hi"}}},
        },
    )
    core_views.home_builder_view(
        _req({"action": "use_block_template:tplA", "insert_after": "hero"}, tenant)
    )
    tenant.refresh_from_db()
    keys = [s["key"] for s in siteconfig.normalize(tenant.site_config)["sections"]]
    assert keys[keys.index("hero") + 1] == "text"  # копия шаблона сразу после hero


def test_use_block_template_without_position_appends():
    """SE-4c: без insert_after поведение прежнее — копия в конец (back-compat)."""
    tenant = TenantFactory(
        slug="cbtplend",
        name="X",
        site_config={
            "block_templates": {"tplA": {"key": "text", "label": "G", "data": {"title": "Hi"}}}
        },
    )
    core_views.home_builder_view(_req({"action": "use_block_template:tplA"}, tenant))
    tenant.refresh_from_db()
    blocks = _cblocks(tenant)
    assert len(blocks) == 1 and blocks[0]["data"]["title"] == "Hi"


def test_save_persists_cblock_edits_and_keeps_fixed_sections():
    tenant = TenantFactory(slug="cb2", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    # основное сохранение: правим текст блока + он включён, фикс-секции тоже шлём.
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"order_cb_{bid}": "3",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "Mein Titel",
        f"cb_{bid}_body": "Mein Text",
        "enabled_contact": "on",
        "order_contact": "5",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    blocks = _cblocks(tenant)
    assert len(blocks) == 1  # C-блок НЕ потерян при сохранении главной
    assert blocks[0]["data"]["title"] == "Mein Titel"
    assert blocks[0]["data"]["body"] == "Mein Text"
    # фикс-секция contact сохранилась включённой
    cfg = siteconfig.normalize(tenant.site_config)
    assert any(s["key"] == "contact" and s["enabled"] for s in cfg["sections"])


def test_delete_checkbox_removes_cblock():
    tenant = TenantFactory(slug="cb3", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "button"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "button",
        f"delete_cb_{bid}": "on",
        f"cb_{bid}_label": "X",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    assert _cblocks(tenant) == []


def test_save_persists_text_style_fields():
    """UC6-2: align/size/color из формы билдера доезжают до site_config."""
    tenant = TenantFactory(slug="cb6", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "T",
        f"cb_{bid}_align": "center",
        f"cb_{bid}_size": "lg",
        f"cb_{bid}_color": "muted",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    block = _cblocks(tenant)[0]
    assert block["data"]["align"] == "center"
    assert block["data"]["size"] == "lg"
    assert block["data"]["color"] == "muted"


def test_save_persists_cblock_width_and_pos():
    """UC6-3: ширина/положение C-блока переживают Save (раньше width терялся)."""
    tenant = TenantFactory(slug="cb7", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "T",
        f"width_cb_{bid}": "w23",
        f"pos_cb_{bid}": "right",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    block = _cblocks(tenant)[0]
    assert block["width"] == "w23"
    assert block["pos"] == "right"


def test_add_block_prefills_demo_data():
    """UC6-5: вставка блока даёт живой пример (DE-рыба), а не пустоту."""
    tenant = TenantFactory(slug="cb8", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "image_text"}, tenant))
    tenant.refresh_from_db()
    block = _cblocks(tenant)[0]
    assert block["data"]["title"]  # демо-заголовок на месте
    assert block["data"]["url"].startswith("/medien/demo.svg")
    # spacer — осознанно без демо-данных
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "spacer"}, tenant))
    tenant.refresh_from_db()
    spacer = next(b for b in _cblocks(tenant) if b["key"] == "spacer")
    assert spacer["data"] == {}


def test_cblock_demo_data_survives_normalize_unchanged():
    """UC6-5: демо-данные каждого типа проходят _clean_cblock_data без потерь."""
    for btype, demo in siteconfig.CBLOCK_DEMO_DATA.items():
        assert siteconfig._clean_cblock_data(btype, demo) == demo, btype


def test_save_persists_newline_flag():
    """UC6-3a: чекбокс «с новой строки» доезжает до site_config."""
    tenant = TenantFactory(slug="cb9", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "T",
        f"width_cb_{bid}": "w13",
        f"newline_cb_{bid}": "on",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    block = _cblocks(tenant)[0]
    assert block["width"] == "w13" and block["newline"] is True


def test_save_persists_cblock_visual():
    """UC6-6b: тень/радиус/фон/отступ блока переживают Save."""
    tenant = TenantFactory(slug="cb10", name="X")
    core_views.home_builder_view(_req({"action": "add_block", "block_type": "text"}, tenant))
    tenant.refresh_from_db()
    bid = _cblocks(tenant)[0]["id"]
    data = {
        "cb_id": bid,
        f"cb_type_{bid}": "text",
        f"enabled_cb_{bid}": "on",
        f"cb_{bid}_title": "T",
        f"visual_shadow_cb_{bid}": "on",
        f"visual_radius_px_cb_{bid}": "12",
        f"visual_padding_cb_{bid}": "16",
        f"visual_bg_on_cb_{bid}": "on",
        f"visual_bg_cb_{bid}": "#ffeecc",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    vis = _cblocks(tenant)[0]["visual"]
    assert vis == {"radius": 12, "shadow": True, "background": "#ffeecc", "padding": 16}


def test_add_block_with_variant_applies_preset():
    """UC6-6c: вставка с variant из инсертера даёт преднастроенный блок."""
    tenant = TenantFactory(slug="cb11", name="X")
    core_views.home_builder_view(
        _req({"action": "add_block", "block_type": "text", "variant": "banner"}, tenant)
    )
    tenant.refresh_from_db()
    block = _cblocks(tenant)[0]
    assert block["data"]["color"] == "accent" and block["data"]["size"] == "xl"
    assert block["visual"]["shadow"] is True and block["visual"]["radius"] == 16
