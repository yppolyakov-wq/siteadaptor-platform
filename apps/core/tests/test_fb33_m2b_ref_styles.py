"""FB-33 M2b: FAQ, команда, галерея и отзывы на страницах — со своим видом.

Раньше блок-ссылка на секцию главной (`faq_ref` и т.д.) всегда рисовался стандартным
видом: стиль терялся. Теперь вид — из видов базовой секции; пусто — как было.
"""

import pytest

from apps.core import site_schema
from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui

REFS = ("faq_ref", "team_ref", "gallery_ref", "testimonials_ref")


@pytest.mark.parametrize("key", REFS)
def test_ref_block_keeps_a_style_of_its_base_section(key):
    base = key[: -len("_ref")]
    style = siteconfig.SECTION_STYLES[base][0]
    assert siteconfig._clean_cblock_data(key, {"style": style}) == {"style": style}
    assert siteconfig._clean_cblock_data(key, {"style": "evil"}) == {}
    assert siteconfig._clean_cblock_data(key, {"title": "x"}) == {}  # контента нет


def test_forms_refs_stay_without_style():
    assert siteconfig._clean_cblock_data("message_ref", {"style": "band"}) == {}


def test_render_passes_the_style_as_section_row(monkeypatch):
    seen = {}

    def fake(tpl, ctx, request=None):
        seen["row"] = ctx["section_row"]
        return ""

    monkeypatch.setattr(siteui, "render_to_string", fake)

    class Ctx(dict):
        def flatten(self):
            return dict(self)

    siteui.render_block(Ctx(), {"key": "faq_ref", "id": "f", "data": {"style": "cards"}})
    assert seen["row"] == {"key": "faq", "style": "cards"}
    siteui.render_block(Ctx(), {"key": "faq_ref", "id": "f", "data": {}})
    assert seen["row"] == {"key": "faq"}  # пусто — прежний вид


@pytest.mark.parametrize("key", REFS)
def test_panel_offers_the_views_of_the_base_section(key):
    block = {"key": key, "fields": site_schema.panel_fields({"key": key, "data": {}})}
    site_schema.fill_options(block, "services")
    field = block["fields"][0]
    assert field["name"] == "style"
    values = [v for v, _lab in field["options"]]
    assert values == ["", *siteconfig.SECTION_STYLES[key[: -len("_ref")]]]


def test_studio_save_keeps_the_ref_style():
    saved = [{"key": "faq_ref", "id": "f1", "data": {"style": "cards"}}]
    posted = [{"key": "faq_ref", "id": "f1", "data": {}}]
    merged = site_schema.merge_structure(saved, posted)
    assert merged[0]["data"] == {"style": "cards"}


@pytest.mark.django_db
def test_panel_writes_and_the_page_draws_the_style(settings):
    """Сквозь «Seitenaufbau»: выбрать вид блока FAQ на странице — он сохранён и виден."""
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    ref = site_schema.apply(tenant, "catalog", "add", block_type="faq_ref")
    html = Browser(tenant).get(f"?seite=catalog&block={ref}")
    assert 'name="f_style"' in html and 'value="numbered"' in html
    site_schema.apply(tenant, "catalog", "update", ref=ref, fields={"style": "numbered"})
    blocks = Tenant.objects.get(pk=tenant.pk).site_config["page_blocks"]["catalog"]
    assert [b["data"] for b in blocks if b["key"] == "faq_ref"] == [{"style": "numbered"}]


@pytest.mark.parametrize("key", site_schema.STYLE_SECTIONS)
def test_home_sections_with_views_get_a_style_field(key):
    assert key in siteconfig.SECTION_STYLES
    fields = site_schema.section_style_fields({"key": key, "style": ""})
    assert [f["name"] for f in fields] == ["style"]
    assert site_schema.section_style_fields({"key": key, "id": "x"}) == []  # свой блок — нет


def test_lists_and_trust_bar_keep_their_own_panels():
    for key in ("products", "promotions", "categories", "usp_bar", "hero"):
        assert site_schema.section_style_fields({"key": key}) == []


@pytest.mark.django_db
def test_home_panel_writes_the_section_style(settings):
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.models import Tenant
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    html = Browser(tenant).get("?seite=home&block=team")
    assert 'name="f_style"' in html and 'value="circles"' in html
    site_schema.apply(tenant, "home", "update", ref="team", fields={"style": "circles"})
    rows = Tenant.objects.get(pk=tenant.pk).site_config["sections"]
    assert next(r for r in rows if r.get("key") == "team").get("style") == "circles"
    site_schema.apply(tenant, "home", "update", ref="team", fields={"style": ""})
    rows = Tenant.objects.get(pk=tenant.pk).site_config["sections"]
    assert "style" not in next(r for r in rows if r.get("key") == "team")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "home", "update", ref="team", fields={"style": "evil"})


def test_stale_studio_tab_does_not_roll_back_the_panel_style():
    """Ревью M2b HIGH: вкладка Студии открыта до правки в панели — Save не откатывает вид."""
    saved = [{"key": "team", "style": "circles"}, {"key": "faq"}]
    posted = [{"key": "team", "style": ""}, {"key": "faq", "style": "cards"}]
    stale = site_schema.merge_structure(saved, posted, fixed=True, keep_data=True)
    by = {r["key"]: r for r in stale}
    assert by["team"].get("style") == "circles" and "style" not in by["faq"]
    fresh = site_schema.merge_structure(saved, posted, fixed=True)  # свежая вкладка — одна ось
    assert {r["key"]: r.get("style") for r in fresh}["faq"] == "cards"


def test_studio_cannot_smuggle_a_ref_style():
    saved = [{"key": "faq_ref", "id": "f1", "data": {}}]
    posted = [{"key": "faq_ref", "id": "f1", "data": {"style": "cards"}}]
    assert site_schema.merge_structure(saved, posted)[0]["data"] == {}


@pytest.mark.parametrize("key", site_schema.STYLE_SECTIONS)
def test_home_section_panel_lists_its_views(key):
    block = {"key": key, "cblock": False, "fields": site_schema.section_style_fields({"key": key})}
    site_schema.fill_options(block, "")
    assert [v for v, _lab in block["fields"][0]["options"]] == ["", *siteconfig.SECTION_STYLES[key]]


def test_style_sections_cover_every_styled_home_section_without_own_panel():
    """Замок: новая секция с видами в SECTION_STYLES не останется без поля «Darstellung»."""
    own_panels = {"products", "promotions", "categories", "usp_bar", "anfrage"}
    home = {k for k, _l, _on in siteconfig.SECTIONS}
    styled = {k for k in siteconfig.SECTION_STYLES if k in home} - own_panels
    assert styled == set(site_schema.STYLE_SECTIONS)


@pytest.mark.django_db
def test_real_render_of_a_styled_faq_block_differs_and_empty_is_unchanged(rf):
    from django.template import Context, Template

    tpl = Template("{% load siteui %}{% render_block b %}")
    req = rf.get("/")
    site = {"faq": [{"q": "Wann?", "a": "Immer."}, {"q": "Wo?", "a": "Hier."}]}

    def html(data):
        return tpl.render(
            Context(
                {"request": req, "site": site, "b": {"key": "faq_ref", "id": "f", "data": data}}
            )
        )

    plain = html({})
    assert plain == html({"style": ""}) and "Wann?" in plain
    assert html({"style": "numbered"}) != plain
