"""FB-33 M3-5b: плашки Schnellzugriff в окне блока (вкладка «Was», макет M0-4).

Замки: плашки и «Vorlage für die Kacheln» — ОДНА форма `bw-form-tiles` во «Was» (прежней
формы набора нет); снятая галочка — скрытие, подпись — своя, стандартная не хранится; смена
набора сбрасывает скрытие и подписи; «Abbrechen» — байт-в-байт; без правок — черновика нет.
"""

import copy
import re

import pytest

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop

pytestmark = pytest.mark.django_db
WOPEN = "openQ1"


def _tenant(data=None):
    tenant = _shop()
    cfg = copy.deepcopy(tenant.site_config)
    for row in cfg["sections"]:
        if row.get("key") == "quick_links":
            row["data"] = data or {"set": "aktionsmarkt"}
    tenant.site_config = cfg
    tenant.save()
    return tenant


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _data(b):
    items = (_drafts(b).get("home") or {}).get("items") or []
    return next(i for i in items if i.get("id") == "quicklinks").get("data")


def _tab(html, key):
    m = re.search(rf'<section id="schema-tab-{key}".*?</section>', html, flags=re.S)
    return m.group(0) if m else ""


def _post(b, **f):
    data = {"seite": "home", "ref": "quicklinks", "op": "update", "panel_present": "1"}
    data.update({"f_tiles_present": "1", "wopen": WOPEN})
    data.update({f"f_{k}": v for k, v in f.items()})
    return b.post(**data)


ALL_SHOWN = {
    "set": "aktionsmarkt",
    "show_deals": "1",
    "show_sortiment": "1",
    "show_loyalty": "1",
    "show_newsletter": "1",
}


def test_tiles_and_set_are_one_form_in_was():
    html = Browser(_tenant()).get("?seite=home&block=quicklinks")
    was = _tab(html, "was")
    form = re.search(r'<form[^>]*id="bw-form-tiles".*?</form>', was, flags=re.S).group(0)
    assert 'name="f_set"' in form and "Vorlage für die Kacheln" in form
    for key in ("deals", "sortiment", "loyalty", "newsletter"):
        assert f'name="f_show_{key}" value="1"' in form and f'name="f_label_{key}"' in form
    assert 'aria-label="Aktuelle Deals zeigen"' in form and "nur wenn Deals laufen" in form
    assert "→ Katalog" in form and "nur mit Bonusprogramm" in form and "→ Newsletter" in form
    assert 'value="Sortiment ansehen"' in form  # стандартная подпись в поле
    assert html.count('name="f_set"') == 1  # прежней формы набора нет
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'value="update"' in first


def test_hide_and_rename_go_to_the_draft():
    b = Browser(_tenant())
    _post(b, **{**ALL_SHOWN, "show_newsletter": "", "label_loyalty": "Punkte sammeln"})
    assert _data(b) == {
        "set": "aktionsmarkt",
        "hidden": ["newsletter"],
        "labels": {"loyalty": "Punkte sammeln"},
    }
    html = b.get("?seite=home&block=quicklinks")
    assert 'value="Punkte sammeln"' in html
    assert re.search(r'name="f_show_newsletter" value="1" class="h-5 w-5" aria-label', html)


def test_unchanged_form_leaves_no_draft():
    b = Browser(_tenant())
    _post(b, **{**ALL_SHOWN, "label_deals": "Aktuelle Deals"})
    assert aufbau_draft.get(type("R", (), {"session": b.session})(), "home") is None


def test_set_change_resets_hidden_and_labels():
    b = Browser(_tenant({"set": "aktionsmarkt", "hidden": ["deals"], "labels": {"loyalty": "P"}}))
    _post(b, **{**ALL_SHOWN, "set": "shop", "label_loyalty": "P"})
    assert _data(b) == {"set": "shop"}


def test_cancel_returns_the_tiles():
    b = Browser(_tenant())
    before = _drafts(b)
    b.get(f"?seite=home&block=quicklinks&wopen={WOPEN}")
    _post(b, **{**ALL_SHOWN, "show_deals": ""})
    _post(b, **{**ALL_SHOWN, "set": "shop"})
    b.post(seite="home", ref="quicklinks", op="revert", wopen=WOPEN)
    assert aufbau_draft.get(type("R", (), {"session": b.session})(), "home") is None
    assert {k: v for k, v in _drafts(b).items() if not v.get("idle")} == before


def test_save_writes_the_block_data():
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    b = Browser(_tenant())
    _post(b, **{**ALL_SHOWN, "show_deals": "", "label_sortiment": "<b>Alles</b>"})
    b.post(seite="home", op="save")
    cfg = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    row = next(r for r in cfg["sections"] if r.get("id") == "quicklinks")
    assert row["data"] == {
        "set": "aktionsmarkt",
        "hidden": ["deals"],
        "labels": {"sortiment": "<b>Alles</b>"},  # текст как есть, экранирует витрина
    }


def test_block_without_set_offers_only_the_set():
    html = Browser(_tenant({"set": "visit"})).get("?seite=home&block=quicklinks")
    assert 'id="bw-form-tiles"' in html and "f_show_" not in html
