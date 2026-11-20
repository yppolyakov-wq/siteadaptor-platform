"""FB-33 M3-5b: вопросы FAQ в черновике «Seitenaufbau» (окно блока, вкладка «Texte»).

Замки: правка — в черновик, на сайт по «Speichern» тем же писателем (`faq_content.put`);
вернул как было — черновика нет; вторая вкладка со старыми номерами — отказ; Студия
сохранила вопросы — конфликт только у черновика с вопросами; «Abbrechen» — байт-в-байт;
форма вопросов не шлёт `panel_present` и не трогает вид секции.
"""

import copy

import pytest

from apps.core import aufbau_draft, faq_content
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window import _shop
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

BASE = [{"q": "A?", "a": "1"}, {"q": "B?", "a": "2"}, {"q": "C?", "a": "3"}]
RU = [{"q": "А?", "a": "1р"}, {"q": "Б?", "a": "2р"}, {"q": "В?", "a": "3р"}]
WOPEN = "openF1"


def _tenant():
    tenant = _shop()
    cfg = copy.deepcopy(tenant.site_config)
    cfg["faq"] = copy.deepcopy(BASE)
    cfg["i18n"] = {"ru": {"faq": copy.deepcopy(RU)}}
    tenant.site_config = cfg
    tenant.save()
    return tenant


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _faq_post(b, seite="home", ref="faq", items=None, src=None, **extra):
    """Форма вопросов окна как её шлёт браузер: тексты всех вопросов, номер состава."""
    if items is None:
        cfg = _saved(b)
        draft = _drafts(b).get(seite)
        items, src = faq_content.state(cfg, draft)
    data = {
        "seite": seite,
        "ref": ref,
        "op": "update",
        "faq_present": "1",
        "wopen": WOPEN,
        "faq_rev": faq_content.revision(items, src),
        "faq_base": faq_content.fingerprint(faq_content.base_items(_saved(b))),
    }
    for i, it in enumerate(items):
        data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
    data.update(extra)
    return b.post(**data)


def test_edit_goes_to_the_draft_and_save_moves_translations():
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    assert _saved(b)["faq"] == BASE  # на сайте ничего
    assert _drafts(b)["home"]["faq"]["src"] == [1, 0, 2]
    resp, msgs = b.post(seite="home", op="save")
    cfg = _saved(b)
    assert [f["q"] for f in cfg["faq"]] == ["B?", "A?", "C?"]
    assert cfg["i18n"]["ru"]["faq"] == [RU[1], RU[0], RU[2]]
    assert "Gespeichert." in msgs


def test_count_and_preview_show_the_draft():
    b = Browser(_tenant())
    _faq_post(b, faq_remove="0")
    draft = _drafts(b)["home"]
    saved = _saved(b)
    shown = aufbau_draft.overlay(saved, draft)
    assert [f["q"] for f in shown["faq"]] == ["B?", "C?"]
    assert shown["i18n"]["ru"]["faq"] == RU[1:]
    state = aufbau_draft._saved_state(saved, True, "")
    assert aufbau_draft.changes(state, draft) == 1


def test_back_to_saved_leaves_no_draft():
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    _faq_post(b, faq_move="0:down")
    assert "faq" not in (_drafts(b).get("home") or {})


def test_german_edit_drops_only_that_translation_on_save():
    b = Browser(_tenant())
    _faq_post(b, faq_1_a="2 neu")
    b.post(seite="home", op="save")
    assert _saved(b)["i18n"]["ru"]["faq"] == [RU[0], {"q": "Б?"}, RU[2]]


def test_add_only_with_the_button():
    b = Browser(_tenant())
    _faq_post(b, faq_new_q="D?", faq_new_a="4")  # со скриптами — поле применяется на лету
    assert "faq" not in (_drafts(b).get("home") or {})
    _faq_post(b, faq_new_q="D?", faq_new_a="4", faq_add="1")
    assert _drafts(b)["home"]["faq"]["items"][-1] == {"q": "D?", "a": "4"}


def test_second_tab_with_old_numbers_is_refused():
    b = Browser(_tenant())
    old_items, old_src = copy.deepcopy(BASE), [0, 1, 2]
    _faq_post(b, faq_remove="0")  # первая вкладка удалила «A?»
    resp, msgs = _faq_post(b, items=old_items, src=old_src, faq_remove="1")  # старая вкладка
    assert [i["q"] for i in _drafts(b)["home"]["faq"]["items"]] == ["B?", "C?"]
    assert faq_content.stale_note() in msgs


def test_text_edits_keep_the_number_valid():
    """Со скриптами окно после правки текста не перерисовывается — номер состава тот же."""
    b = Browser(_tenant())
    items, src = copy.deepcopy(BASE), [0, 1, 2]
    _faq_post(b, items=items, src=src, faq_0_q="A neu?")
    resp, msgs = _faq_post(b, items=items, src=src, faq_0_q="A neu?", faq_2_a="3 neu")
    got = _drafts(b)["home"]["faq"]["items"]
    assert got[0]["q"] == "A neu?" and got[2]["a"] == "3 neu" and not msgs


def _studio_changes_faq(b):
    t = Tenant.objects.get(pk=b.tenant.pk)
    cfg = copy.deepcopy(t.site_config)
    faq_content.put(cfg, [*BASE, {"q": "Studio?", "a": "x"}], [0, 1, 2, None])
    t.site_config = cfg
    t.save()


def test_studio_save_meanwhile_is_a_conflict_only_for_a_draft_with_questions():
    b = Browser(_tenant())
    b.post(seite="text", ref="f1", op="toggle")  # черновик другой страницы, FAQ не тронут
    _faq_post(b, faq_move="0:down")
    _studio_changes_faq(b)
    saved = _saved(b)
    assert aufbau_draft.info(_req(b), saved, "home")["conflict"] is True
    assert aufbau_draft.info(_req(b), saved, "text")["conflict"] is False
    resp, msgs = b.post(seite="home", op="save")
    assert any("an anderer Stelle" in m for m in msgs)
    assert [f["q"] for f in _saved(b)["faq"]][-1] == "Studio?"  # не записано


def test_force_after_conflict_matches_by_text(caplog):
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    _studio_changes_faq(b)
    b.post(seite="home", op="save", force="1")
    cfg = _saved(b)
    assert [f["q"] for f in cfg["faq"]] == ["B?", "A?", "C?"]
    assert cfg["i18n"]["ru"]["faq"] == [RU[1], RU[0], RU[2]]
    assert "matched by text" in caplog.text


def _req(b):
    from types import SimpleNamespace

    return SimpleNamespace(session=b.session)


def test_cancel_returns_the_draft_byte_for_byte():
    b = Browser(_tenant())
    b.post(seite="home", ref="t1", op="toggle", wopen="other")
    b.post(seite="home", ref="t1", op="window_done")
    before = _drafts(b)
    b.get(f"?seite=home&block=faq&tab=texte&wopen={WOPEN}")
    _faq_post(b, faq_move="0:down")
    _faq_post(b, faq_1_q="Neu?")
    assert _drafts(b)["home"]["faq"]
    b.post(seite="home", ref="faq", op="revert", wopen=WOPEN)
    assert _drafts(b) == before


def test_cancel_after_studio_save_drops_the_conflict():
    b = Browser(_tenant())
    _faq_post(b, faq_move="0:down")
    _studio_changes_faq(b)
    b.post(seite="home", ref="faq", op="revert", wopen=WOPEN)
    assert aufbau_draft.get(_req(b), "home") is None


def test_faq_form_does_not_touch_the_section_view():
    b = Browser(_tenant())
    _faq_post(b, f_style="cards")  # поле вида без panel_present — не читается
    # тексты те же — правки нет (остался только снимок окна), вид секции не тронут
    assert aufbau_draft.get(_req(b), "home") is None


def test_faq_ref_block_on_a_page_edits_the_same_questions():
    b = Browser(_tenant())
    _faq_post(b, seite="text", ref="f1", faq_remove="2")
    b.post(seite="text", op="save")
    assert [f["q"] for f in _saved(b)["faq"]] == ["A?", "B?"]


def test_detail_section_faq_is_not_the_site_faq():
    """У детальной секция «faq» — свои вопросы объекта: форма вопросов сайта её не правит."""
    assert not aufbau_draft._is_faq_row({"home": False}, {"key": "faq"})
    assert aufbau_draft._is_faq_row({"home": True}, {"key": "faq"})
    assert aufbau_draft._is_faq_row({"home": False}, {"key": "faq_ref", "id": "f1"})
