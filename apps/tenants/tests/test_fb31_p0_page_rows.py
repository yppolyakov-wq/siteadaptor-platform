"""FB-31 P0: страницы, кроме главной, хранят встроенные строки-списки (как главная) и поля
маркера ★. До P0 `normalize_page_blocks` молча выкидывал всё, кроме C-блоков, ссылочных секций
и голого маркера, — блок «Kategorien» на странице каталога терялся при сохранении."""

import pytest

from apps.tenants import siteconfig

CAT = {"key": "categories", "enabled": True, "style": "compact", "layout": {"cols": 4}}


def _norm(host, items):
    return siteconfig.normalize_page_blocks({host: items}).get(host, [])


@pytest.mark.parametrize("host", ["catalog", "catalog:brot"])
def test_catalog_hosts_keep_a_categories_row(host):
    rows = _norm(host, [CAT, {"key": "main"}])
    assert [r["key"] for r in rows] == ["categories", "main"]
    assert rows[0]["style"] == "compact" and rows[0]["enabled"] is True


def test_other_hosts_still_drop_it_and_duplicates_collapse():
    assert _norm("info", [CAT]) == []
    rows = _norm("catalog", [CAT, dict(CAT), {"key": "main"}])
    assert [r["key"] for r in rows] == ["categories", "main"]


def test_junk_in_the_row_is_cleaned_like_on_the_home_page():
    rows = _norm("catalog", [{**CAT, "style": "<script>", "bogus": 1}, {"key": "main"}])
    assert "style" not in rows[0] and "bogus" not in rows[0]


def test_main_marker_keeps_its_view_fields_even_in_first_place():
    rows = _norm("catalog", [{"key": "main", "style": "mosaik", "focus": True, "grid": "cols4"}])
    assert rows == [{"key": "main", "style": "mosaik", "focus": True, "grid": "cols4"}]
    plain = _norm("catalog", [{"key": "main"}, {"key": "text", "id": "t1", "data": {"text": "x"}}])
    assert plain[0]["key"] == "text", "голый маркер первым по-прежнему не храним (как раньше)"


def test_main_marker_drops_unknown_values():
    rows = _norm("catalog", [{"key": "main", "style": "gold", "grid": "x", "focus": "yes"}])
    assert rows == []


@pytest.mark.django_db
def test_structure_screen_and_studio_keep_the_rows(settings):
    """Экран «Seitenaufbau» открывается с такой строкой, а сохранение порядка/черновика её
    не теряет."""
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    rows = [CAT, {"key": "main", "style": "mosaik"}]
    tenant = TenantFactory(disabled_modules=[], site_config={"page_blocks": {"catalog": rows}})
    html = Browser(tenant).get("?seite=catalog")
    assert "schema" in html  # экран отрисовался
    from apps.core import site_schema

    saved = siteconfig.normalize(tenant.site_config)["page_blocks"]["catalog"]
    # Студия прислала форму без этих строк (у неё нет такого блока) — строки остаются
    merged = site_schema.merge_structure(saved, [])
    assert [r["key"] for r in merged] == ["categories", "main"]
    assert merged[1].get("style") == "mosaik"
