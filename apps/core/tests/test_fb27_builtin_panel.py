"""FB-27: встроенные списки главной («Kategorien», «Produkte» …) открывают в «Seitenaufbau»
ту же панель «Welche · Wie», что блок «Liste» (макет Main). Правки идут в черновик;
нетронутая панель ничего не меняет (W0)."""

import pytest

from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_design_tabs import _Form
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(kind="online_shop"):
    return TenantFactory(business_type=kind, disabled_modules=list(default_disabled_for(kind)))


def _row(tenant, key):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return next(s for s in cfg["sections"] if s.get("key") == key and not s.get("id"))


def test_builtin_list_opens_the_which_and_how_panel():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=products")
    assert "data-schema-list" in html
    assert 'data-schema-group="welche"' in html and 'data-schema-group="wie"' in html
    # источник закреплён ключом секции, ручного состава у встроенной строки нет
    assert 'name="f_source"' not in html and 'data-schema-which-mode="einzeln"' not in html
    assert 'name="f_limit"' in html and 'name="f_cols"' in html and 'name="f_out"' in html
    assert "data-schema-source" in html


def test_change_goes_through_the_draft_and_reaches_the_site():
    b = Browser(_tenant())
    b.post(
        seite="home", op="update", ref="products", panel_present="1",
        f_limit="4", f_cols="2", f_out="slider",
    )  # fmt: skip
    assert _row(b.tenant, "products").get("layout", {}).get("scroll") is not True  # черновик
    b.post(seite="home", op="save")
    row = _row(b.tenant, "products")
    assert row["limit"] == 4 and row["layout"]["cols"] == 2 and row["layout"]["scroll"] is True
    b.post(seite="home", op="update", ref="products", panel_present="1", f_out="grid")
    b.post(seite="home", op="save")
    assert "scroll" not in _row(b.tenant, "products")["layout"]


def test_filter_of_the_section_is_stored_in_its_data():
    b = Browser(_tenant())
    b.post(seite="home", op="update", ref="products", panel_present="1", f_only="sale")
    b.post(seite="home", op="save")
    from apps.core import list_blocks

    assert list_blocks.section_data(_row(b.tenant, "products")).get("only") == "sale"


def test_rubbish_is_not_stored():
    b = Browser(_tenant())
    before = _row(b.tenant, "products")
    b.post(
        seite="home", op="update", ref="products", panel_present="1",
        f_limit="<x>", f_cols="99", f_out="<script>", f_source="reviews", f_title="X",
    )  # fmt: skip
    b.post(seite="home", op="save")
    row = _row(b.tenant, "products")
    assert row["limit"] == before["limit"]
    assert 1 <= row["layout"]["cols"] <= 6
    assert "title" not in (row.get("data") or {}) and "source" not in (row.get("data") or {})


def _untouched(b, key):
    form = _Form()
    form.inside_marker = "data-schema-list"
    html = b.get(f"?seite=home&block={key}")
    start = html.index("data-schema-list")
    chunk = html[html.rfind("<form", 0, start) : html.index("</form>", start) + 7]
    form.feed(chunk.replace("data-schema-list", "data-design-form"))
    return dict(form.fields)


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        ("online_shop", "products"),
        ("online_shop", "categories"),
        ("online_shop", "promotions"),
        ("friseur", "services"),
        ("hotel", "stay_rooms"),
        ("events", "events"),
    ],
)
def test_untouched_panel_never_changes_the_section(kind, key):
    tenant = _tenant(kind)
    cfg = siteconfig.normalize(tenant.site_config)
    if not any(s.get("key") == key for s in cfg["sections"]):
        pytest.skip("у этого типа бизнеса такой секции нет")
    b = Browser(tenant)
    fields = _untouched(b, key)
    assert fields.get("panel_present") == "1"
    before = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    b.post(**{**fields, "op": "update"})
    html = b.get("?seite=home")
    assert "data-schema-draft-note" not in html, "нетронутая панель создала черновик"
    assert siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config) == before


def test_banner_setting_is_open_when_it_is_the_only_one():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=hero")
    assert html.count("data-schema-setting-box=") >= 1
    if html.count("data-schema-setting-box=") == 1:
        box = html[html.index("data-schema-setting-box=") :][:200]
        assert " open" in box.split(">")[0]


def test_stale_studio_tab_cannot_roll_the_panel_edit_back():
    """Ревью: вкладка Студии, открытая до правки, несёт прежние лимит, вид и фильтр
    встроенного списка — отпечаток обязан измениться, а слияние — оставить сохранённое."""
    from apps.core import site_schema

    b = Browser(_tenant())
    old_cfg = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    old_hash = site_schema.structure_hash(old_cfg)
    b.post(
        seite="home", op="update", ref="products", panel_present="1",
        f_only="sale", f_limit="4", f_out="slider",
    )  # fmt: skip
    b.post(seite="home", op="save")
    new_cfg = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    assert site_schema.structure_hash(new_cfg) != old_hash
    merged = site_schema.merge_structure(
        new_cfg["sections"], old_cfg["sections"], fixed=True, keep_data=True
    )
    row = next(s for s in merged if s.get("key") == "products" and not s.get("id"))
    saved = next(s for s in new_cfg["sections"] if s.get("key") == "products" and not s.get("id"))
    for field in site_schema.BUILTIN_OWNED_FIELDS:
        assert row.get(field) == saved.get(field), field
