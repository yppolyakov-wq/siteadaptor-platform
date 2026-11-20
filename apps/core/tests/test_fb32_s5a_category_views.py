"""FB-32 S5a: один список видов «Kategorien» на главной и в каталоге — виды, которых на
этой странице (пока) нет, видны с причиной и не выбираются (решение владельца: «Reiter» и
«Seitenspalte» на главной — недоступны)."""

import re

import pytest

from apps.core import block_views
from apps.core.tests.test_fb27_builtin_panel import _tenant
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_registry_covers_both_pages_view_values():
    from apps.core.site_schema import CATEGORY_VIEW_CHOICES

    home = {v.home for v in block_views.CATEGORY_VIEWS if v.home is not None}
    catalog = {v.catalog for v in block_views.CATEGORY_VIEWS if v.catalog is not None}
    assert home == {"", *siteconfig.SECTION_STYLES["categories"]}
    assert catalog == {v for v, *_rest in CATEGORY_VIEW_CHOICES}


def test_home_shows_catalog_views_disabled_with_reason():
    html = Browser(_tenant()).get("?seite=home&block=categories")
    for key in ("tabs", "side"):
        assert f'data-schema-style-off="{key}"' in html
    # FB-32 S5b: «Regale», «Index», «Wegweiser» на главной теперь выбираются
    for key in ("regale", "index", "wegweiser"):
        assert f'name="f_style" value="{key}"' in html
    assert "Nur auf Katalogseiten" in html
    assert 'name="f_style" value="tabs"' not in html


def test_catalog_shows_home_tile_forms_disabled_with_reason():
    html = Browser(_tenant()).get("?seite=catalog&block=categories")
    assert "Vorerst nur auf der Startseite." in html
    for key in ("square", "tall", "wide", "compact"):
        assert f'data-style-thumb="{key}"' in html


def test_disabled_view_cannot_be_posted_on_catalog():
    from apps.core import aufbau_draft

    b = Browser(_tenant())
    for value in ("home:square", ""):
        _resp, msgs = b.post(seite="catalog", op="catview", ref="categories", value=value)
        assert msgs, "отказ с сообщением"
    req = b._request("get")
    assert not aufbau_draft.get(req, "catalog"), "черновик не появился"


def test_catalog_views_on_home_hide_columns_and_output_but_keep_them():
    from apps.core.tests.test_fb27_builtin_panel import _row

    b = Browser(_tenant())
    b.post(
        seite="home", op="update", ref="categories", panel_present="1", f_cols="2", f_out="slider"
    )
    b.post(seite="home", op="update", ref="categories", panel_present="1", f_style="regale")
    html = b.get("?seite=home&block=categories")
    # FB-33 M3-3c: форма «zurücksetzen» шлёт пустые вид/вывод/колонки/ряды осознанно —
    # замок о формах правки
    html = re.sub(r"<form[^>]*data-schema-reset-form.*?</form>", "", html, flags=re.S)
    assert 'name="f_cols"' not in html and 'name="f_out"' not in html
    assert 'name="f_style"' in html
    b.post(
        seite="home",
        op="update",
        ref="categories",
        panel_present="1",
        f_style="regale",
        f_limit="5",
    )
    b.post(seite="home", op="save")
    row = _row(b.tenant, "categories")
    assert row["style"] == "regale" and row["layout"]["cols"] == 2, "скрытые значения не стёрты"
