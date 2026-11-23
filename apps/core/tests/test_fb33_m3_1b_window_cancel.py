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


#: токен открытия окна в тестах: правки из окна его несут (скрытое поле `wopen`)
WOPEN = "openT1"


def _post(b, **data):
    data.setdefault("wopen", WOPEN)
    return b.post(**data)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _home_item(b, ref):
    draft = (_drafts(b).get("home") or {}).get("items") or []
    return next((i for i in draft if (i.get("id") or i.get("key")) == ref), None)


def test_cancel_after_an_edit_leaves_no_draft_when_there_was_none():
    b = Browser(_shop())
    b.get("?seite=home&block=t1")
    _post(b, seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="X")
    _post(b, seite="home", ref="t1", op="toggle")
    assert _drafts(b)["home"]["window"]  # снимок есть, пока окно не закрыто
    resp, msgs = _post(b, seite="home", ref="t1", op="revert")
    assert resp.status_code == 302 and "block=" not in resp["Location"]
    assert _drafts(b) == {}  # черновика не было — и нет
    assert msgs  # читатель экрана слышит, что правки отменены


def test_cancel_returns_the_draft_byte_for_byte_as_before_opening():
    b = Browser(_shop())
    _post(b, seite="home", ref="bt1", op="toggle")  # правка другого блока — до окна
    _post(b, seite="home", ref="bt1", op="window_done")
    before = _drafts(b)
    b.get("?seite=home&block=t1")
    _post(b, seite="home", ref="t1", op="width", value="w6")
    _post(b, seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="X")
    _post(b, seite="home", ref="t1", op="down")
    _post(b, seite="home", ref="t1", op="revert")
    assert _drafts(b) == before


def test_two_tabs_with_different_blocks_keep_each_other():
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="update", panel_present="1", f_title="T1", f_body="")
    _post(b, seite="home", ref="bt1", op="update", panel_present="1", f_label="B", f_url="/b")
    _post(b, seite="home", ref="t1", op="revert")
    assert _home_item(b, "t1")["data"]["title"] == "Hallo"  # первый блок — как был
    assert _home_item(b, "bt1")["data"]["label"] == "B"  # правка второй вкладки цела
    assert list(_drafts(b)["home"]["window"]) == ["bt1"]


def test_cancel_or_done_without_an_edit_writes_nothing():
    b = Browser(_shop())
    b.get("?seite=home&block=t1&tab=texte")  # открыть окно — ничего не пишет
    assert _drafts(b) == {}
    for op in ("revert", "window_done"):
        resp, _msgs = _post(b, seite="home", ref="t1", op=op)
        assert resp.status_code == 302 and _drafts(b) == {}


def test_done_keeps_the_edit_and_forgets_the_snapshot():
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="update", panel_present="1", f_title="Neu", f_body="")
    resp, _msgs = _post(b, seite="home", ref="t1", op="window_done")
    assert "block=" not in resp["Location"]
    assert "window" not in _drafts(b)["home"]
    _post(b, seite="home", ref="t1", op="revert")  # окно закрыто — отменять нечего
    assert _home_item(b, "t1")["data"]["title"] == "Neu"


def test_save_and_discard_drop_the_snapshot_with_the_draft():
    for op in ("save", "discard"):
        b = Browser(_shop())
        _post(b, seite="home", ref="t1", op="toggle")
        _post(b, seite="home", op=op)
        assert _drafts(b) == {}, op


def test_snapshot_is_outside_the_fingerprint_and_the_counter():
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="toggle")
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
    _post(b, seite="home", ref="t1", op="toggle")
    _post(b, seite="home", ref="t1", op="toggle")
    assert "data-schema-draft-note" not in b.get("?seite=home")
    assert aufbau_draft.dirty_codes(_Req(b.session)) == []
    _post(b, seite="home", ref="t1", op="window_done")
    assert _drafts(b) == {}


def test_cancel_refuses_when_the_page_was_published_elsewhere():
    """Ревью M3-1b (HIGH): страницу сохранили в другом месте — откат отказывает с видимым
    сообщением и черновик не трогает (чужая публикация не перезаписывается)."""
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="toggle")
    before = _drafts(b)
    t = Tenant.objects.get(pk=b.tenant.pk)
    cfg = dict(t.site_config)
    cfg["sections"] = [dict(s) for s in cfg["sections"]] + [{"key": "spacer", "id": "sp9"}]
    t.site_config = cfg
    t.save()
    resp, msgs = _post(b, seite="home", ref="t1", op="revert")
    assert resp.status_code == 302
    assert _drafts(b) == before
    assert any("an anderer Stelle gespeichert" in m for m in msgs)


def test_title_and_settings_rows_are_restored_too():
    b = Browser(_shop())
    # FB-33 M5b-2 W1: заголовок и настройки типа — в окне ★-строки страницы (`__page`)
    _post(b, seite="promos", ref="__page", op="update", panel_present="1", f_title="Mein Titel")
    assert _drafts(b)["promos"]["title"]
    _post(b, seite="promos", ref="__page", op="revert")
    assert _drafts(b) == {}
    html = b.get("?seite=catalog&block=__page")
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
    _resp, msgs = _post(b, seite="catalog", ref="__page", op="setting", setting=code, value=free[0])
    assert (_drafts(b).get("catalog") or {}).get("settings"), (code, free, msgs)
    _post(b, seite="catalog", ref="__page", op="revert")
    assert _drafts(b) == {}


def test_at_most_three_snapshots_oldest_first_out():
    b = Browser(_shop())
    for ref in ("t1", "bt1", "l1", "quicklinks"):
        _post(b, seite="home", ref=ref, op="toggle")
    assert list(_drafts(b)["home"]["window"]) == ["bt1", "l1", "quicklinks"]


def test_window_has_done_and_cancel_buttons_without_scripts():
    b = Browser(_shop())
    panel = _panel(b.get("?seite=home&block=t1"))
    actions = re.search(r"<form[^>]*data-window-actions.*?</form>", panel, re.S).group(0)
    assert 'value="revert"' in actions and 'value="window_done"' in actions
    assert 'name="ref" value="t1"' in actions
    confirm = _panel(b.get("?seite=home&block=t1&entfernen=1"))
    assert "data-window-actions" not in confirm


# ───────────── ревью M3-1b ─────────────


def test_reopening_the_window_takes_a_fresh_snapshot():
    """HIGH: снимок прежнего открытия не живёт дольше: новое открытие (другой токен
    `wopen`) — снимок с текущего состояния; Abbrechen — к моменту второго открытия."""
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", wopen="openA1", op="update", panel_present="1",
           f_title="Erstes", f_body="")  # fmt: skip
    # окно закрыли мобильной ссылкой «Fertig» (снимок не снят) и открыли снова
    _post(b, seite="home", ref="t1", wopen="openB2", op="update", panel_present="1",
           f_title="Zweites", f_body="")  # fmt: skip
    resp, msgs = _post(b, seite="home", ref="t1", wopen="openB2", op="revert")
    assert _home_item(b, "t1")["data"]["title"] == "Erstes"
    assert any("zurückgenommen" in m for m in msgs)


def test_same_block_in_two_tabs_last_opening_wins():
    """LOW: две вкладки одной сессии на одном блоке делят снимок — правка из окна с
    другим токеном начинает его заново (побеждает последнее открытие)."""
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", wopen="tabAaa", op="toggle")
    _post(b, seite="home", ref="t1", wopen="tabBbb", op="width", value="w6")
    _post(b, seite="home", ref="t1", wopen="tabBbb", op="revert")
    item = _home_item(b, "t1")
    assert item["enabled"] is False and (item.get("width") or "") != "w6"
    # вкладка A после этого: её снимка уже нет — честно «нечего»
    _resp, msgs = _post(b, seite="home", ref="t1", wopen="tabAaa", op="revert")
    assert any("Nichts zurückzunehmen" in m for m in msgs)


def test_actions_keep_the_opening_token_and_a_new_opening_gets_a_new_one():
    b = Browser(_shop())
    html = b.get("?seite=home&block=t1")
    token = re.search(r'name="wopen" value="([^"]+)"', html).group(1)
    resp, _msgs = _post(b, seite="home", ref="t1", wopen=token, op="toggle")
    assert f"wopen={token}" in resp["Location"]  # действие окна — то же открытие
    query = "?" + resp["Location"].split("?", 1)[1].split("#", 1)[0]
    assert f'name="wopen" value="{token}"' in b.get(query)
    again = b.get("?seite=home&block=t1")
    assert f'name="wopen" value="{token}"' not in again  # новое открытие — новый токен


def test_delete_drops_the_snapshot_and_dead_snapshots_free_their_slot():
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="toggle")
    _post(b, seite="home", ref="bt1", op="toggle")
    _post(b, seite="home", ref="l1", op="toggle")
    _post(b, seite="home", ref="bt1", op="delete")
    assert list(_drafts(b)["home"]["window"]) == ["t1", "l1"]
    _post(b, seite="home", ref="quicklinks", op="toggle")
    _post(b, seite="home", ref="t1", op="width", value="w6")
    assert list(_drafts(b)["home"]["window"]) == ["t1", "l1", "quicklinks"]


def test_cancel_without_a_snapshot_warns_instead_of_claiming_success():
    """HIGH: снимка нет (вытеснен, «Verwerfen» в другой вкладке, сессия истекла) —
    предупреждение, а не «zurückgenommen»."""
    b = Browser(_shop())
    _resp, msgs = _post(b, seite="home", ref="t1", op="revert")
    assert any("Nichts zurückzunehmen" in m for m in msgs)
    assert not any("zurückgenommen." in m for m in msgs)
    _post(b, seite="home", ref="t1", op="toggle")
    _post(b, seite="home", op="discard")  # другая вкладка отбросила черновик
    _resp, msgs = _post(b, seite="home", ref="t1", op="revert")
    assert any("Nichts zurückzunehmen" in m for m in msgs) and _drafts(b) == {}


def test_apply_all_settings_are_restored_too(monkeypatch):
    """MEDIUM: «на все списки» — снимок помнит все задетые настройки, откат возвращает их."""
    from apps.core import page_settings

    tenant = _shop()
    draft = {"items": [], "settings": {"catalog_layout": {"v": "cols3", "o": None}}}
    proto = {}
    aufbau_draft._record_codes(draft, proto, ["catalog_layout", "promos_layout"])
    draft["settings"] = {
        "catalog_layout": {"v": "cols4", "o": None},
        "promos_layout": {"v": "cols4", "o": None},
    }
    draft["window"] = {"main": {**proto, "item": None}}
    aufbau_draft._revert(draft, "main", draft["window"]["main"])
    assert draft["settings"] == {"catalog_layout": {"v": "cols3", "o": None}}
    assert tenant and page_settings  # настройки — те же записи, что пишет setting_op


def test_missing_setting_codes_are_logged_not_swallowed(monkeypatch, caplog):
    from apps.core import site_schema

    def boom(*a, **kw):
        raise site_schema.SchemaError("block")

    monkeypatch.setattr(site_schema, "setting_codes", boom)
    with caplog.at_level("WARNING", logger="apps.core.aufbau_draft"):
        # FB-33 M5b-2 W1: строка настроек каталога — ★-строка страницы (`__page`)
        assert aufbau_draft._window_setting_codes(_shop(), "catalog", "__page") == []
    assert "setting codes" in caplog.text


def _two_text_tenant():
    tenant = _shop()
    cfg = dict(tenant.site_config)
    cfg["sections"] = [
        {"key": "hero"},
        {"key": "text", "id": "a0", "enabled": True, "data": {"title": "A0", "body": ""}},
        {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Hallo", "body": ""}},
        {"key": "button", "id": "bt1", "enabled": True, "data": {"label": "B", "url": "/b"}},
    ]
    tenant.site_config = cfg
    tenant.save()
    return tenant


def _order(b):
    return [i.get("id") or i.get("key") for i in _drafts(b)["home"]["items"]][:4]


def test_row_returns_next_to_its_old_neighbour_not_to_an_old_index():
    """MEDIUM: место строки — по соседу сверху; в другой вкладке подняли блок над соседом
    (индексы сдвинулись) — строка всё равно встаёт сразу после прежнего соседа."""
    b = Browser(_two_text_tenant())
    _post(b, seite="home", ref="t1", op="down")  # окно t1: hero · a0 · bt1 · t1
    _post(b, seite="home", ref="bt1", op="up")  # другая вкладка: hero · bt1 · a0 · t1
    _post(b, seite="home", ref="t1", op="revert")
    assert _order(b) == ["hero", "bt1", "a0", "t1"]  # по индексу встал бы перед a0


def test_row_without_its_neighbour_goes_to_the_nearest_place():
    proto = {"item": {"id": "t1"}, "at": 5, "after": "gone"}
    draft = {"items": [{"id": "x"}, {"id": "t1"}, {"id": "y"}], "window": {"t1": proto}}
    aufbau_draft._revert(draft, "t1", proto)
    assert [i["id"] for i in draft["items"]] == ["x", "y", "t1"]  # индекс в пределах списка
    proto = {"item": {"id": "t1"}, "at": 3, "after": None}
    draft = {"items": [{"id": "x"}, {"id": "t1"}], "window": {"t1": proto}}
    aufbau_draft._revert(draft, "t1", proto)
    assert [i["id"] for i in draft["items"]] == ["t1", "x"]  # был первым — первым


def test_idle_drafts_do_not_push_out_real_ones_and_expire(monkeypatch):
    """MEDIUM: «пустой» черновик (только снимок) не занимает места настоящих и живёт сутки."""
    req = _Req(_Session())
    for i in range(aufbau_draft.MAX_DRAFTS):
        aufbau_draft._put(req, f"real{i}", {"items": [{"key": "a"}], "base": "x"})
    aufbau_draft._put(req, "idle1", {"items": [], "idle": True, "idle_at": 10**12, "window": {}})
    assert len([c for c in req.session["aufbau_draft"] if c.startswith("real")]) == 10
    assert aufbau_draft._raw(req, "idle1") is not None
    monkeypatch.setattr(aufbau_draft.time, "time", lambda: 10**12 + aufbau_draft.IDLE_TTL + 1)
    assert aufbau_draft._raw(req, "idle1") is None  # истёк — как его нет
    aufbau_draft._put(req, "real0", {"items": [{"key": "b"}], "base": "y"})
    assert "idle1" not in req.session["aufbau_draft"]


def test_draft_after_cancel_passes_the_same_normalization(caplog):
    """LOW: откат пишет в черновик сам — результат проходит ту же нормализацию витрины."""
    b = Browser(_shop())
    _post(b, seite="home", ref="bt1", op="toggle")
    _post(b, seite="home", ref="t1", op="update", panel_present="1", f_title="X", f_body="Y")
    with caplog.at_level("WARNING", logger="apps.core.aufbau_draft"):
        _post(b, seite="home", ref="t1", op="revert")
    assert "after revert" not in caplog.text
    draft = _drafts(b)["home"]
    saved = siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)
    shown = siteconfig.normalize(aufbau_draft.overlay(saved, draft))
    from apps.core import site_schema

    assert site_schema.load_items(shown, True, "") == draft["items"]


# ───────────── ревью 2 M3-1b ─────────────


def test_edit_outside_the_window_writes_no_snapshot_and_cancel_says_nothing():
    """MEDIUM: правка без токена (список «Blöcke», меню строки) снимка не пишет; окно,
    открытое после неё, «Abbrechen»-ом её не откатывает."""
    b = Browser(_shop())
    b.post(seite="home", ref="t1", op="toggle")  # «Blöcke»: без токена окна
    assert "window" not in _drafts(b)["home"]
    html = b.get("?seite=home&block=t1")
    token = re.search(r'name="wopen" value="([^"]+)"', html).group(1)
    _resp, msgs = b.post(seite="home", ref="t1", wopen=token, op="revert")
    assert _home_item(b, "t1")["enabled"] is False  # скрытие осталось
    assert any("Nichts zurückzunehmen" in m for m in msgs)


def test_cancel_needs_the_token_of_its_opening():
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="toggle")
    for token in ("", "otherOne"):
        _resp, msgs = b.post(seite="home", ref="t1", wopen=token, op="revert")
        assert any("Nichts zurückzunehmen" in m for m in msgs), token
    assert _home_item(b, "t1")["enabled"] is False


def _open_link(html, ref):
    m = re.search(rf'href="(\?seite=home&amp;block={ref}&amp;wopen=[A-Za-z0-9_-]+)', html)
    return m.group(1).replace("&amp;", "&")


def test_reload_keeps_the_opening_so_cancel_goes_back_to_the_first_edit():
    """MEDIUM: ссылка на блок несёт токен открытия — F5 остаётся тем же открытием:
    правка → F5 → правка → Abbrechen возвращает к моменту открытия."""
    b = Browser(_shop())
    url = _open_link(b.get("?seite=home"), "t1")
    token = re.search(r"wopen=([A-Za-z0-9_-]+)", url).group(1)
    assert f'name="wopen" value="{token}"' in b.get(url)
    b.post(seite="home", ref="t1", wopen=token, op="update", panel_present="1",
           f_title="Eins", f_body="")  # fmt: skip
    assert f'name="wopen" value="{token}"' in b.get(url)  # F5 — тот же токен
    b.post(seite="home", ref="t1", wopen=token, op="update", panel_present="1",
           f_title="Zwei", f_body="")  # fmt: skip
    b.post(seite="home", ref="t1", wopen=token, op="revert")
    assert _drafts(b) == {}  # как до открытия: черновика не было


def test_confirm_links_and_phone_done_keep_the_opening():
    b = Browser(_shop())
    html = b.get("?seite=home&block=t1&wopen=keepMe1")
    # FB-33 M5c-2: «⋯» строки схемы — новое открытие; в шапке окна — то же открытие
    panel = html[html.index('id="schema-panel"') :]
    remove = re.search(r'href="([^"]*entfernen=1[^"]*)"', panel).group(1)
    assert "wopen=keepMe1" in remove
    confirm = b.get("?seite=home&block=t1&entfernen=1&wopen=keepMe1")
    back = re.search(r'<a href="([^"]*)" class="ui-btn ui-btn-secondary">', confirm).group(1)
    assert "wopen=keepMe1" in back
    done = re.search(r"<form[^>]*xl:hidden[^>]*>.*?</form>", html, re.S).group(0)
    assert 'value="window_done"' in done and "data-schema-done" in done
    assert 'name="wopen" value="keepMe1"' in done


def test_banner_editor_returns_with_the_opening_token():
    from apps.core import banner_views

    resp = banner_views._back_to_schema("home", "hero", "keepMe1")
    assert "wopen=keepMe1" in resp["Location"] and "block=hero" in resp["Location"]


def test_adopt_and_reset_drop_the_snapshots(monkeypatch):
    """LOW: своя схема категории — строки заменены целиком, их снимки больше не годятся."""
    from apps.core import site_schema

    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="toggle")
    assert _drafts(b)["home"]["window"]
    monkeypatch.setattr(site_schema, "category_items", lambda c, h, items, op: list(items))
    req = b._request("post", {})
    aufbau_draft.op(req, b.tenant, "home", "adopt", token=WOPEN)
    assert "window" not in (_drafts(b).get("home") or {})


def test_a_refused_edit_writes_no_snapshot():
    """LOW: снимок пишется после успешной операции — отказ (SchemaError) его не оставляет."""
    b = Browser(_shop())
    _post(b, seite="home", ref="t1", op="width", value="nonsense")
    assert "window" not in (_drafts(b).get("home") or {})


def test_session_is_marked_modified_on_every_write():
    req = _Req(_Session())
    aufbau_draft._put(req, "home", {"items": [{"key": "a"}], "base": "x"})
    assert req.session.modified is True


def test_normalization_check_covers_section_pages_too(caplog):
    """LOW: проверка нормализацией — и у страниц разделов (нормализованное против
    нормализованного — без шума)."""
    b = Browser(_shop())
    _post(b, seite="product", ref="related", op="toggle")
    with caplog.at_level("WARNING", logger="apps.core.aufbau_draft"):
        _resp, msgs = _post(b, seite="product", ref="related", op="revert")
    assert any("zurückgenommen" in m for m in msgs)
    assert "after revert" not in caplog.text


class _Session(dict):
    modified = False


class _Req:
    def __init__(self, session):
        self.session = session
