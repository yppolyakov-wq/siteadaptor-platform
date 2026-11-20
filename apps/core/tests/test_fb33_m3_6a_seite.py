"""FB-33 M3-6a (макет M0-11): «Einstellungen der Seite» окном с вкладкой «Seite»; SEO страницы
во «Texte» через черновик (только текстовые хосты); строка наследования вида у категории.

Замки C0 (до кода — strict-xfail): окно `__page` и «Abbrechen» байт-в-байт; формы настроек —
те же, что у прежней колонки; `__page` не правится операциями схемы; SEO — в черновике, запись
по «Speichern» одним писателем; черновик, начатый до среза, не конфликтует.
"""

import json
import re

import pytest

from apps.core import aufbau_draft, content_pages, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import (
    CFG,
    GOLDEN,
    _forms,
    _old_panel,
    _panel,
)
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _shop(config=None):
    tenant = _tenant()
    tenant.site_config = config if config is not None else CFG
    tenant.save()
    return tenant


class _Req:
    def __init__(self, session):
        self.session = session


def _raw(browser, code="text"):
    return (browser.session.get(aufbau_draft.SESSION_KEY) or {}).get(code)


def _tabs(html):
    return re.findall(r'data-window-tab="([a-z]+)"( hidden)?', _panel(html))


def _token(html):
    return re.search(r'name="wopen" value="([A-Za-z0-9_-]+)"', _panel(html)).group(1)


# ───────────── C1: «Einstellungen der Seite» окном ─────────────


def test_page_row_opens_the_block_window_on_the_seite_tab():
    b = Browser(_shop())
    html = b.get("?seite=text&block=__page")
    panel = _panel(html)
    assert 'value="window_done"' in panel and 'value="revert"' in panel, "окно с Fertig/Abbrechen"
    assert re.search(r'<h2 id="schema-panel-title"[^>]*>Einstellungen der Seite</h2>', panel)
    assert ("seite", "") in _tabs(html), "вкладка «Seite» открыта"
    assert "data-schema-more" not in panel, "строку не скрыть и не удалить — меню «⋯» нет"
    # строка в списке слева — прежняя ссылка
    assert 'data-schema-block="__page" aria-current="true"' in html


def test_settings_forms_are_the_old_column_forms_byte_for_byte():
    """Правка из окна даёт тот же черновик: формы прежней колонки — те же (без токена)."""
    want = json.loads(GOLDEN.read_text())["text|__page"]["forms"]
    html = Browser(_shop()).get("?seite=text&block=__page")
    got = _forms(_old_panel(_panel(html)))
    for form in want:
        assert form in got


def test_page_row_has_no_schema_ops_and_no_remove_confirm():
    tenant = _shop()
    b = Browser(tenant)
    for op in ("toggle", "up", "down", "delete", "width", "duplicate"):
        _resp, msgs = b.post(seite="text", op=op, ref="__page", value="half")
        assert msgs == ["Diese Änderung ist hier nicht möglich."], op
    assert _raw(b) is None
    html = b.get("?seite=text&block=__page&entfernen=1")
    assert "data-schema-confirm" not in html and 'value="window_done"' in html


def test_page_row_mutate_is_refused():
    items = []
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(items, "text", "toggle", site_schema.PAGE_REF)


def test_page_window_without_settings_has_no_row():
    """Нет настроек у страницы — нет и строки «Seite»: адрес `block=__page` — «Block wählen»."""
    tenant = _shop()
    b = Browser(tenant)
    html = b.get("?seite=team&block=__page")
    if 'data-schema-block="__page"' in html:
        pytest.skip("у «Team» есть настройки")
    assert 'value="window_done"' not in _panel(html)


def _layout(panel):
    """Первая настройка панели и значение, отличное от выбранного."""
    setting = re.search(r'name="setting" value="([a-z_]+)"', panel).group(1)
    form = panel[panel.index(f'data-schema-setting="{setting}"') :]
    form = form[: form.index("</form>")]
    radios = re.findall(r'<input type="radio"[^>]*name="value" value="([^"]*)"([^>]*)>', form)
    other = next(v for v, rest in radios if "checked" not in rest)
    return setting, other


def test_fertig_closes_and_abbrechen_restores_the_setting_byte_for_byte():
    tenant = _shop()
    b = Browser(tenant)
    html = b.get("?seite=product&block=__page")
    setting, other = _layout(_panel(html))
    token = _token(html)
    assert _raw(b, "product") is None
    resp, _m = b.post(
        seite="product", op="setting", ref="__page", setting=setting, value=other, wopen=token
    )
    assert resp.status_code == 302
    assert "__page" in (_raw(b, "product").get("window") or {}), "снимок окна «Seite»"
    resp, msgs = b.post(seite="product", op="revert", ref="__page", wopen=token)
    assert msgs == ["Änderungen an diesem Block zurückgenommen."]
    assert "block=" not in resp["Location"]
    assert aufbau_draft.get(_Req(b.session), "product") is None, "черновик — как до открытия"


def test_abbrechen_restores_the_earlier_draft_value_of_the_setting():
    """Снимок помнит прежнее значение настройки в черновике (до первой правки окна)."""
    tenant = _shop()
    b = Browser(tenant)
    panel = _panel(b.get("?seite=product&block=__page"))
    setting, other = _layout(panel)
    form = panel[panel.index(f'data-schema-setting="{setting}"') :]
    radios = re.findall(r'<input type="radio"[^>]*name="value" value="([^"]*)"([^>]*)>', form)
    current = next(v for v, rest in radios if "checked" in rest)
    b.post(seite="product", op="setting", ref="__page", setting=setting, value=other)  # без окна
    saved_settings = json.dumps(_raw(b, "product").get("settings"), sort_keys=True)
    token = _token(b.get("?seite=product&block=__page"))
    b.post(seite="product", op="setting", ref="__page", setting=setting, value=current, wopen=token)
    assert not _raw(b, "product").get("settings"), "вернули сохранённое — настройки в черновике нет"
    b.post(seite="product", op="revert", ref="__page", wopen=token)
    assert json.dumps(_raw(b, "product").get("settings"), sort_keys=True) == saved_settings
    assert "__page" not in (_raw(b, "product").get("window") or {})


def test_window_done_on_page_row_drops_the_snapshot():
    tenant = _shop()
    b = Browser(tenant)
    token = _token(b.get("?seite=text&block=__page"))
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="A", wopen=token)
    assert "__page" in (_raw(b).get("window") or {})
    resp, _m = b.post(seite="text", op="window_done", ref="__page", wopen=token)
    assert "block=" not in resp["Location"]
    assert "__page" not in (_raw(b).get("window") or {})


# ───────────── C2: SEO страницы во «Texte» ─────────────


def test_seo_part_only_on_text_hosts():
    tenant = _shop()
    b = Browser(tenant)
    text = _panel(b.get("?seite=text&block=__page"))
    assert 'id="bw-form-seo"' in text and 'name="f_seo_title"' in text
    assert 'maxlength="70"' in text and 'maxlength="200"' in text
    cart = _panel(b.get("?seite=cart&block=__page"))
    assert "f_seo_title" not in cart
    product = _panel(b.get("?seite=product&block=__page"))
    assert "f_seo_title" not in product


def test_seo_edit_goes_to_the_draft_and_save_writes_it_keeping_noindex():
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt", "noindex": True}}}})
    b = Browser(tenant)
    token = _token(b.get("?seite=text&block=__page&tab=texte"))
    b.post(
        seite="text",
        op="update",
        ref="__page",
        panel_present="1",
        f_seo_title="  Neu   Titel ",
        f_seo_description="Beschreibung",
        wopen=token,
    )
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["pages"]["info"] == {"title": "Alt", "noindex": True}
    assert _raw(b)["seo"] == {"title": "Neu Titel", "description": "Beschreibung", "noindex": True}
    html = b.get("?seite=text&block=__page&tab=texte")
    assert 'value="Neu Titel"' in html and "Änderungen: 1" in html
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == ["Gespeichert."]
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["pages"]["info"] == {
        "title": "Neu Titel",
        "description": "Beschreibung",
        "noindex": True,
    }


def test_seo_back_to_saved_means_no_draft_and_abbrechen_restores():
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt"}}}})
    b = Browser(tenant)
    token = _token(b.get("?seite=text&block=__page"))
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="X", wopen=token)
    assert _raw(b)["seo"]["title"] == "X"
    b.post(
        seite="text", op="update", ref="__page", panel_present="1", f_seo_title="Alt", wopen=token
    )
    assert aufbau_draft.get(_Req(b.session), "text") is None, "вернули как было — правки нет"
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="Y", wopen=token)
    b.post(seite="text", op="revert", ref="__page", wopen=token)
    assert aufbau_draft.get(_Req(b.session), "text") is None


def test_seo_changed_on_the_pages_screen_is_a_conflict():
    tenant = _shop()
    b = Browser(tenant)
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="Mein")
    content_pages.save_page_seo(tenant, "info", {"title": "Anders"})
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == [
        "Diese Seite wurde inzwischen an anderer Stelle geändert. Ihr Entwurf wurde nicht "
        "gespeichert."
    ]
    tenant.refresh_from_db()
    assert tenant.site_config["seo"]["pages"]["info"] == {"title": "Anders"}


def test_a_draft_started_before_the_slice_is_not_a_conflict():
    """Живые черновики после деплоя: без ключа `seo` отпечаток считается без него."""
    tenant = _shop({**CFG, "seo": {"pages": {"info": {"title": "Alt"}}}})
    b = Browser(tenant)
    b.post(seite="text", op="toggle", ref="tp1")
    draft = _raw(b)
    draft.pop("seo")
    config = siteconfig.normalize(tenant.site_config)
    saved = aufbau_draft._saved_state(config, False, "info")
    draft["base"] = aufbau_draft._base_fingerprint(saved, config, draft)
    b.session[aufbau_draft.SESSION_KEY] = {"text": draft}
    assert aufbau_draft.info(_Req(b.session), config, "text")["conflict"] is False
    # и правка SEO в таком черновике — без ложного конфликта
    b.post(seite="text", op="update", ref="__page", panel_present="1", f_seo_title="Neu")
    assert aufbau_draft.info(_Req(b.session), config, "text")["conflict"] is False
    _resp, msgs = b.post(seite="text", op="save")
    assert msgs == ["Gespeichert."]


def test_save_page_seo_and_commit_use_one_writer():
    src = open("apps/core/content_pages.py").read()
    body = src[src.index("def save_page_seo") :]
    body = body[: body.index("\ndef ")]
    assert "put_page_seo(config, host, entry)" in body
    draft_src = open("apps/core/page_window.py").read()
    assert "save_page_seo" not in draft_src.replace("`save_page_seo`", "")


def test_category_star_links_to_the_category_form_for_seo():
    from apps.catalog.models import Category

    tenant = _shop()
    cat = Category.objects.create(name={"de": "Brot"}, slug="brot")
    html = Browser(tenant).get("?seite=category@catalog:brot&block=main")
    panel = _panel(html)
    assert "In der Kategorie bearbeiten →" in panel
    assert f"/catalog/categories/{cat.pk}/edit/" in panel
    assert "f_seo_title" not in panel


# ───────────── C2: строка наследования вида у категории ─────────────


def test_category_inherit_row_names_the_shared_view_and_resets_the_own_one():
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Brot"}, slug="brot")
    tenant = _shop(
        {
            **CFG,
            "page_blocks": {
                **CFG["page_blocks"],
                "category": [{"key": "main", "style": "magazin"}],
                "catalog:brot": [{"key": "main", "style": "mosaik"}],
            },
        }
    )
    b = Browser(tenant)
    html = b.get("?seite=category@catalog:brot&block=main")
    row = _panel(html)
    row = row[row.index("data-schema-page-inherit") :]
    assert "Wie bei allen Kategorie-Seiten: Magazin" in row
    assert "hier geändert gilt nur für „Brot“: Mosaik" in row
    assert "für alle ändern" in row and "seite=category&amp;block=main" in row
    _resp, _m = b.post(seite="category@catalog:brot", op="view_reset", ref="main")
    marker = next(i for i in _raw(b, "category@catalog:brot")["items"] if i.get("key") == "main")
    assert "style" not in marker and "grid" not in marker
    html = b.get("?seite=category@catalog:brot&block=main")
    assert "hier geändert gilt nur" not in _panel(html)


def test_category_without_own_view_has_no_reset():
    from apps.catalog.models import Category

    Category.objects.create(name={"de": "Brot"}, slug="brot")
    html = Browser(_shop()).get("?seite=category@catalog:brot&block=main")
    row = _panel(html)
    assert "Wie bei allen Kategorie-Seiten: Raster" in row
    assert 'value="view_reset"' not in row
