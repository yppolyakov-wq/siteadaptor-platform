"""FB-27 «Seitenaufbau», доводка по макету: вид «Telefon» и способ «Welche» переживают
действие с блоком; правка в панели без «Übernehmen» (скрипт поверх работающей формы);
ссылка на источник списка."""

import pathlib

import pytest

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _list(browser):
    return site_schema.apply(browser.tenant, "text", "add", block_type="list")


def test_phone_view_survives_an_action():
    b = Browser(_tenant())
    ref = _list(b)
    resp, _msgs = b.post(seite="text", op="hide", ref=ref, ansicht="telefon")
    assert "ansicht=telefon" in resp["Location"]
    html = b.get(f"?seite=text&block={ref}&ansicht=telefon")
    # каждая форма страницы несёт вид с собой, ссылки — тоже
    assert html.count('name="ansicht" value="telefon"') >= html.count('method="post"')
    assert "welche=regel&amp;ansicht=telefon" in html or "ansicht=telefon&amp;welche" in html


def test_computer_view_adds_nothing():
    b = Browser(_tenant())
    ref = _list(b)
    resp, _msgs = b.post(seite="text", op="hide", ref=ref)
    assert "ansicht" not in resp["Location"]
    assert 'name="ansicht"' not in b.get(f"?seite=text&block={ref}")


def test_rubbish_view_and_mode_are_not_echoed():
    b = Browser(_tenant())
    ref = _list(b)
    resp, _msgs = b.post(
        seite="text", op="hide", ref=ref, ansicht="//evil.example", welche='"><script>'
    )
    assert "evil" not in resp["Location"] and "script" not in resp["Location"]


def test_which_mode_survives_an_update():
    b = Browser(_tenant())
    ref = _list(b)
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_source="products")
    html = b.get(f"?seite=text&block={ref}&welche=kategorie")
    assert 'name="welche" value="kategorie"' in html
    resp, _msgs = b.post(
        seite="text", op="update", ref=ref, panel_present="1", welche="kategorie", f_limit="5"
    )
    assert "welche=kategorie" in resp["Location"]


def test_list_panel_links_to_the_source_screen():
    b = Browser(_tenant())
    ref = _list(b)
    b.post(seite="text", op="update", ref=ref, panel_present="1", f_source="products")
    html = b.get(f"?seite=text&block={ref}")
    assert "data-schema-source" in html and "/products/" in html


def test_apply_button_stays_for_no_script_and_script_only_enhances():
    tpl = pathlib.Path("templates/tenant/site_schema.html").read_text()
    assert tpl.count('value="update"') >= 2  # без скриптов кнопка остаётся
    js = pathlib.Path("static/js/aufbau.js").read_text()
    assert "data-schema-list" in js and "fetch(" in js
    # сбой запроса не теряет правку: обычная отправка формы
    assert "requestSubmit" in js
