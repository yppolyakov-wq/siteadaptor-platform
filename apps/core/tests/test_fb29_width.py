"""FB-29.5 (макет A, утверждён владельцем 2026-11-13): ширина — у ВСЕХ блоков, включая
встроенные секции главной; узкие соседи стоят в одном ряду; панель говорит, с кем рядом."""

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


def _cfg(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _row(tenant, key):
    return next(s for s in _cfg(tenant)["sections"] if s.get("key") == key and not s.get("id"))


def test_builtin_section_has_width_buttons():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=products")
    assert "data-schema-width" in html
    box = html[html.index("data-schema-width") :]
    box = box[: box.index("</form>")]
    for value in ("contained", "w23", "w12", "w13"):
        assert f'value="{value}"' in box, value
    assert "data-schema-width-bar" in box  # кнопка показывает долю полоской


def test_builtin_width_goes_through_the_draft_and_survives_normalize():
    b = Browser(_tenant())
    b.post(seite="home", op="width", ref="products", value="w12")
    assert _row(b.tenant, "products").get("width", "contained") == "contained"  # черновик
    b.post(seite="home", op="save")
    assert _row(b.tenant, "products")["width"] == "w12"
    # повторный normalize ничего не меняет
    cfg = _cfg(b.tenant)
    assert siteconfig.normalize(cfg) == cfg


def test_two_narrow_builtin_sections_stand_in_one_row():
    tenant = _tenant()
    on = [s for s in _cfg(tenant)["sections"] if s.get("enabled") and not s.get("id")]
    pair = next(
        (
            (a["key"], b["key"])
            for a, b in zip(on, on[1:], strict=False)
            if site_schema.home_section(a) and site_schema.home_section(b)
        ),
        None,
    )
    assert pair, "у магазина есть две соседние встроенные секции"
    for key in pair:
        site_schema.apply(tenant, "home", "width", ref=key, value="w12")
    rows = siteconfig.group_block_rows([s for s in _cfg(tenant)["sections"] if s.get("enabled")])
    row = next(r for r in rows if r.get("key") == "_row")
    assert [s["key"] for s in row["row"]] == list(pair)


def test_rubbish_width_is_refused():
    b = Browser(_tenant())
    before = _row(b.tenant, "products").get("width")
    _resp, msgs = b.post(seite="home", op="width", ref="products", value="w99")
    b.post(seite="home", op="save")
    assert _row(b.tenant, "products").get("width") == before
    assert msgs  # владельцу сказано, что так нельзя


def test_studio_save_keeps_the_width_set_in_seitenaufbau():
    """Ширину встроенной секции теперь задаёт «Seitenaufbau» — форма Студии её не откатит."""
    tenant = _tenant()
    site_schema.apply(tenant, "home", "width", ref="products", value="w12")
    saved = _cfg(tenant)["sections"]
    posted = [{**s, "width": "contained"} for s in saved]
    merged = site_schema.merge_structure(saved, posted, fixed=True)
    row = next(s for s in merged if s.get("key") == "products" and not s.get("id"))
    assert row["width"] == "w12"


def test_panel_names_the_neighbours():
    tenant = _tenant()
    site_schema.apply(tenant, "home", "width", ref="products", value="w12")
    b = Browser(tenant)
    html = b.get("?seite=home&block=products")
    assert "data-schema-width-mates" in html


# ───────── FB-29.3: наглядная панель — миниатюра следует за настройками ─────────


def test_row_thumbnail_follows_columns_and_output():
    b = Browser(_tenant())
    b.post(seite="home", op="update", ref="products", panel_present="1", f_cols="2", f_out="grid")
    html = b.get("?seite=home&block=products")
    row = html[html.index('data-schema-block="products"') :]
    row = row[: row.index("</a>")]
    assert 'data-schema-thumb="cards"' in row and 'data-thumb-cols="2"' in row
    b.post(seite="home", op="update", ref="products", panel_present="1", f_out="slider")
    html = b.get("?seite=home&block=products")
    row = html[html.index('data-schema-block="products"') :]
    assert 'data-thumb-out="slider"' in row[: row.index("</a>")]


def test_panel_shows_a_preview_of_the_block():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=products")
    panel = html[html.index("data-schema-panel") :]
    assert "data-schema-preview" in panel
    assert "So sieht der Block aus" in panel


def test_columns_are_buttons_when_there_is_nothing_to_inherit():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=products")
    assert 'data-schema-buttons="cols"' in html
    box = html[html.index('data-schema-buttons="cols"') :]
    box = box[: box.index("</div>")]
    assert box.count('type="radio"') == 6 and 'name="f_cols"' in box


# ───────── FB-29.5b: перетаскивание — та же перестановка, что «выше/ниже» ─────────


def _refs(tenant):
    return [s.get("id") or s["key"] for s in _cfg(tenant)["sections"] if s.get("enabled", True)]


def test_move_places_a_block_before_or_after_another():
    b = Browser(_tenant())
    refs = _refs(b.tenant)
    assert len(refs) >= 3
    first, last = refs[0], refs[-1]
    b.post(seite="home", op="move", ref=last, value=f"before:{first}")
    b.post(seite="home", op="save")
    assert _refs(b.tenant) == [last, *refs[:-1]]
    b.post(seite="home", op="move", ref=last, value=f"after:{refs[-2]}")
    b.post(seite="home", op="save")
    assert _refs(b.tenant) == refs


def test_move_equals_the_buttons():
    one, two = Browser(_tenant()), Browser(_tenant())
    refs = _refs(one.tenant)
    one.post(seite="home", op="up", ref=refs[1])
    one.post(seite="home", op="save")
    two.post(seite="home", op="move", ref=refs[1], value=f"before:{refs[0]}")
    two.post(seite="home", op="save")
    assert _refs(one.tenant) == _refs(two.tenant)


def test_move_with_rubbish_changes_nothing():
    b = Browser(_tenant())
    refs = _refs(b.tenant)
    for value in ("", "before:", "sideways:" + refs[0], "before:nope", f"before:{refs[1]}"):
        b.post(seite="home", op="move", ref=refs[1], value=value)
    b.post(seite="home", op="save")
    assert _refs(b.tenant) == refs


def test_rows_are_draggable_only_with_scripts_and_buttons_stay():
    import pathlib

    tpl = pathlib.Path("templates/tenant/site_schema.html").read_text()
    assert "data-schema-drag" in tpl and 'value="up"' in tpl and 'value="down"' in tpl
    js = pathlib.Path("static/js/aufbau.js").read_text()
    assert "dragstart" in js and '"move"' in js


def test_banner_cannot_be_narrow():
    """Ревью: баннер рисуется во всю ширину экрана — доли ширины ломали бы вёрстку."""
    b = Browser(_tenant())
    html = b.get("?seite=home&block=hero")
    box = html[html.index("data-schema-width") :]
    box = box[: box.index("</form>")]
    assert 'value="contained"' in box and 'value="w12"' not in box
    _resp, msgs = b.post(seite="home", op="width", ref="hero", value="w12")
    assert msgs


def test_empty_narrow_section_leaves_no_hole():
    import pathlib

    tpl = pathlib.Path("templates/storefront/_section_block.html").read_text()
    assert "[&:not(:has(*))]:hidden" in tpl
