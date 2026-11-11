"""FB-27 R3a: ширина блока в «Seitenaufbau» — узкие соседи встают в один ряд."""

import pytest

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _blocks(tenant, host="info"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return [b for b in cfg["page_blocks"][host] if b.get("id")]


def test_two_halves_make_one_row_after_saving():
    b = Browser(_tenant())
    refs = [site_schema.apply(b.tenant, "text", "add", block_type=t) for t in ("text", "image")]
    for ref in refs:
        b.post(seite="text", op="width", ref=ref, value="w12")
    assert [x["width"] for x in _blocks(b.tenant)] == ["contained", "contained"]  # пока черновик
    html = b.get("?seite=text")
    assert "Blöcke nebeneinander" in html and html.count(">½<") >= 2
    b.post(seite="text", op="save")
    assert [x["width"] for x in _blocks(b.tenant)] == ["w12", "w12"]
    rows = siteconfig.group_block_rows(_blocks(b.tenant))
    assert len(rows) == 1 and len(rows[0]["row"]) == 2  # витрина рисует один ряд


def test_every_width_down_to_a_sixth_is_offered_for_a_simple_block():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="text")
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(x for x in site_schema.blocks_for(cfg, "text") if x["ref"] == ref)
    assert [w[0] for w in block["widths"]] == [
        "contained", "w23", "w12", "w13", "w14", "w15", "w16",
    ]  # fmt: skip


def test_list_blocks_do_not_go_narrower_than_a_half():
    """Решение владельца: сетки карточек не сужаются сильнее половины."""
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(x for x in site_schema.blocks_for(cfg, "text") if x["ref"] == ref)
    assert [w[0] for w in block["widths"]] == ["contained", "w23", "w12"]
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "width", ref=ref, value="w16")


def test_existing_narrow_list_keeps_its_width():
    """Уже выбранная ширина остаётся в списке и не сбрасывается (W0)."""
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    row = Tenant.objects.get(pk=tenant.pk)
    cfg = siteconfig.normalize(row.site_config)
    next(x for x in cfg["page_blocks"]["info"] if x.get("id") == ref)["width"] = "w13"
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    block = next(x for x in site_schema.blocks_for(cfg, "text") if x["ref"] == ref)
    assert "w13" in [w[0] for w in block["widths"]]


def test_width_is_refused_for_fixed_rows_and_garbage():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="text")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "home", "width", ref="hero", value="w12")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "catalog", "width", ref=siteconfig.MAIN_LIST_KEY, value="w12")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "width", ref=ref, value="evil")


def test_new_row_toggle_only_for_narrow_blocks():
    tenant = _tenant()
    refs = [site_schema.apply(tenant, "text", "add", block_type="text") for _ in range(2)]
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "newline", ref=refs[1])  # широкий
    for ref in refs:
        site_schema.apply(tenant, "text", "width", ref=ref, value="w12")
    site_schema.apply(tenant, "text", "newline", ref=refs[1])
    assert len(siteconfig.group_block_rows(_blocks(tenant))) == 2  # два ряда по одному
    site_schema.apply(tenant, "text", "width", ref=refs[1], value="contained")
    assert "newline" not in next(x for x in _blocks(tenant) if x["id"] == refs[1])


def test_width_counts_as_a_change():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    b.post(seite="text", op="width", ref=ref, value="w13")
    assert "data-schema-draft" in b.get("?seite=text")
    b.post(seite="text", op="width", ref=ref, value="contained")
    assert "data-schema-draft" not in b.get("?seite=text")


def test_panel_offers_width_only_for_own_blocks():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    assert "data-schema-width" in b.get(f"?seite=text&block={ref}")
    assert "data-schema-width" not in b.get("?seite=home&block=hero")


@pytest.mark.parametrize(
    "block_type", ["banner", "stats", "newsletter", "image_text", "promo", "faq_ref", "anfrage_ref"]
)
def test_only_simple_blocks_go_narrower_than_a_half(block_type):
    """Формы, баннер, цифры и сетки в ⅙ ширины ломаются — им не уже половины."""
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type=block_type)
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "width", ref=ref, value="w13")
    site_schema.apply(tenant, "text", "width", ref=ref, value="w12")


def test_width_works_for_own_blocks_on_the_home_page():
    b = Browser(_tenant())
    refs = [site_schema.apply(b.tenant, "home", "add", block_type="text") for _ in range(2)]
    for ref in refs:
        b.post(seite="home", op="width", ref=ref, value="w12")
    b.post(seite="home", op="save")
    cfg = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    own = [x for x in cfg["sections"] if x.get("id") in refs]
    assert [x["width"] for x in own] == ["w12", "w12"]
    rows = [g for g in siteconfig.group_block_rows(cfg["sections"]) if g.get("key") == "_row"]
    assert len(rows) == 1 and [x["id"] for x in rows[0]["row"]] == refs


def test_widths_are_named_in_words_for_screen_readers():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    html = b.get(f"?seite=text&block={ref}")
    assert 'aria-label="ein Sechstel"' in html and 'aria-label="die Hälfte"' in html


# --- R3b: короткое содержимое простого блока в панели -------------------------


def test_text_is_edited_in_the_panel_through_the_draft():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    html = b.get(f"?seite=text&block={ref}")
    assert "data-schema-fields" in html and 'name="f_title"' in html and 'name="f_body"' in html
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_title="Neu", f_body="Hallo")
    assert _blocks(b.tenant)[0]["data"]["title"] != "Neu"  # пока только черновик
    assert 'value="Neu"' in b.get(f"?seite=text&block={ref}")
    b.post(seite="text", op="save")
    data = _blocks(b.tenant)[0]["data"]
    assert data["title"] == "Neu" and data["body"] == "Hallo"


def test_panel_update_is_a_patch_not_a_rebuild():
    """Панель показывает часть полей — остальные (стиль, фото, оформление) не стираются."""
    tenant = _tenant()
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "info": [
                    {
                        "id": "a1",
                        "key": "image_text",
                        "enabled": True,
                        "width": "w23",
                        "pos": "right",
                        "visual": {"radius": 12, "shadow": True, "background": "", "padding": 0},
                        "data": {
                            "url": "/media/x.jpg",
                            "title": "Alt",
                            "body": "Text",
                            "side": "right",
                            "align": "center",
                            "rounded": "3xl",
                        },
                    }
                ]
            }
        }
    )
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    before = _blocks(tenant)[0]
    b = Browser(tenant)
    b.post(seite="text", op="update", ref="a1", panel_present="1", f_title="Neu")
    b.post(seite="text", op="save")
    after = _blocks(tenant)[0]
    assert after["data"]["title"] == "Neu"
    expected = {**before, "data": {**before["data"], "title": "Neu"}}
    assert after == expected


def test_fields_are_ignored_without_the_panel_sentinel():
    """«Выше/ниже» с той же страницы не должны стирать текст блока."""
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    title = _blocks(b.tenant)[0]["data"]["title"]
    b.post(seite="text", op="update", ref=ref, f_title="")
    b.post(seite="text", op="save")
    assert _blocks(b.tenant)[0]["data"]["title"] == title


def test_unknown_fields_and_blocks_without_panel_fields_are_refused():
    tenant = _tenant()
    text = site_schema.apply(tenant, "text", "add", block_type="text")
    banner = site_schema.apply(tenant, "text", "add", block_type="banner")
    site_schema.apply(tenant, "text", "update", ref=text, fields={"evil": "x", "align": "right"})
    data = next(x for x in _blocks(tenant) if x["id"] == text)["data"]
    assert "evil" not in data and data.get("align") != "right"  # чужое поле не прошло
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "update", ref=banner, fields={"title": "x"})
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "home", "update", ref="hero", fields={"title": "x"})


def test_content_change_counts_and_reverts():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="button")
    label = _blocks(b.tenant)[0]["data"]["label"]
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_label="Jetzt")
    assert "data-schema-draft" in b.get("?seite=text")
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_label=label)
    assert "data-schema-draft" not in b.get("?seite=text")
