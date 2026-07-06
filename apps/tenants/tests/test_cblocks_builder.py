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


# ---------- UC6-7b: C-блоки страниц (page_blocks) в билдере ----------


def _page_blocks(tenant, host):
    return siteconfig.normalize(tenant.site_config).get("page_blocks", {}).get(host, [])


def test_add_block_with_page_key_goes_to_page_blocks():
    """UC6-7b: инсертер на подстранице (page_key) кладёт блок в page_blocks[хост],
    секции главной не трогает; редирект возвращает канву на ту же страницу."""
    tenant = TenantFactory(slug="pb1", name="X")
    resp = core_views.home_builder_view(
        _req(
            {
                "action": "add_block",
                "block_type": "text",
                "page_key": "services",
                "page_path": "/termin/",
                "add_after": "pbhost:services",  # якорь пустой страницы → append
            },
            tenant,
        )
    )
    tenant.refresh_from_db()
    blocks = _page_blocks(tenant, "services")
    assert len(blocks) == 1 and blocks[0]["key"] == "text"
    assert _cblocks(tenant) == []  # главная не тронута
    assert resp.url == "/dashboard/site/home/?page=/termin/"


def test_add_block_with_unknown_page_key_falls_back_to_home():
    """UC6-7b: page_key вне whitelist (в т.ч. legal) — блок идёт на главную."""
    tenant = TenantFactory(slug="pb2", name="X")
    core_views.home_builder_view(
        _req({"action": "add_block", "block_type": "text", "page_key": "legal"}, tenant)
    )
    tenant.refresh_from_db()
    assert len(_cblocks(tenant)) == 1
    assert siteconfig.normalize(tenant.site_config).get("page_blocks", {}) == {}


def test_add_block_page_insert_after_block_id():
    """UC6-7b: add_after=<id pb-блока> вставляет сразу после него (внутри хоста)."""
    tenant = TenantFactory(
        slug="pb3",
        name="X",
        site_config={
            "page_blocks": {
                "services": [
                    {"key": "text", "id": "aaa", "enabled": True, "data": {"title": "1"}},
                    {"key": "text", "id": "bbb", "enabled": True, "data": {"title": "2"}},
                ]
            }
        },
    )
    core_views.home_builder_view(
        _req(
            {
                "action": "add_block",
                "block_type": "button",
                "page_key": "services",
                "add_after": "aaa",
            },
            tenant,
        )
    )
    tenant.refresh_from_db()
    keys = [(b["key"], b["id"]) for b in _page_blocks(tenant, "services")]
    assert keys[0][1] == "aaa" and keys[1][0] == "button" and keys[2][1] == "bbb"


def test_use_block_template_with_page_key_goes_to_page_blocks():
    """UC6-7b: вставка блок-шаблона на подстранице — в page_blocks[хост]."""
    tenant = TenantFactory(
        slug="pb4",
        name="X",
        site_config={
            "block_templates": {"tplA": {"key": "text", "label": "G", "data": {"title": "Hi"}}}
        },
    )
    core_views.home_builder_view(
        _req(
            {"action": "use_block_template:tplA", "page_key": "catalog", "page_path": "/waren/"},
            tenant,
        )
    )
    tenant.refresh_from_db()
    blocks = _page_blocks(tenant, "catalog")
    assert len(blocks) == 1 and blocks[0]["data"]["title"] == "Hi"
    assert _cblocks(tenant) == []


def test_save_rebuilds_page_blocks_from_pb_rows():
    """UC6-7b: Save пересобирает page_blocks из pb_id-строк (данные/порядок/удаление),
    хост вне whitelist отбрасывается."""
    tenant = TenantFactory(
        slug="pb5",
        name="X",
        site_config={
            "page_blocks": {
                "services": [
                    {"key": "text", "id": "aaa", "enabled": True, "data": {"title": "Alt"}},
                    {"key": "button", "id": "bbb", "enabled": True, "data": {"label": "X"}},
                ],
                "cart": [{"key": "text", "id": "ccc", "enabled": True, "data": {"title": "C"}}],
            }
        },
    )
    data = {
        "pb_present": "1",
        "pb_id": ["aaa", "bbb", "ccc", "zzz"],
        # aaa: правка текста + порядок 2 (уходит после bbb)
        "pb_page_aaa": "services",
        "cb_type_aaa": "text",
        "order_cb_aaa": "2",
        "enabled_cb_aaa": "on",
        "cb_aaa_title": "Neu",
        # bbb: порядок 1
        "pb_page_bbb": "services",
        "cb_type_bbb": "button",
        "order_cb_bbb": "1",
        "enabled_cb_bbb": "on",
        "cb_bbb_label": "Mehr",
        # ccc: удаление
        "pb_page_ccc": "cart",
        "cb_type_ccc": "text",
        "delete_cb_ccc": "on",
        # zzz: хост вне whitelist — отбрасывается
        "pb_page_zzz": "legal",
        "cb_type_zzz": "text",
        "cb_zzz_title": "Nope",
    }
    core_views.home_builder_view(_req(data, tenant))
    tenant.refresh_from_db()
    pb = siteconfig.normalize(tenant.site_config).get("page_blocks", {})
    svc = pb.get("services", [])
    assert [b["id"] for b in svc] == ["bbb", "aaa"]  # пересортировано по order
    assert svc[1]["data"]["title"] == "Neu"
    assert "cart" not in pb  # последний блок хоста удалён → хост исчез
    assert "legal" not in pb


def test_save_without_pb_present_keeps_page_blocks():
    """UC6-7b: POST без presence-guard (старая вкладка) НЕ стирает page_blocks."""
    tenant = TenantFactory(
        slug="pb6",
        name="X",
        site_config={
            "page_blocks": {
                "services": [{"key": "text", "id": "aaa", "enabled": True, "data": {"title": "T"}}]
            }
        },
    )
    core_views.home_builder_view(_req({"order_contact": "5", "enabled_contact": "on"}, tenant))
    tenant.refresh_from_db()
    assert len(_page_blocks(tenant, "services")) == 1


def test_builder_form_renders_pb_rows():
    """UC6-7b: GET билдера рендерит строки page_blocks (общий партиал; маркеры
    pb_id/pb_page_<id>/data-pb-page + presence-guard pb_present)."""
    tenant = TenantFactory(
        slug="pb7",
        name="X",
        site_config={
            "page_blocks": {
                "services": [{"key": "text", "id": "aaa", "enabled": True, "data": {"title": "T"}}]
            }
        },
    )
    request = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    html = core_views.home_builder_view(request).content.decode()
    assert 'name="pb_present"' in html
    assert 'name="pb_page_aaa" value="services"' in html
    assert 'data-pb-page="services"' in html
    assert 'name="cb_aaa_title"' in html  # поля те же, что у блоков главной


def _req_fetch(data, tenant):
    request = RequestFactory().post("/dashboard/site/home/", data, HTTP_X_REQUESTED_WITH="fetch")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    return request


def test_add_block_fetch_returns_row_html():
    """UC6-7c-2: инсертер-без-перезагрузки — fetch add_block с page_key отдаёт JSON
    {ok, id, host, row_html}; row_html — строка _cb_row с pb-маркерами; блок сохранён."""
    import json

    tenant = TenantFactory(slug="pbf1", name="X")
    resp = core_views.home_builder_view(
        _req_fetch(
            {
                "action": "add_block",
                "block_type": "text",
                "page_key": "services",
                "page_path": "/termin/",
            },
            tenant,
        )
    )
    assert resp.status_code == 200
    payload = json.loads(resp.content)
    assert payload["ok"] is True and payload["host"] == "services"
    bid = payload["id"]
    assert f'name="pb_page_{bid}" value="services"' in payload["row_html"]
    assert f'name="cb_{bid}_title"' in payload["row_html"]  # поля строки на месте
    tenant.refresh_from_db()
    assert len(_page_blocks(tenant, "services")) == 1  # блок реально сохранён


def test_add_block_fetch_on_home_returns_not_ok():
    """UC6-7c-2: fetch без хоста страницы (главная) → {ok:false} (клиент откатится
    на форм-POST); блок при этом всё равно добавляется в sections."""
    import json

    tenant = TenantFactory(slug="pbf2", name="X")
    resp = core_views.home_builder_view(
        _req_fetch({"action": "add_block", "block_type": "text"}, tenant)
    )
    assert resp.status_code == 200
    assert json.loads(resp.content)["ok"] is False
    tenant.refresh_from_db()
    assert len(_cblocks(tenant)) == 1  # на главную блок добавлен


def test_home_content_blocks_details_is_home_scoped():
    """UC6-7b (review-fix): строка блока ГЛАВНОЙ (cb_id → sections) рендерится внутри
    <details data-scope=\"home\">, чтобы applyPageScope прятал её на подстраницах
    (иначе блоки главной путаются с блоками страницы). Язык-независимый якорь —
    поле cb_<id>_title домашнего блока (у pb-строк отдельный маркер data-pb-page)."""
    tenant = TenantFactory(
        slug="pbscope",
        name="X",
        site_config={
            "sections": [{"key": "text", "id": "hhh", "enabled": True, "data": {"title": "H"}}]
        },
    )
    request = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    html = core_views.home_builder_view(request).content.decode()
    # строка блока главной — по её полю cb_hhh_title (домашняя, без data-pb-page).
    idx = html.find('name="cb_hhh_title"')
    assert idx > 0
    details_open = html.rfind("<details", 0, idx)
    assert details_open > 0
    assert 'data-scope="home"' in html[details_open:idx]
