"""FB-33 M3-5b — ревью ECC (silent-failure-hunter, a11y-architect): по замку на пункт."""

import copy
import json
import logging
import re

import pytest

from apps.core import aufbau_draft, faq_content, hero_tiles, site_schema, window_parts
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m35b_before import block_html, modules_on
from apps.core.tests.test_fb33_m35b_faq_draft import (
    BASE,
    RU,
    _drafts,
    _faq_post,
    _req,
    _saved,
    _studio_changes_faq,
    _tenant,
)
from apps.core.tests.test_fb33_m35b_tiles_window import ALL_SHOWN, _post
from apps.core.tests.test_fb33_m35b_tiles_window import _tenant as _tiles_tenant
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# 1 (HIGH): сбой чтения строк — в лог, форма плашек не рисуется; пустой набор не «молча»
def test_rows_failure_is_logged_and_tiles_form_is_not_drawn(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(site_schema, "load_items", boom)
    selected = {"key": "quick_links", "ref": "q1", "cblock": True, "fields": [{"name": "set"}]}
    with caplog.at_level(logging.ERROR, logger="apps.core.window_parts"):
        window_parts.decorate(selected, {}, None, True, {}, "")
    assert "tiles" not in selected and selected["fields"]  # прежняя форма набора
    assert "block rows unavailable" in caplog.text


def test_tiles_form_without_set_field_keeps_the_set():
    data = {"set": "shop", "hidden": ["deals"]}
    assert hero_tiles.update_data(data, {"show_sortiment": "1"})["set"] == "shop"


# 2: новый вопрос не теряется; ответ без вопроса — сообщение
def test_new_question_is_taken_by_apply_and_by_arrows():
    b = Browser(_tenant())
    _faq_post(b, faq_new_q="D?", faq_new_a="4", faq_add="1")  # «Übernehmen»/Enter
    assert _drafts(b)["home"]["faq"]["items"][-1] == {"q": "D?", "a": "4"}
    b2 = Browser(_tenant())
    _faq_post(b2, faq_new_q="E?", faq_move="0:down")
    assert [i["q"] for i in _drafts(b2)["home"]["faq"]["items"]] == ["B?", "A?", "C?", "E?"]


def test_answer_without_question_is_said():
    notes = []
    faq_content.apply_ops(BASE, [0, 1, 2], {"faq_new_a": "nur Antwort", "faq_add": "1"}, notes)
    assert faq_content.orphan_note() in notes
    notes = []
    items, _src = faq_content.apply_ops(BASE, [0, 1, 2], {"faq_1_q": "", "faq_1_a": "x"}, notes)
    assert len(items) == 2 and faq_content.orphan_note() in notes


# 3: переводы подписей плашек — снимаются при правке/сбросе/смене набора
def _with_label_overlay(data, tr):
    tenant = _tiles_tenant(data)
    cfg = copy.deepcopy(tenant.site_config)
    rows = siteconfig.normalize(cfg)["sections"]
    at = next(i for i, r in enumerate(rows) if r.get("id") == "quicklinks")
    ov = [{} for _ in rows]
    ov[at] = {"data": {"labels": tr}}
    cfg["sections"] = rows
    cfg["i18n"] = {"ru": {"sections": ov}}
    tenant.site_config = cfg
    tenant.save()
    return tenant, at


def _ru_labels(b, at):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    ov = ((cfg.get("i18n") or {}).get("ru") or {}).get("sections") or []
    return ((ov[at] if at < len(ov) else {}).get("data") or {}).get("labels")


def test_german_label_edit_drops_only_that_translation():
    data = {"set": "aktionsmarkt", "labels": {"loyalty": "Punkte", "sortiment": "Alles"}}
    tenant, at = _with_label_overlay(data, {"loyalty": "Баллы", "sortiment": "Всё"})
    b = Browser(tenant)
    _post(b, **{**ALL_SHOWN, "label_loyalty": "Punkte sammeln", "label_sortiment": "Alles"})
    b.post(seite="home", op="save")
    assert _ru_labels(b, at) == {"sortiment": "Всё"}


def test_set_change_drops_all_label_translations():
    """Общий ключ («sortiment» есть и в aktionsmarkt, и в shop) не протекает в новый набор."""
    data = {"set": "aktionsmarkt", "labels": {"sortiment": "Alles"}}
    tenant, at = _with_label_overlay(data, {"sortiment": "Всё"})
    b = Browser(tenant)
    _post(b, **{**ALL_SHOWN, "set": "shop"})
    b.post(seite="home", op="save")
    assert not _ru_labels(b, at)


# 4: устаревшая вкладка с прежним набором — отказ
def test_stale_tiles_tab_is_refused():
    b = Browser(_tiles_tenant({"set": "shop", "hidden": ["deals"]}))
    stale = {**ALL_SHOWN, "tiles_rev": hero_tiles.revision({"set": "aktionsmarkt"})}
    data = {"seite": "home", "ref": "quicklinks", "op": "update", "panel_present": "1"}
    data.update({f"f_{k}": v for k, v in {**stale, "tiles_present": "1"}.items()})
    _resp, msgs = b.post(**data)
    assert hero_tiles.stale_note() in msgs
    assert aufbau_draft.get(_req(b), "home") is None


# 5: канва — от свежего конфига под блокировкой, устаревший отпечаток — 409
def test_canvas_stale_fingerprint_is_refused():
    from apps.core import views
    from apps.core.tests.test_fb33_m35b_faq_writers import _inline  # noqa: F401
    from apps.core.tests.test_fb33_m35b_faq_writers import _req as _wreq
    from apps.core.tests.test_fb33_m35b_faq_writers import _tenant as _wtenant

    tenant = _wtenant()
    body = json.dumps({"field": "faq.0.q", "value": "Neu?", "faq_base": "deadbeefdeadbeef"})
    req = _wreq(tenant, "post", "/x/", body, content_type="application/json")
    req._body = body.encode()
    assert views.site_inline_edit(req).status_code == 409
    assert _inline(tenant, "faq.0.a", "Ja, klar.").status_code == 204


def test_canvas_writes_from_the_fresh_row():
    from apps.core.tests.test_fb33_m35b_faq_writers import _inline
    from apps.core.tests.test_fb33_m35b_faq_writers import _tenant as _wtenant

    tenant = _wtenant()
    stale = copy.deepcopy(tenant.site_config)
    fresh = Tenant.objects.get(pk=tenant.pk)
    cfg = copy.deepcopy(fresh.site_config)
    cfg["faq"] = [*cfg["faq"], {"q": "Studio?", "a": ""}]
    fresh.site_config = cfg
    fresh.save()
    tenant.site_config = stale  # запрос начат до записи Студии
    assert _inline(tenant, "faq.0.a", "Ja!").status_code == 204
    saved = Tenant.objects.get(pk=tenant.pk).site_config
    assert saved["faq"][-1]["q"] == "Studio?" and saved["faq"][0]["a"] == "Ja!"


# 6: конфликт общих вопросов — своё сообщение; force — сообщение владельцу
def test_faq_conflict_has_its_own_message_and_force_says_it():
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    _studio_changes_faq(b)
    _resp, msgs = b.post(seite="home", op="save")
    assert faq_content.faq_changed_note() in msgs
    _resp, msgs = b.post(seite="home", op="save", force="1")
    assert faq_content.faq_forced_note() in msgs
    assert [f["q"] for f in _saved(b)["faq"]] == ["B?", "A?", "C?"]


def test_studio_with_stale_fingerprint_says_it():
    from apps.core.tests.test_fb33_m35b_faq_writers import _studio_save
    from apps.core.tests.test_fb33_m35b_faq_writers import _tenant as _wtenant

    tenant = _wtenant()
    cfg = _studio_save(tenant, {0: ("Parkplatz?", "Ja.")}, "deadbeefdeadbeef")
    assert cfg["faq"] == [{"q": "Parkplatz?", "a": "Ja."}]  # записано, переводы — по тексту


# 7: блок FAQ убрали из черновика страницы — вопросы «в тени» не публикуются
def test_faq_edit_of_a_removed_block_is_not_published():
    b = Browser(_tenant())
    _faq_post(b, seite="text", ref="f1", faq_remove="2")
    b.post(seite="text", ref="f1", op="delete")
    _resp, msgs = b.post(seite="text", op="save")
    assert faq_content.dropped_note() in msgs
    assert _saved(b)["faq"] == BASE and _saved(b)["i18n"]["ru"]["faq"] == RU


def test_put_warning_names_schema_and_sizes(caplog):
    c = {"faq": copy.deepcopy(BASE)}
    with caplog.at_level(logging.WARNING, logger="apps.core.faq_content"):
        faq_content.put(c, BASE[:1], [0], base_fp="0000")
    assert "saved 3, written 1" in caplog.text


# 8: после ↑↓ открыт и в фокусе сдвинутый вопрос; подпись «Gilt…» описывает форму
def test_moved_question_is_open_and_focused():
    b = Browser(_tenant())
    b.post(**_move_data(b))
    html = b.get("?seite=home&block=faq&tab=texte")
    item = re.search(r'<details[^>]*data-faq-item="1"[^>]*>\s*<summary[^>]*>', html).group(0)
    assert " open" in item and "autofocus" in item
    first = re.search(r'<details[^>]*data-faq-item="0"[^>]*>', html).group(0)
    assert " open" not in first
    again = b.get("?seite=home&block=faq&tab=texte")  # один раз
    assert "autofocus" not in re.search(r'<form[^>]*id="bw-form-faq".*?</form>', again, re.S).group(
        0
    )
    assert 'aria-describedby="bw-faq-shared"' in html and 'id="bw-faq-shared"' in html
    assert "Neue Frage" in html


def _move_data(b):
    cfg = _saved(b)
    items, src = faq_content.state(cfg, None)
    data = {
        "seite": "home",
        "ref": "faq",
        "op": "update",
        "faq_present": "1",
        "faq_move": "0:down",
        "faq_rev": faq_content.revision(items, src),
    }
    for i, it in enumerate(items):
        data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
    return data


# 9: подписи плашек для чтения
def test_tiles_form_labels_for_screen_readers():
    html = Browser(_tiles_tenant()).get("?seite=home&block=quicklinks")
    form = re.search(r'<form[^>]*id="bw-form-tiles".*?</form>', html, re.S).group(0)
    assert 'aria-label="Beschriftung – Treuepunkte"' in form
    box = re.search(r'<input type="checkbox" name="f_show_loyalty"[^>]*>', form).group(0)
    assert 'aria-describedby="bw-tile-hint-loyalty"' in box
    assert '<span aria-hidden="true">→ </span>Katalog' in form


# 10: все скрыты — без пустой сетки; одна видимая из скрытых — узкой колонкой
@pytest.mark.parametrize("name", ("gastro", "bakery", "butcher", "mode"))
def test_handwritten_all_hidden_has_no_empty_grid(monkeypatch, name):
    from django.template.loader import render_to_string

    modules_on(monkeypatch, True)
    ctx = {"hero_widget": name, "ql_hidden": list(hero_tiles.tile_keys(name)), "ql_labels": {}}
    assert "grid" not in render_to_string("storefront/sections/_hero_widget.html", ctx)


def test_bakery_one_visible_is_narrow(monkeypatch):
    modules_on(monkeypatch, True)
    html = block_html({"set": "bakery", "hidden": ["deal", "preorder", "party"]}, True)
    assert "sm:max-w-sm" in html and html.count("<a ") == 1
