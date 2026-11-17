"""FB-32 S2: «Полоса доверия» правится в панели «Seitenaufbau» — пункты (иконка кнопкой,
заголовок, текст), удалить, выше/ниже, «＋ Punkt», вид — общим выпадающим списком (макет S2).
Хранение прежнее — `usp_bar`; правки идут в черновик и на сайт по «Speichern»."""

import pytest

from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _cfg, _tenant
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

USP = [
    {"icon": "bio", "label": "Bio"},
    {"icon": "local", "label": "Regional", "text": "aus dem Bergischen"},
]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _with_usp():
    tenant = _tenant()
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["usp_bar"] = USP
    for s in cfg["sections"]:
        if s["key"] == "usp_bar":
            s["enabled"] = True
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    return Browser(tenant)


def _form(**extra):
    base = {
        "seite": "home", "op": "update", "ref": "usp_bar", "panel_present": "1",
        "f_usp_0_icon": "bio", "f_usp_0_label": "Bio", "f_usp_0_text": "",
        "f_usp_1_icon": "local", "f_usp_1_label": "Regional", "f_usp_1_text": "aus dem Bergischen",
    }  # fmt: skip
    return {**base, **extra}


def test_panel_shows_items_with_icon_buttons_and_an_empty_slot():
    html = _with_usp().get("?seite=home&block=usp_bar")
    assert "data-schema-usp" in html and 'value="Regional"' in html
    assert 'name="f_usp_0_icon" value="bio"' in html and "data-schema-usp-new" in html
    assert 'name="f_usp_2_label"' in html, "пустая строка «＋ Punkt»"


def test_add_edit_and_save_reach_the_site():
    b = _with_usp()
    b.post(**_form(f_usp_2_icon="clock", f_usp_2_label="Ab 6 Uhr", f_usp_1_label="Regional!"))
    assert _cfg(b.tenant)["usp_bar"] == USP, "сначала черновик"
    b.post(seite="home", op="save")
    usp = _cfg(b.tenant)["usp_bar"]
    assert [u["label"] for u in usp] == ["Bio", "Regional!", "Ab 6 Uhr"]
    assert usp[2]["icon"] == "clock"
    row = next(s for s in _cfg(b.tenant)["sections"] if s["key"] == "usp_bar")
    assert "data" not in row, "пункты хранятся в одном месте — `usp_bar`"


def test_remove_and_move():
    b = _with_usp()
    b.post(**_form(f_usp_move="1:up"))
    b.post(seite="home", op="save")
    assert [u["label"] for u in _cfg(b.tenant)["usp_bar"]] == ["Regional", "Bio"]
    b.post(**_form(f_usp_0_label="Regional", f_usp_1_label="Bio", f_usp_remove="0"))
    b.post(seite="home", op="save")
    assert [u["label"] for u in _cfg(b.tenant)["usp_bar"]] == ["Bio"]


def test_view_and_junk():
    b = _with_usp()
    b.post(**_form(f_style="pillars", f_usp_0_icon="<x>"))
    b.post(seite="home", op="save")
    cfg = _cfg(b.tenant)
    row = next(s for s in cfg["sections"] if s["key"] == "usp_bar")
    assert row["style"] == "pillars" and cfg["usp_bar"][0]["icon"] == "check"
    b.post(**_form(f_style="spotlight"))
    b.post(seite="home", op="save")
    assert (
        next(s for s in _cfg(b.tenant)["sections"] if s["key"] == "usp_bar")["style"] == "pillars"
    )


def test_review_move_or_remove_without_rows_keeps_the_points():
    b = _with_usp()
    b.post(seite="home", op="update", ref="usp_bar", panel_present="1", f_usp_remove="0")
    b.post(seite="home", op="update", ref="usp_bar", panel_present="1", f_usp_move="0:down")
    b.post(seite="home", op="save")
    assert _cfg(b.tenant)["usp_bar"] == USP


def test_review_item_buttons_work_and_enter_means_apply():
    b = _with_usp()
    html = b.get("?seite=home&block=usp_bar")
    form = html[html.index("data-schema-usp") :]
    first_button = form[form.index("<button") : form.index("</button>")]
    assert 'value="update"' in first_button, "Enter в поле — «Übernehmen»"
    assert '<input type="hidden" name="op" value="update">' in form
    form_data = _form(f_usp_move="0:down")
    form_data.pop("op")
    b.post(op="update", **{k: v for k, v in form_data.items()})
    b.post(seite="home", op="save")
    assert [u["label"] for u in _cfg(b.tenant)["usp_bar"]] == ["Regional", "Bio"]


def test_review_stale_studio_tab_keeps_points_saved_in_the_schema():
    from apps.core import site_schema

    b = _with_usp()
    old_hash = site_schema.structure_hash(b.tenant.site_config)
    b.post(**_form(f_usp_0_label="Neu"))
    b.post(seite="home", op="save")
    assert site_schema.structure_hash(_cfg(b.tenant)) != old_hash, "правка пунктов видна отпечатку"
