"""FB-32 S1: вид встроенного списка главной («Aktuelle Angebote», «Produkte», «Kategorien»)
снова выбирается в «Seitenaufbau» — выпадающим списком со схемами, как вид баннера
(решение владельца 2026-11-17, `docs/fb32-unified-blocks-plan-2026-11-17.md`)."""

import pytest

from apps.core import site_schema
from apps.core.tests.test_fb27_builtin_panel import _row, _tenant
from apps.core.tests.test_fb27_r2_draft import Browser

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_categories_panel_has_the_view_dropdown_with_pictures():
    html = Browser(_tenant()).get("?seite=home&block=categories")
    # FB-33 M3-3c: во вкладке «Wie anordnen» виды — открытыми плитками (было: выпадающий список)
    assert 'data-schema-view-tiles="style"' in html and 'name="f_style"' in html
    for key in ("square", "tall", "wide", "compact"):
        assert f'data-style-thumb="{key}"' in html


def test_owner_picks_a_view_and_it_reaches_the_site_and_the_row_caption():
    b = Browser(_tenant())
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="tall")
    assert _row(b.tenant, "categories").get("style") != "tall", "сначала черновик"
    b.post(seite="home", op="save")
    row = _row(b.tenant, "categories")
    assert row["style"] == "tall"
    assert "Hochformat" in site_schema._row_summary({}, row)
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="")
    b.post(seite="home", op="save")
    assert "style" not in _row(b.tenant, "categories")


def test_foreign_or_junk_view_is_not_stored():
    b = Browser(_tenant())
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="spotlight")
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="<x>")
    b.post(seite="home", op="save")
    assert "style" not in _row(b.tenant, "categories")


def test_untouched_view_field_does_not_change_the_row():
    b = Browser(_tenant())
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="square")
    b.post(seite="home", op="save")
    before = _row(b.tenant, "categories")
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="square")
    b.post(seite="home", op="save")
    assert _row(b.tenant, "categories") == before
