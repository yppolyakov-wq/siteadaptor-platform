"""FB-27 R6: блоки «Textseite» и «Kontakt», меню «+ Block» с готовыми строками."""

import uuid

import pytest
from django.http import QueryDict
from django.template import Context, Template
from django.test import RequestFactory

from apps.core import content_pages, site_schema, views
from apps.core.models import ContentPage
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    return TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        **kw,
    )


def _page(slug="zahlung", title="Zahlung", body="<p>Wir nehmen Karte und bar.</p>", **kw):
    return ContentPage.objects.create(
        slug=slug, title=title, body=body, is_published=kw.pop("is_published", True), **kw
    )


def _blocks(tenant, host="info"):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return [b for b in (cfg.get("page_blocks") or {}).get(host, []) if b.get("id")]


def _render(tenant, block, host="", url_name=""):
    request = RequestFactory().get("/")
    request.tenant = tenant
    if url_name:
        request.resolver_match = type("M", (), {"url_name": url_name})()
    tpl = Template("{% load siteui %}{% render_block block %}")
    return tpl.render(Context({"request": request, "block": block, "pb_host": host}))


# ───────────── R6a: данные и вывод ─────────────


def test_rubbish_never_reaches_the_config():
    good = str(uuid.uuid4())
    clean = siteconfig._clean_cblock_data
    assert clean("textpage", {"page": good, "mode": "teaser", "x": 1}) == {
        "page": good,
        "mode": "teaser",
    }
    assert clean("textpage", {"page": "<script>", "mode": "all"}) == {}
    assert clean("textpage", None) == {}
    assert clean("contact_card", {"style": "split", "body": "x"}) == {"style": "split"}
    assert clean("contact_card", {"style": "evil"}) == {}


def test_blocks_are_known_everywhere_they_are_drawn():
    from apps.tenants.templatetags import siteui

    for key in ("textpage", "contact_card"):
        assert key in siteconfig.REPEATABLE_BLOCKS
        assert key in siteui.CBLOCK_TEMPLATES and key in siteconfig.CBLOCK_LABELS


def test_full_text_is_shown_with_its_markup():
    tenant = _tenant()
    page = _page(body="<h2>Bar</h2><p>Karte <script>x()</script>geht auch.</p>")
    html = _render(tenant, {"key": "textpage", "id": "t1", "data": {"page": str(page.pk)}})
    # заголовки текста — на уровень ниже названия страницы (оно h2 блока)
    assert "Zahlung" in html and "<h3>Bar</h3>" in html and "<h2>Bar" not in html
    assert "<script>" not in html and "Weiterlesen" not in html


def test_teaser_shows_the_beginning_as_plain_text_with_a_link():
    tenant = _tenant()
    page = _page(body="<p><b>Fett</b> " + "wort " * 200 + "</p>")
    data = {"page": str(page.pk), "mode": "teaser"}
    html = _render(tenant, {"key": "textpage", "id": "t1", "data": data})
    assert "Weiterlesen" in html and "/zahlung/" in html
    assert "<b>" not in html and "…" in html
    assert html.count("wort") < 70


def test_missing_or_unpublished_page_shows_nothing_and_does_not_crash():
    tenant = _tenant()
    hidden = _page(is_published=False)
    for data in ({}, {"page": str(uuid.uuid4())}, {"page": "rubbish"}, {"page": str(hidden.pk)}):
        html = _render(tenant, {"key": "textpage", "id": "t1", "data": data})
        assert "data-block-textpage" not in html


def test_address_change_does_not_break_the_block():
    tenant = _tenant()
    page = _page()
    block = {"key": "textpage", "id": "t1", "data": {"page": str(page.pk)}}
    page.slug = "bezahlen"
    page.save(update_fields=["slug"])
    assert "Wir nehmen Karte" in _render(tenant, block)


def test_page_is_never_shown_inside_itself():
    tenant = _tenant()
    own, about = _page(), _page(slug="ueber-uns", title="Über uns", body="<p>Wir.</p>")
    block = {"key": "textpage", "id": "t1", "data": {"page": str(own.pk)}}
    assert "data-block-textpage" not in _render(tenant, block, host="seite:zahlung")
    assert "data-block-textpage" in _render(tenant, block, host="seite:andere")
    sysblock = {"key": "textpage", "id": "t2", "data": {"page": str(about.pk)}}
    assert "data-block-textpage" not in _render(tenant, sysblock, url_name="storefront-about")
    assert content_pages.embeds_itself("versand", "versand")
    assert not content_pages.embeds_itself("versand", "info")


def test_contact_block_draws_the_business_card():
    tenant = _tenant(address="Hauptstr. 1\n42651 Solingen", opening_hours="Mo–Fr 9–18")
    html = _render(tenant, {"key": "contact_card", "id": "c1", "data": {}})
    assert "Hauptstr. 1" in html and "Mo–Fr 9–18" in html
    compact = _render(tenant, {"key": "contact_card", "id": "c1", "data": {"style": "compact"}})
    assert "Hauptstr. 1" in compact and "rounded-2xl shadow-sm" not in compact


def test_studio_save_keeps_the_data_of_both_blocks():
    good = str(uuid.uuid4())
    post = QueryDict(mutable=True)
    post.update({"cb_x_page": good, "cb_x_mode": "teaser", "cb_y_style": "split"})
    assert views._read_cblock_data(post, "x", "textpage") == {"page": good, "mode": "teaser"}
    assert views._read_cblock_data(post, "y", "contact_card") == {"style": "split"}


# ───────────── R6b: панель ─────────────


def test_panel_offers_pages_but_not_the_one_the_block_stands_on():
    tenant = _tenant()
    own, other = _page(), _page(slug="lieferung", title="Lieferung")
    draft = _page(slug="bald", title="Bald", is_published=False)
    code = "text@seite:zahlung"
    ref = site_schema.apply(tenant, code, "add", block_type="textpage")
    html = Browser(tenant).get(f"?seite={code}&block={ref}")
    assert f'value="{other.pk}"' in html and f'value="{own.pk}"' not in html
    assert f'value="{draft.pk}"' in html and "Bald (Entwurf)" in html
    assert 'name="f_mode"' in html and "data-schema-source" in html


def test_update_refuses_the_own_page_and_unknown_pages():
    tenant = _tenant()
    own, other = _page(), _page(slug="lieferung", title="Lieferung")
    code = "text@seite:zahlung"
    ref = site_schema.apply(tenant, code, "add", block_type="textpage")
    for bad in (str(own.pk), str(uuid.uuid4()), "<x>"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.apply(tenant, code, "update", ref=ref, fields={"page": bad})
    site_schema.apply(
        tenant, code, "update", ref=ref, fields={"page": str(other.pk), "mode": "teaser"}
    )
    assert _blocks(tenant, "seite:zahlung")[0]["data"] == {"page": str(other.pk), "mode": "teaser"}


def test_deleted_page_stays_selected_in_the_panel_and_is_named_in_the_row():
    tenant = _tenant()
    page = _page()
    ref = site_schema.apply(tenant, "text", "add", block_type="textpage")
    site_schema.apply(tenant, "text", "update", ref=ref, fields={"page": str(page.pk)})
    browser = Browser(tenant)
    assert "Zahlung" in browser.get("?seite=text")
    pk = str(page.pk)
    page.delete()
    html = browser.get(f"?seite=text&block={ref}")
    assert f'<option value="{pk}" selected>' in html and "nicht verfügbar" in html
    assert "Seite nicht mehr vorhanden" in html
    # «Übernehmen» без правок блок не меняет (W0)
    browser.post(seite="text", op="update", ref=ref, panel_present="1", f_page=pk, f_mode="")
    assert "data-schema-draft" not in browser.get("?seite=text")


def test_contact_panel_changes_only_the_look():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "catalog", "add", block_type="contact_card")
    html = Browser(tenant).get(f"?seite=catalog&block={ref}")
    assert 'name="f_style"' in html and 'value="map_first"' in html
    site_schema.apply(tenant, "catalog", "update", ref=ref, fields={"style": "compact"})
    assert _blocks(tenant, "catalog")[0]["data"] == {"style": "compact"}
    widths = [v for v, _lab in site_schema.width_choices({"key": "contact_card", "id": "c"})]
    assert widths == ["contained", "w23", "w12"]


# ───────────── R6c: меню «+ Block» и готовые строки ─────────────


@pytest.mark.parametrize("code", ["home", "text", "catalog"])
def test_every_addable_block_is_in_exactly_one_menu_group(code):
    grouped = [k for g in site_schema.add_groups(code) for k, _lab in g["options"]]
    assert sorted(grouped) == sorted(k for k, _lab in site_schema.add_options(code))
    assert len(grouped) == len(set(grouped))


def test_menu_is_drawn_in_groups_with_ready_rows():
    html = Browser(_tenant()).get("?seite=text")
    assert html.count("<optgroup") >= 3 and "Von anderen Stellen" in html
    assert "data-schema-add-row" in html
    for label in ("Text + Foto", "Foto + Text", "Drei Karten", "Text + Kontakt"):
        assert label in html


@pytest.mark.parametrize("preset", list(site_schema.ROW_PRESETS))
def test_every_ready_row_survives_normalize_and_stands_in_one_row(preset):
    blocks = site_schema.preset_blocks(preset)
    cfg = siteconfig.normalize({"page_blocks": {"info": blocks}})
    saved = [b for b in cfg["page_blocks"]["info"] if b.get("id")]
    assert [(b["key"], b["width"], b["data"]) for b in saved] == [
        (b["key"], b["width"], b["data"]) for b in blocks
    ]
    rows = [r for r in siteconfig.group_block_rows(saved) if r.get("key") == "_row"]
    assert len(rows) == 1 and len(rows[0]["row"]) == len(blocks)
    assert saved[0].get("newline") is True


def test_ready_row_goes_through_the_draft():
    tenant = _tenant()
    browser = Browser(tenant)
    resp, _msgs = browser.post(seite="text", op="add_row", value="text_contact")
    assert resp.status_code == 302 and _blocks(tenant) == []
    browser.post(seite="text", op="save")
    assert [b["key"] for b in _blocks(tenant)] == ["text", "contact_card"]


def test_unknown_row_is_refused_and_a_full_page_takes_no_half_row():
    tenant = _tenant()
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "text", "add_row", value="nope")
    items = [{"key": "text", "id": f"b{i}", "data": {}} for i in range(siteconfig._MAX_CBLOCKS - 1)]
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "text", "add_row", value="three_cards")
    assert len(items) == siteconfig._MAX_CBLOCKS - 1


def test_same_page_in_many_blocks_costs_one_query():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    tenant = _tenant()
    page = _page()
    request = RequestFactory().get("/")
    request.tenant = tenant
    tpl = Template("{% load siteui %}{% for b in blocks %}{% render_block b %}{% endfor %}")
    blocks = [{"key": "textpage", "id": f"t{i}", "data": {"page": str(page.pk)}} for i in range(5)]
    with CaptureQueriesContext(connection) as ctx:
        html = tpl.render(Context({"request": request, "blocks": blocks}))
    assert html.count("data-block-textpage") == 5
    assert sum("core_contentpage" in q["sql"] for q in ctx) == 1


def test_full_page_says_so_instead_of_dropping_the_block_silently():
    tenant = _tenant()
    browser = Browser(tenant)
    for _i in range(siteconfig._MAX_CBLOCKS):
        browser.post(seite="text", op="add", type="spacer")
    _resp, msgs = browser.post(seite="text", op="add", type="spacer")
    assert any("kein Platz" in m for m in msgs)
    _resp, msgs = browser.post(seite="text", op="add_row", value="three_cards")
    assert any("kein Platz" in m for m in msgs)


def test_untouched_panel_never_changes_the_new_blocks():
    tenant = _tenant()
    page = _page()
    a = site_schema.apply(tenant, "text", "add", block_type="textpage")
    site_schema.apply(tenant, "text", "update", ref=a, fields={"page": str(page.pk)})
    b = site_schema.apply(tenant, "text", "add", block_type="contact_card")
    before = Tenant.objects.get(pk=tenant.pk).site_config
    browser = Browser(tenant)
    browser.post(
        seite="text", op="update", ref=a, panel_present="1", f_page=str(page.pk), f_mode=""
    )
    browser.post(seite="text", op="update", ref=b, panel_present="1", f_style="")
    assert "data-schema-draft" not in browser.get("?seite=text")
    assert Tenant.objects.get(pk=tenant.pk).site_config == before


def test_own_contact_block_replaces_the_fixed_card_on_about():
    from apps.tenants.templatetags.siteui import has_page_block

    block = {"key": "contact_card", "id": "c1", "enabled": True, "data": {}}
    assert has_page_block({"page_blocks": {"info": [block]}}, "info:contact_card")
    assert not has_page_block(
        {"page_blocks": {"info": [{**block, "enabled": False}]}}, "info:contact_card"
    )
    assert not has_page_block({"page_blocks": {"catalog": [block]}}, "info:contact_card")
    assert not has_page_block({}, "info:contact_card")


def test_two_contact_blocks_get_their_own_map():
    tenant = _tenant(address="Hauptstr. 1", latitude=51.17, longitude=7.08)
    one = _render(tenant, {"key": "contact_card", "id": "c1", "data": {}})
    two = _render(tenant, {"key": "contact_card", "id": "c2", "data": {}})
    assert "sf-contact-map-c1" in one and "sf-contact-map-c2" in two


def test_page_key_is_not_offered_for_translation():
    assert not siteconfig._is_translatable_field("page")
    assert not siteconfig._is_translatable_field("mode")
