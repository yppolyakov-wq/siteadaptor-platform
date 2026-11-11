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
    assert [v for v, _l in block["widths"]] == [
        "contained", "w23", "w12", "w13", "w14", "w15", "w16",
    ]  # fmt: skip


def test_list_blocks_do_not_go_narrower_than_a_half():
    """Решение владельца: сетки карточек не сужаются сильнее половины."""
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(x for x in site_schema.blocks_for(cfg, "text") if x["ref"] == ref)
    assert [v for v, _l in block["widths"]] == ["contained", "w23", "w12"]
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
    assert "w13" in [v for v, _l in block["widths"]]


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
    assert "1 Änderung" in b.get("?seite=text")
    b.post(seite="text", op="width", ref=ref, value="contained")
    assert "data-schema-draft" not in b.get("?seite=text")


def test_panel_offers_width_only_for_own_blocks():
    b = Browser(_tenant())
    ref = site_schema.apply(b.tenant, "text", "add", block_type="text")
    assert "data-schema-width" in b.get(f"?seite=text&block={ref}")
    assert "data-schema-width" not in b.get("?seite=home&block=hero")
