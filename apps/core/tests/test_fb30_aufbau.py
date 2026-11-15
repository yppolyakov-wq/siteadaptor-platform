"""FB-30.2–30.5: «Seitenaufbau» — вид баннера без «Übernehmen», доля узкого блока в списке,
понятные способы и заголовки панели списка."""

import pathlib

import pytest

from apps.core import list_panel, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- 30.2 ---


def test_page_type_settings_apply_without_the_extra_button():
    js = pathlib.Path("static/js/aufbau.js").read_text()
    assert "[data-schema-setting]" in js.split("var FORMS =", 1)[1].split(";", 1)[0]
    assert "[data-schema-setting]:not([data-schema-manual])" in js, "вывод списка — с кнопкой"
    settings = pathlib.Path("templates/tenant/_schema_settings.html").read_text()
    assert '{% if s.kind == "layout" %} data-schema-manual{% endif %}' in settings
    assert 'if (!form.matches("[data-schema-setting]")) data.set("op", "update")' in js
    html = Browser(_tenant()).get("?seite=home&block=hero")
    form = html[html.index('data-schema-setting="') :]
    form = form[: form.index("</form>")]
    assert 'name="op" value="setting"' in form, "своя операция настройки"
    assert "data-schema-apply" in form, "без скриптов кнопка остаётся"
    assert 'id="st-' in form, "у переключателей есть id — фокус возвращается в свою форму"


# --- 30.3 ---


def test_narrow_block_takes_its_share_in_the_structure_list():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="text")
    site_schema.apply(tenant, "text", "width", ref=ref, value="w12")
    html = Browser(tenant).get("?seite=text")
    row = html[html.index(f'data-schema-drag="{ref}"') - 200 :][:420]
    assert "flex: 0 1 50%" in row and 'data-schema-share="50"' in row
    wide = site_schema.apply(tenant, "text", "add", block_type="text")
    html = Browser(tenant).get("?seite=text")
    row = html[html.index(f'data-schema-drag="{wide}"') - 200 :][:420]
    assert "data-schema-share" not in row.split(f'data-schema-drag="{wide}"')[1][:40]


# --- 30.4, 30.5 ---


def test_category_list_names_its_ways_by_what_they_show():
    mode, modes = list_panel.which_mode("categories", {}, "")
    assert [str(m["label"]) for m in modes] == ["Alle", "Unterkategorien", "Von Hand"]
    _mode, modes = list_panel.which_mode("products", {}, "")
    assert [str(m["label"]) for m in modes] == ["Automatisch", "Aus einer Kategorie", "Von Hand"]


def test_group_headings_name_the_source():
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="list")
    html = Browser(tenant).get(f"?seite=text&block={ref}")
    label = str(siteconfig.LIST_SOURCES[siteconfig.LIST_SOURCE_DEFAULT]["label"])
    assert f"Welche {label} gezeigt werden" in html and f"Wie {label} aussehen" in html
    assert ">Welche<" not in html and ">Wie<" not in html
    assert html.count('data-schema-group="wie"') == 1
    assert "nach „Übernehmen“" not in html


# --- 30.6 ---


def test_banner_style_is_a_dropdown_with_a_sketch_per_style():
    b = Browser(_tenant())
    html = b.get("?seite=home&block=hero")
    box = html[html.index('data-schema-setting-box="home_hero"') :]
    box = box[: box.index("</details>")]
    head = box[: box.index("</summary>")]
    assert " open" not in box[: box.index(">")], "закрыт: виден выбранный вид со схемой"
    assert head.count("data-hero-thumb=") == 1
    for style in siteconfig.HERO_STYLES:
        assert box.count(f'data-hero-thumb="{style}"') >= 1, style
    assert box.count("data-hero-thumb=") == len(siteconfig.HERO_STYLES) + 1
    # после выбора список остаётся раскрытым — владелец видит, что выбрано
    opened = b.get("?seite=home&block=hero&offen=home_hero")
    opened = opened[opened.index('data-schema-setting-box="home_hero"') :]
    assert " open" in opened[: opened.index(">")]
