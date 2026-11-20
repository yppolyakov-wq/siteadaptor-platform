"""FB-33 M3-1b: «Fertig» и «Abbrechen» окна блока (`docs/fb33-editor-model-2026-11-19.md`
§«План M3», architect п. 2). «Abbrechen» возвращает блок к состоянию на момент открытия
окна: снимок в черновике пишется первой правкой после открытия, откат — тем же писателем."""

import copy
import re

import pytest

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _home_item(b, ref):
    draft = (_drafts(b).get("home") or {}).get("items") or []
    return next((i for i in draft if (i.get("id") or i.get("key")) == ref), None)


def test_cancel_after_an_edit_leaves_no_draft_when_there_was_none():
    b = Browser(_shop())
    b.get("?seite=home&block=t1")
    b.post(seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="X")
    b.post(seite="home", ref="t1", op="toggle")
    assert _drafts(b)["home"]["window"]  # снимок есть, пока окно не закрыто
    resp, msgs = b.post(seite="home", ref="t1", op="revert")
    assert resp.status_code == 302 and "block=" not in resp["Location"]
    assert _drafts(b) == {}  # черновика не было — и нет
    assert msgs  # читатель экрана слышит, что правки отменены


def test_cancel_returns_the_draft_byte_for_byte_as_before_opening():
    b = Browser(_shop())
    b.post(seite="home", ref="bt1", op="toggle")  # правка другого блока — до окна
    b.post(seite="home", ref="bt1", op="window_done")
    before = _drafts(b)
    b.get("?seite=home&block=t1")
    b.post(seite="home", ref="t1", op="width", value="w6")
    b.post(seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="X")
    b.post(seite="home", ref="t1", op="down")
    b.post(seite="home", ref="t1", op="revert")
    assert _drafts(b) == before


def test_two_tabs_with_different_blocks_keep_each_other():
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="update", panel_present="1", f_title="T1", f_body="")
    b.post(seite="home", ref="bt1", op="update", panel_present="1", f_label="B", f_url="/b")
    b.post(seite="home", ref="t1", op="revert")
    assert _home_item(b, "t1")["data"]["title"] == "Hallo"  # первый блок — как был
    assert _home_item(b, "bt1")["data"]["label"] == "B"  # правка второй вкладки цела
    assert list(_drafts(b)["home"]["window"]) == ["bt1"]


def test_cancel_or_done_without_an_edit_writes_nothing():
    b = Browser(_shop())
    b.get("?seite=home&block=t1&tab=texte")  # открыть окно — ничего не пишет
    assert _drafts(b) == {}
    for op in ("revert", "window_done"):
        resp, _msgs = b.post(seite="home", ref="t1", op=op)
        assert resp.status_code == 302 and _drafts(b) == {}


def test_done_keeps_the_edit_and_forgets_the_snapshot():
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="")
    resp, _msgs = b.post(seite="home", ref="t1", op="window_done")
    assert "block=" not in resp["Location"]
    assert "window" not in _drafts(b)["home"]
    b.post(seite="home", ref="t1", op="revert")  # окно закрыто — отменять нечего
    assert _home_item(b, "t1")["data"]["title"] == "Neu"


def test_save_and_discard_drop_the_snapshot_with_the_draft():
    for op in ("save", "discard"):
        b = Browser(_shop())
        b.post(seite="home", ref="t1", op="toggle")
        b.post(seite="home", op=op)
        assert _drafts(b) == {}, op


def test_snapshot_is_outside_the_fingerprint_and_the_counter():
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="toggle")
    draft = _drafts(b)["home"]
    saved = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    bare = {k: v for k, v in draft.items() if k != "window"}
    state = aufbau_draft._saved_state(saved, True, "")
    assert aufbau_draft.changes(state, draft) == aufbau_draft.changes(state, bare) == 1
    assert aufbau_draft._base_fingerprint(state, saved, draft) == draft["base"]


def test_hand_undo_keeps_the_snapshot_but_shows_no_draft():
    """Правка и её возврат руками: черновик «чистый», но окно открыто — снимок живёт
    (Abbrechen ещё должен работать), а экран и список черновиков его не видят."""
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="toggle")
    b.post(seite="home", ref="t1", op="toggle")
    assert "data-schema-draft-note" not in b.get("?seite=home")
    assert aufbau_draft.dirty_codes(_Req(b.session)) == []
    b.post(seite="home", ref="t1", op="window_done")
    assert _drafts(b) == {}


def test_cancel_survives_a_stale_draft():
    """Сохранённое изменили в другом месте: откат правит только черновик, не падает."""
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="toggle")
    t = Tenant.objects.get(pk=b.tenant.pk)
    cfg = dict(t.site_config)
    cfg["sections"] = [dict(s) for s in cfg["sections"]] + [{"key": "spacer", "id": "sp9"}]
    t.site_config = cfg
    t.save()
    resp, _msgs = b.post(seite="home", ref="t1", op="revert")
    assert resp.status_code == 302
    draft = _drafts(b).get("home") or {}
    assert "window" not in draft  # снимок снят; черновик (если остался) — с конфликтом
    if draft:
        assert aufbau_draft.info(_Req(b.session), siteconfig.normalize(cfg), "home")["conflict"]


def test_title_and_settings_rows_are_restored_too():
    b = Browser(_shop())
    b.post(seite="promos", ref="__title", op="update", panel_present="1", f_title="Mein Titel")
    assert _drafts(b)["promos"]["title"]
    b.post(seite="promos", ref="__title", op="revert")
    assert _drafts(b) == {}
    html = b.get("?seite=catalog&block=main")
    # первая настройка ★ с выбором: значение, которое сейчас НЕ выбрано (иначе черновика нет)
    for form in re.finditer(
        r'<form method="post"[^>]*data-schema-setting="([a-z_]+)" data-pt-setting.*?</form>',
        html,
        re.S,
    ):
        radios = re.findall(r'<input type="radio"[^>]*name="value"[^>]*>', form.group(0))
        free = [
            re.search(r'value="([^"]*)"', r).group(1)
            for r in radios
            if " checked" not in r and " disabled" not in r
        ]
        if free:
            code = form.group(1)
            break
    _resp, msgs = b.post(seite="catalog", ref="main", op="setting", setting=code, value=free[0])
    assert (_drafts(b).get("catalog") or {}).get("settings"), (code, free, msgs)
    b.post(seite="catalog", ref="main", op="revert")
    assert _drafts(b) == {}


def test_at_most_three_snapshots_oldest_first_out():
    b = Browser(_shop())
    for ref in ("t1", "bt1", "l1", "quicklinks"):
        b.post(seite="home", ref=ref, op="toggle")
    assert list(_drafts(b)["home"]["window"]) == ["bt1", "l1", "quicklinks"]


def test_window_has_done_and_cancel_buttons_without_scripts():
    b = Browser(_shop())
    panel = _panel(b.get("?seite=home&block=t1"))
    actions = re.search(r"<form[^>]*data-window-actions.*?</form>", panel, re.S).group(0)
    assert 'value="revert"' in actions and 'value="window_done"' in actions
    assert 'name="ref" value="t1"' in actions
    confirm = _panel(b.get("?seite=home&block=t1&entfernen=1"))
    assert "data-window-actions" not in confirm


class _Req:
    def __init__(self, session):
        self.session = session
