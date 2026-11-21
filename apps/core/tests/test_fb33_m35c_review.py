"""FB-33 M3-5c: замки по ревью django-reviewer и a11y-architect.

H1 удалённый блок не оставляет переводов в черновике (иначе вечный ложный конфликт). H2 переводы
вопросов ключуются индексом источника — изменённый в другом месте немецкий список (общий или
объекта) — конфликт; у своих вопросов — и под блокировкой объекта. M1 «Trotzdem speichern» поверх
изменённых вопросов: перевод из окна остаётся у пункта черновика, где его набрали; без правки
самих вопросов — не применяется, с заметкой. M2 чужие поля перевода игнорируются. A1 подписи
полей перевода однозначны; A2 невидимая «Übernehmen» без aria-hidden; A3 заметка о снятом
переводе начинается с data-prefix живой области; A5 кнопки языка — в одной форме окна.
"""

import copy
import re
from collections import Counter

import pytest
from django.utils import translation

from apps.core import aufbau_draft
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m3_window_before import CASES, _panel
from apps.core.tests.test_fb33_m35b_faq_draft import BASE, _drafts, _faq_post, _saved
from apps.core.tests.test_fb33_m35b_faq_draft import _tenant as faq_tenant
from apps.core.tests.test_fb33_m35c_draft import _live, _post, _shop, _with_ru
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db
XF = pytest.mark.xfail(strict=True, reason="M3-5c ревью: ещё не сделано")


def _ml(tenant, locales=("de", "ru")):
    tenant.enabled_locales = list(locales)
    tenant.save()
    return tenant


def _rewrite(b, fn):
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    cfg = copy.deepcopy(tenant.site_config)
    fn(cfg)
    tenant.site_config = cfg
    tenant.save()


# --- H1 ---------------------------------------------------------------------------------------


@XF
def test_deleted_block_leaves_no_translations_and_no_conflict():
    b = Browser(_shop())
    _post(b, ref="bt1", label="Los", url="/x", tr_label_ru="Вперёд")
    b.post(seite="home", op="delete", ref="bt1")
    draft = _live(b)
    assert "bt1" not in (draft.get("btr") or {}) and "bt1" not in (draft.get("btr_base") or {})
    assert not aufbau_draft.info(b._request("get"), _saved(b), "home")["conflict"]
    _resp, msgs = b.post(seite="home", op="save")
    assert "Gespeichert." in msgs


@XF
def test_conflict_ignores_a_block_that_is_gone():
    from apps.core import block_i18n

    b = Browser(_shop())
    _post(b, ref="bt1", label="Los", url="/x", tr_label_ru="Вперёд")
    draft = copy.deepcopy(_live(b))
    draft["items"] = [it for it in draft["items"] if it.get("id") != "bt1"]
    draft["btr_base"]["bt1"] = "stale"
    assert not block_i18n.conflict(_saved(b), draft)


# --- H2 ---------------------------------------------------------------------------------------


@XF
def test_shared_questions_changed_elsewhere_are_a_conflict():
    from apps.core import block_i18n

    b = Browser(_ml(faq_tenant()))
    _faq_post(b, faq_1_q_ru="Б-новый?")
    assert "faq" not in _drafts(b)["home"]  # только перевод

    def studio(cfg):
        cfg["faq"] = [BASE[1], BASE[2]]  # «A?» удалили в Студии, переводы не тронули

    _rewrite(b, studio)
    _resp, msgs = b.post(seite="home", op="save")
    assert block_i18n.conflict_note() in msgs


def _object_setup():
    from apps.core.tests.test_fb33_m2b2b_window import _setup, own_block

    return _setup(blocks=[own_block()])


@XF
def test_object_questions_changed_elsewhere_are_a_conflict(monkeypatch):
    from apps.core import block_i18n, view_perms
    from apps.core.tests.test_fb33_m2b2b_window import _post as ofaq_post

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant, svc, code = _object_setup()
    b = Browser(tenant)
    ofaq_post(b, code, svc, faq_1_q_ru="Мыть волосы?")
    svc.faq = svc.faq[1:]  # вопрос удалили в форме услуги, переводы те же
    svc.save(update_fields=["faq"])
    _resp, msgs = b.post(seite=code, op="save")
    assert block_i18n.conflict_note() in msgs


@XF
def test_object_commit_rechecks_under_the_lock(monkeypatch):
    from apps.core import object_faq, site_schema, view_perms
    from apps.core.tests.test_fb33_m2b2b_window import _post as ofaq_post

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)
    tenant, svc, code = _object_setup()
    b = Browser(tenant)
    ofaq_post(b, code, svc, faq_1_q_ru="Мыть волосы?")
    draft = copy.deepcopy(_live(b, code))
    svc.faq = svc.faq[1:]  # между проверкой и блокировкой
    svc.save(update_fields=["faq"])
    with pytest.raises(site_schema.SchemaError):
        object_faq.commit(svc, "service", draft, None, [], False)


# --- M1 ---------------------------------------------------------------------------------------


@XF
def test_forced_save_keeps_window_translation_on_its_draft_item():
    b = Browser(_ml(faq_tenant()))
    _faq_post(b, faq_move="1:up", faq_0_q_ru="Б-окно?")  # «B?» первым, перевод набран у него
    assert _drafts(b)["home"]["btr"]["faq"] == {"ru": {"faq.1.q": "Б-окно?"}}

    def studio(cfg):
        cfg["faq"] = [{"q": "Neu?", "a": "0"}, *copy.deepcopy(BASE)]

    _rewrite(b, studio)
    b.post(seite="home", op="save", force="1")
    cfg = _saved(b)
    assert [i["q"] for i in cfg["faq"]] == ["B?", "A?", "C?"]
    assert cfg["i18n"]["ru"]["faq"][0]["q"] == "Б-окно?"


@XF
def test_forced_translation_only_over_changed_questions_is_not_applied_with_a_note():
    b = Browser(_ml(faq_tenant()))
    _faq_post(b, faq_1_q_ru="Б-новый?")

    def studio(cfg):
        cfg["faq"] = [BASE[1], BASE[2]]

    _rewrite(b, studio)
    _resp, msgs = b.post(seite="home", op="save", force="1")
    assert "Übersetzungen aus dem Fenster wurden nicht übernommen." in msgs
    assert all(e.get("q") != "Б-новый?" for e in _saved(b)["i18n"]["ru"]["faq"])


# --- M2 ---------------------------------------------------------------------------------------


def test_object_scope_post_on_shared_faq_writes_nothing():
    b = Browser(_ml(faq_tenant()))
    _faq_post(b, faq_scope="object", faq_0_q_ru="Чужое")
    assert "btr" not in (_drafts(b).get("home") or {})


def test_foreign_translation_fields_are_ignored():
    b = Browser(_shop())
    _post(b, title="Hallo", body="Welt", tr_label_ru="Чужое", tr_title_xx="X", tr_title_de="Y")
    assert _live(b) is None


# --- A1 / A2 / A3 / A5 ------------------------------------------------------------------------


def _html(b, query):
    with translation.override("de"):
        return b.get(query)


@XF
def test_translation_labels_name_the_field():
    html = _html(Browser(_shop(_with_ru())), "?seite=home&block=t1&tab=texte")
    assert '<span lang="de">„Überschrift“</span> – Übersetzung (Русский)' in html
    faq = _html(Browser(_ml(faq_tenant())), "?seite=home&block=faq&tab=texte")
    assert '<span lang="de">„Frage 1“</span> – Übersetzung (Русский)' in faq
    assert '<span lang="de">„Antwort 1“</span> – Übersetzung (Русский)' in faq


@XF
def test_invisible_apply_button_is_not_aria_hidden():
    html = _html(Browser(_shop(_with_ru())), "?seite=home&block=t1&tab=texte")
    form = re.search(r'<form[^>]*id="bw-form-fields".*?</form>', html, flags=re.S).group(0)
    first = re.search(r"<button[^>]*>", form).group(0)
    assert "sr-only" in first and 'tabindex="-1"' in first and "aria-hidden" not in first
    # скрытое op и кнопка op — одна операция: кнопка языка применяет форму без отказа
    b = Browser(_shop())
    data = {"seite": "home", "ref": "t1", "panel_present": "1", "op": "update"}
    resp, msgs = b.post(**data, f_title="Hallo", f_body="Welt", f_tr_title_ru="П", f_sprache="en")
    assert msgs == [] and resp["Location"].endswith("#schema-tab-lang-en")


@XF
def test_dropped_note_starts_with_the_live_region_prefix():
    cfg = _with_ru()
    b = Browser(_shop(cfg))
    html = _html(b, "?seite=home&block=t1&tab=texte")
    box = re.search(r'<p role="status"[^>]*data-form-status[^>]*>', html).group(0)
    assert 'aria-atomic="true"' in box
    prefix = re.search(r'data-prefix="([^"]*)"', box).group(1).strip()
    with translation.override("de"):
        _resp, msgs = _post(b, title="Neu", body="Welt", tr_title_ru="Привет")
    assert msgs and msgs[0].startswith(prefix)
    page = _html(b, "?seite=home&block=t1&tab=texte")
    shown = page[page.index("data-schema-messages") :]
    assert msgs[0].split(":")[0] in shown


def test_language_buttons_live_in_one_form_of_a_window():
    tenant = _shop(_with_ru(), locales=("de", "ru", "en"))
    for case in CASES:
        code, ref, extra = (*case, "")[:3]
        panel = _panel(_html(Browser(tenant), f"?seite={code}&block={ref}{extra}"))
        assert panel.count("data-form-langs") <= 1, case
        ids = Counter(re.findall(r'\bid="([^"]+)"', panel))
        assert [i for i, n in ids.items() if n > 1] == [], case


@XF
def test_shown_reads_only_strings():
    from apps.core import block_i18n

    draft = {"btr": {"t1": {"ru": {"title": 5}}}}
    assert block_i18n.shown({"ru": {"title": "S"}}, draft, "t1", "ru", "title") == "S"
