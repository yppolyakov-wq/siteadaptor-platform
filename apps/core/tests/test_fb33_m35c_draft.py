"""FB-33 M3-5c C2: переводы текстов блока в черновике «Seitenaufbau» (окно блока).

L7 присланный перевод — в черновик (`btr`), на сайт — по «Speichern»; равный сохранённому —
записи нет, черновика нет; счётчик — одно изменение на окно. L8 правка немецкого текста снимает
перевод этого поля у всех языков (сообщение со списком языков), перевод, введённый в той же
форме, остаётся. L9 «Abbrechen» возвращает переводы только своего блока. L10 «Speichern» пишет
перевод на место блока, даже если блоки переставлены. L11 переводы изменили в другом месте —
отказ «btr_conflict», «Trotzdem speichern» пишет поверх. L12 превью черновика показывает
перевод на своём языке. L13 «Seitentitel» и «Was passiert jetzt».
"""

import copy

import pytest

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import CFG
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db
WOPEN = "openC5"
XF = pytest.mark.xfail(strict=True, reason="M3-5c C2: переводов в черновике ещё нет")


def _shop(cfg=None, locales=("de", "ru", "en"), default="de"):
    tenant = _tenant()
    tenant.site_config = copy.deepcopy(cfg if cfg is not None else CFG)
    tenant.enabled_locales = list(locales)
    tenant.default_locale = default
    tenant.save()
    return tenant


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _idx(cfg, ref):
    return next(i for i, r in enumerate(cfg["sections"]) if r.get("id") == ref)


def _ru(cfg, ref):
    rows = ((cfg.get("i18n") or {}).get("ru") or {}).get("sections") or []
    i = _idx(cfg, ref)
    return (rows[i] if i < len(rows) else {}).get("data") or {}


def _post(b, ref="t1", seite="home", **fields):
    data = {"seite": seite, "ref": ref, "op": "update", "panel_present": "1", "wopen": WOPEN}
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


def _with_ru(title="Привет", body=""):
    cfg = siteconfig.normalize(copy.deepcopy(CFG))
    i = _idx(cfg, "t1")
    entry = {"data": {k: v for k, v in (("title", title), ("body", body)) if v}}
    cfg["i18n"] = {"ru": {"sections": [{}] * i + [entry]}}
    return cfg


@XF
def test_translation_goes_to_the_draft_then_to_the_site():
    b = Browser(_shop())
    _resp, msgs = _post(b, title="Hallo", body="Welt", tr_title_ru="Привет")
    assert msgs == []
    draft = _drafts(b)["home"]
    assert draft["btr"] == {"t1": {"ru": {"title": "Привет"}}}
    assert aufbau_draft.info(b._request("get"), _saved(b), "home")["count"] == 1
    assert _ru(_saved(b), "t1") == {}  # на сайте ничего
    resp, msgs = b.post(seite="home", op="save")
    assert "Gespeichert." in msgs
    assert _ru(_saved(b), "t1") == {"title": "Привет"}
    assert "home" not in _drafts(b)


@XF
def test_same_as_saved_leaves_no_draft():
    b = Browser(_shop(_with_ru()))
    _post(b, title="Hallo", body="Welt", tr_title_ru="Привет")
    assert "home" not in _drafts(b)  # «Übernehmen» без правок — черновика нет
    _post(b, title="Hallo", body="Welt", tr_title_ru="Иначе")
    _post(b, title="Hallo", body="Welt", tr_title_ru="Привет")  # вернул как было
    assert "home" not in _drafts(b)


@XF
def test_german_edit_drops_the_translation_with_a_note():
    cfg = _with_ru()
    cfg["i18n"]["en"] = copy.deepcopy(cfg["i18n"]["ru"])
    cfg["i18n"]["en"]["sections"][-1] = {"data": {"title": "Hi"}}
    b = Browser(_shop(cfg))
    _resp, msgs = _post(b, title="Guten Tag", body="Welt", tr_title_ru="Привет")
    assert any("Übersetzung entfernt" in m and "Русский" in m and "English" in m for m in msgs)
    assert _drafts(b)["home"]["btr"]["t1"] == {"ru": {"title": ""}, "en": {"title": ""}}
    b.post(seite="home", op="save")
    assert _ru(_saved(b), "t1") == {}
    # перевод, введённый в той же форме, остаётся
    b2 = Browser(_shop(_with_ru()))
    _resp, msgs = _post(b2, title="Neu", body="Welt", tr_title_ru="Новое")
    assert not any("Übersetzung entfernt" in m for m in msgs)
    assert _drafts(b2)["home"]["btr"]["t1"] == {"ru": {"title": "Новое"}}


@XF
def test_cancel_returns_only_own_block_translations():
    b = Browser(_shop())
    _post(b, ref="bt1", label="Los", url="/x", tr_label_ru="Вперёд")
    _post(b, title="Hallo", body="Welt", tr_title_ru="Привет")
    resp, msgs = b.post(seite="home", ref="t1", op="revert", wopen=WOPEN)
    assert "Änderungen an diesem Block zurückgenommen." in msgs
    assert _drafts(b)["home"]["btr"] == {"bt1": {"ru": {"label": "Вперёд"}}}


@XF
def test_save_puts_translation_on_the_block_after_reorder():
    b = Browser(_shop())
    _post(b, title="Hallo", body="Welt", tr_body_ru="Мир")
    b.post(seite="home", op="up", ref="t1")
    b.post(seite="home", op="save")
    cfg = _saved(b)
    assert _ru(cfg, "t1") == {"body": "Мир"}


@XF
def test_translation_changed_meanwhile_is_a_conflict():
    from apps.core import block_i18n

    b = Browser(_shop(_with_ru()))
    _post(b, title="Hallo", body="Welt", tr_title_ru="Моё")
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    tenant.site_config = _with_ru(title="Студия")
    tenant.save()
    _resp, msgs = b.post(seite="home", op="save")
    assert block_i18n.conflict_note() in msgs
    assert _ru(_saved(b), "t1") == {"title": "Студия"}
    _resp, msgs = b.post(seite="home", op="save", force="1")
    assert "Gespeichert." in msgs and _ru(_saved(b), "t1") == {"title": "Моё"}


@XF
def test_preview_overlay_shows_the_draft_translation():
    b = Browser(_shop(_with_ru()))
    _post(b, title="Hallo", body="Welt", tr_title_ru="Черновик")
    shown = aufbau_draft.overlay(_saved(b), _drafts(b)["home"])
    local = siteconfig.localize(siteconfig.normalize(shown), "ru")
    row = next(r for r in local["sections"] if r.get("id") == "t1")
    assert row["data"]["title"] == "Черновик"


@XF
def test_page_title_and_confirmation_next():
    cfg = copy.deepcopy(CFG)
    cfg["confirmation_next"] = "Wir melden uns."
    b = Browser(_shop(cfg))
    _post(b, ref="__title", seite="promos", title="Aktionen", tr_title_en="Deals")
    b.post(seite="promos", op="save")
    assert _saved(b)["i18n"]["en"]["page_titles"]["promos"] == {"title": "Deals"}
    _post(b, ref="next", seite="confirmation", text="Wir melden uns.", tr_text_ru="Позвоним.")
    b.post(seite="confirmation", op="save")
    assert _saved(b)["i18n"]["ru"]["confirmation_next"] == "Позвоним."
