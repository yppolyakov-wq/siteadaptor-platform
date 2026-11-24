"""FB-33 стопка 14 E5: общий заголовок FAQ (`section_titles["faq"]`) в окне блока FAQ.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 «E5», §4, §10 (architect H2, H3, M6, L5;
a11y M4). Решение владельца: заголовок ОБЩИЙ, правится во вкладке «Texte» с видимой
подсказкой, через черновик страницы; писатель один — `faq_content.put_title`; нового
хранилища нет; поле — только при общем источнике вопросов.

Замки: окно и «Vorschau» показывают заголовок черновика; возврат к сохранённому снимает
правку; «Abbrechen» возвращает; без строки FAQ не публикуется; конфликт — до записи, текст
не теряется; правка немецкого снимает перевод; Студия (сохранение и превью) переносит
незнакомые ключи `section_titles`; витрина без заголовка — байт-в-байт. Переводы своих
вопросов объекта в окне — по источнику (`object` — поля, `each`/`noaccess` — нет).
"""

import ast
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import polib
import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.core import aufbau_draft, faq_content
from apps.core.tests import test_fb33_m2b2b_window as _ow
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2b2a_before import FAQ4, faq_block
from apps.core.tests.test_fb33_m35b_faq_draft import WOPEN, _faq_post, _tenant
from apps.core.tests.test_fb33_m35b_faq_writers import _req
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]
HINT = "Gilt für alle FAQ-Blöcke der Website. Leer lassen für die Standard-Überschrift."
CONFLICT = (
    "Die Überschrift wurde inzwischen an anderer Stelle geändert – Ihre Fassung wurde nicht "
    "gespeichert."
)
LOCALES = ("de", "en", "ru", "tr", "uk")


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _form(html):
    m = re.search(r'<form[^>]*id="bw-form-faq".*?</form>', html, flags=re.S)
    return m.group(0) if m else ""


def _title_field(form):
    m = re.search(r'<input[^>]*name="faq_title"[^>]*>', form)
    return m.group(0) if m else ""


def _set_saved_title(tenant, text, ru=None):
    t = Tenant.objects.get(pk=tenant.pk)
    cfg = copy.deepcopy(t.site_config)
    cfg.setdefault("section_titles", {})["faq"] = text
    if ru is not None:
        cfg.setdefault("i18n", {}).setdefault("ru", {}).setdefault("section_titles", {})["faq"] = ru
    t.site_config = cfg
    t.save()


def ref_html(host, site_titles=None):
    """Блок FAQ через `render_block` (как `test_fb33_m2b2a_faq_render.ref_html`), с
    сохранёнными заголовками секций."""
    from django.template import Context, Template
    from django.test import RequestFactory

    site = {"faq": FAQ4}
    if site_titles is not None:
        site["section_titles"] = site_titles
    tpl = Template("{% load siteui %}{% render_block b %}")
    ctx = {"request": RequestFactory().get("/"), "site": site, "b": faq_block()}
    return tpl.render(Context({**ctx, "pb_page_key": host}))


def _title(cfg):
    return (cfg.get("section_titles") or {}).get("faq", "")


# ──────────────────── были красными до кода (strict xfail первого коммита) ────────────────────


def test_one_title_writer(monkeypatch):
    """№1: заголовок пишет только `faq_content.put_title` («Speichern» окна — через него)."""
    calls = []
    real = faq_content.put_title
    monkeypatch.setattr(
        faq_content, "put_title", lambda cfg, text: (calls.append(text), real(cfg, text))
    )
    b = Browser(_tenant())
    _faq_post(b, faq_title="Fragen zu uns")
    b.post(seite="home", op="save")
    assert calls == ["Fragen zu uns"] and _title(_saved(b)) == "Fragen zu uns"
    # grep-замок: строка `"faq"` рядом с записью в `section_titles` — только у писателя
    for path in (ROOT / "apps").rglob("*.py"):
        if "tests" in path.parts or path.name == "faq_content.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    src = ast.unparse(tgt)
                    assert not ("section_titles" in src and "'faq'" in src), (path, src)


def _studio_post(tenant, data):
    from apps.core import views

    req = _req(tenant, "post", "/dashboard/site/home/", data)
    return views.home_builder_view(req)


def test_studio_save_keeps_unknown_title_keys(settings):
    """M6: Save Студии пересобирает только `SECTION_TITLE_KEYS`, прочие ключи переносит."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    _set_saved_title(tenant, "Fragen zu uns")
    tenant.refresh_from_db()
    resp = _studio_post(tenant, {"order_events": "1", "enabled_events": "on", "title_events": "E"})
    assert resp.status_code == 302
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert cfg["section_titles"] == {"events": "E", "faq": "Fragen zu uns"}


def test_studio_preview_keeps_faq_title():
    """M6: превью Студии (`site_preview_draft`) не стирает общий заголовок FAQ."""
    from apps.core import views

    tenant = _tenant()
    _set_saved_title(tenant, "Fragen zu uns")
    tenant.refresh_from_db()
    body = json.dumps({"section_titles": {"events": "E", "faq": "Fremd"}})
    req = _req(tenant, "post", "/dashboard/site/preview/", body, content_type="application/json")
    req._body = body.encode()
    views.site_preview_draft(req)
    draft = Tenant.objects.get(pk=tenant.pk).site_config["_draft"]
    assert draft["section_titles"] == {"events": "E", "faq": "Fragen zu uns"}


def test_window_shows_draft_title():
    """H2: правка — в черновик; окно и «Vorschau» (`overlay`) показывают её, сайт — нет."""
    b = Browser(_tenant())
    _faq_post(b, faq_title="Fragen zu uns")
    assert _title(_saved(b)) == ""
    draft = _drafts(b)["home"]
    assert draft["faq_title"] == "Fragen zu uns" and draft["faq_title_base"] == ""
    field = _title_field(_form(b.get("?seite=home&block=faq&tab=texte")))
    assert 'value="Fragen zu uns"' in field
    shown = aufbau_draft.overlay(_saved(b), draft)
    assert _title(shown) == "Fragen zu uns"
    assert aufbau_draft.get(SimpleNamespace(session=b.session), "home") is not None


def test_title_back_to_saved_clears_draft():
    b = Browser(_tenant())
    _set_saved_title(b.tenant, "Alt")
    _faq_post(b, faq_title="Neu")
    assert _drafts(b)["home"]["faq_title"] == "Neu"
    _faq_post(b, faq_title=" Alt ")
    draft = _drafts(b).get("home") or {}
    assert "faq_title" not in draft and "faq_title_base" not in draft


def test_cancel_restores_title():
    b = Browser(_tenant())
    b.get(f"?seite=home&block=faq&tab=texte&wopen={WOPEN}")
    _faq_post(b, faq_title="Neu")
    assert _drafts(b)["home"]["faq_title"] == "Neu"
    b.post(seite="home", ref="faq", op="revert", wopen=WOPEN)
    assert "faq_title" not in (_drafts(b).get("home") or {})
    assert aufbau_draft.get(SimpleNamespace(session=b.session), "home") is None


def test_title_not_written_without_faq_row():
    """H2: блок FAQ из черновика убрали — заголовок «в тени» не публикуется (с заметкой)."""
    b = Browser(_tenant())
    _faq_post(b, seite="text", ref="f1", faq_title="Neu")
    b.post(seite="text", op="delete", ref="f1")
    _resp, msgs = b.post(seite="text", op="save")
    assert _title(_saved(b)) == ""
    assert faq_content.dropped_note() in msgs


def _object_html(scope, monkeypatch):
    from apps.core import view_perms

    if scope == "each":
        tenant, svc, _code = _ow._setup(shared_blocks=[_ow.own_block()])
        return tenant, svc, "service"
    tenant, svc, code = _ow._setup([_ow.own_block()])
    if scope == "noaccess":
        monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: False)
    return tenant, svc, code


@pytest.mark.parametrize("scope", ["object", "each", "noaccess"])
def test_title_field_only_shared(scope, monkeypatch, settings):
    """H3: поле заголовка — только при общем источнике; POST при своём ничего не пишет."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr("apps.core.view_perms.allowed", lambda *a, **k: True)
    tenant, svc, code = _object_html(scope, monkeypatch)
    b = Browser(tenant)
    html = b.get(f"?seite={code}&block=faqown01&tab=texte")
    assert 'name="faq_title"' not in html and HINT not in html
    if scope == "object":
        _ow._post(b, code, svc, faq_title="Fremd", faq_remove="0")
        assert "faq_title" not in (_drafts(b).get(code) or {})
    # контроль: общий источник на той же детальной — поле есть
    shared, _svc, scode = _ow._setup([{"key": "faq_ref", "id": "faqsh01", "enabled": True}])
    monkeypatch.setattr("apps.core.view_perms.allowed", lambda *a, **k: True)
    assert 'name="faq_title"' in Browser(shared).get(f"?seite={scode}&block=faqsh01&tab=texte")


def _req_of(b):
    """Запрос с сессией браузера-заглушки — для прямого `aufbau_draft.commit`."""
    req = b._request("post")
    req.session = b.session
    return req


def test_title_conflict_before_write():
    """№9/№10, ревью E5 №3: заголовок успели сменить в другом месте — без `force` конфликт ДО
    записи (ничего не опубликовано, черновик с набранным заголовком цел), экран конфликта."""
    b = Browser(_tenant())
    _faq_post(b, faq_title="Meine Fassung", faq_move="0:down")
    _set_saved_title(b.tenant, "Andere Fassung")
    saved = _saved(b)
    assert aufbau_draft.info(SimpleNamespace(session=b.session), saved, "home")["conflict"]
    _resp, msgs = b.post(seite="home", op="save")
    cfg = _saved(b)
    assert _title(cfg) == "Andere Fassung"
    assert [f["q"] for f in cfg["faq"]][:2] == ["A?", "B?"]  # вопросы тоже не записаны
    assert _drafts(b)["home"]["faq_title"] == "Meine Fassung"
    assert "Gespeichert." not in msgs
    with pytest.raises(aufbau_draft.DraftConflict):
        aufbau_draft.commit(_req_of(b), Tenant.objects.get(pk=b.tenant.pk), "home")


def test_title_conflict_force_writes_over():
    """Ревью E5 №3: «Trotzdem speichern» (`force`) — заголовок поверх, как вопросы при `force`."""
    b = Browser(_tenant())
    _faq_post(b, faq_title="Meine Fassung")
    _set_saved_title(b.tenant, "Andere Fassung")
    _resp, msgs = b.post(seite="home", op="save", force="1")
    assert "Gespeichert." in msgs and _title(_saved(b)) == "Meine Fassung"
    assert "home" not in _drafts(b)


def test_title_and_question_translations_both_written():
    """Ревью E5 №1 (а): правка переводов вопросов + заголовок (без `faq`) — оба на сайте."""
    from apps.core.tests.test_fb33_m35c_faq import _ml

    b = Browser(_ml(_tenant()))
    _faq_post(b, faq_1_q_ru="Б-новый?", faq_title="Neu")
    assert "faq" not in _drafts(b)["home"]
    _resp, msgs = b.post(seite="home", op="save")
    cfg = _saved(b)
    assert cfg["i18n"]["ru"]["faq"][1]["q"] == "Б-новый?" and _title(cfg) == "Neu"


def test_questions_and_translations_no_false_skip_note():
    """Ревью E5 №1 (б): ↑↓ + перевод — ветка переводов один раз, ложной заметки нет."""
    from apps.core import block_i18n
    from apps.core.tests.test_fb33_m35c_faq import _ml

    b = Browser(_ml(_tenant()))
    _faq_post(b, faq_1_q_ru="Б-новый?")
    _faq_post(b, faq_move="1:up")
    _resp, msgs = b.post(seite="home", op="save")
    assert block_i18n.window_skipped_note() not in msgs
    assert _saved(b)["i18n"]["ru"]["faq"][0]["q"] == "Б-новый?"


def test_title_counts_as_one_change():
    """Ревью E5 №2 (silent-failure M-1): только заголовок — одна правка; с вопросами — две
    (каждая часть FAQ — одна правка, как `faq` и `ofaq`)."""
    b = Browser(_tenant())
    _faq_post(b, faq_title="Neu")
    req = SimpleNamespace(session=b.session)
    assert aufbau_draft.info(req, _saved(b), "home")["count"] == 1
    _faq_post(b, faq_move="0:down", faq_title="Neu")
    assert aufbau_draft.info(req, _saved(b), "home")["count"] == 2


def test_put_title_drops_translation_only_on_change():
    """Ревью E5 №5: перевод заголовка снимается при смене немецкого текста, тот же текст — цел;
    `normalize` перевод заголовка хранит."""
    cfg = siteconfig.normalize(
        {"section_titles": {"faq": "Alt"}, "i18n": {"ru": {"section_titles": {"faq": "Старый"}}}}
    )
    assert cfg["i18n"]["ru"]["section_titles"] == {"faq": "Старый"}
    same = copy.deepcopy(cfg)
    faq_content.put_title(same, " Alt ")
    assert same["i18n"]["ru"]["section_titles"] == {"faq": "Старый"}
    faq_content.put_title(cfg, "Neu")
    assert "section_titles" not in cfg["i18n"]["ru"] and _title(cfg) == "Neu"


def test_german_title_change_drops_translation():
    b = Browser(_tenant())
    _set_saved_title(b.tenant, "Alt", ru="Старый")
    assert _saved(b)["i18n"]["ru"]["section_titles"]["faq"] == "Старый"
    _faq_post(b, faq_title="Neu")
    b.post(seite="home", op="save")
    cfg = _saved(b)
    assert _title(cfg) == "Neu"
    assert "faq" not in ((cfg.get("i18n") or {}).get("ru") or {}).get("section_titles", {})


def test_title_maxlength():
    b = Browser(_tenant())
    field = _title_field(_form(b.get("?seite=home&block=faq&tab=texte")))
    assert f'maxlength="{siteconfig._SECTION_TITLE_MAX}"' in field
    _faq_post(b, faq_title="x" * 120)
    assert _drafts(b)["home"]["faq_title"] == "x" * siteconfig._SECTION_TITLE_MAX


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
def test_storefront_title_with_page_cache(settings):
    """№13: «Speichern» сбрасывает кэш витрины; витрина показывает свой заголовок."""
    from apps.core import pagecache

    cache.clear()
    b = Browser(_tenant())
    _faq_post(b, faq_title="Fragen zu uns")
    before = pagecache._sf_version(b.tenant.schema_name)
    b.post(seite="home", op="save")
    assert pagecache._sf_version(b.tenant.schema_name) > before
    settings.ROOT_URLCONF = "config.urls_tenant"
    html = ref_html("catalog", site_titles={"faq": "Fragen zu uns"})
    assert ">Fragen zu uns</h2>" in html and "Häufig gestellte Fragen" not in html
    detail = ref_html("service_detail", site_titles={"faq": "Fragen zu uns"})
    assert ">Fragen zu uns</h2>" in detail and "Allgemeine Fragen" not in detail


def test_title_field_named():
    """№22, a11y M4: подпись «Überschrift», видимая подсказка с уникальным id в
    `aria-describedby`, поле — до «Fragen»."""
    b = Browser(_tenant())
    form = _form(b.get("?seite=home&block=faq&tab=texte"))
    field = _title_field(form)
    m = re.search(r'aria-describedby="([^"]+)"', field)
    assert m
    hint_id = m.group(1).split()[0]
    hint = re.search(rf'<p[^>]*id="{hint_id}"[^>]*>(.*?)</p>', form, flags=re.S)
    assert hint and HINT in hint.group(1) and "sr-only" not in hint.group(0)
    assert form.count(f'id="{hint_id}"') == 1
    label = re.search(r"<label[^>]*>(?:(?!</label>).)*name=\"faq_title\"", form, flags=re.S)
    assert label and "Überschrift" in label.group(0)
    assert form.index('name="faq_title"') < form.index('id="schema-tab-faq-list"')


# ─────────────────────────────── охранные ───────────────────────────────


def test_e5_msgids_in_all_po():
    """№16: строки среза — во всех пяти каталогах, с переводом."""
    for loc in LOCALES:
        po = polib.pofile(str(ROOT / "locale" / loc / "LC_MESSAGES" / "django.po"))
        for msgid in (HINT, CONFLICT, "Überschrift"):
            entry = po.find(msgid)
            assert entry is not None and entry.msgstr and not entry.obsolete, (loc, msgid)


def test_inline_path_rejects_faq_title():
    """№1/№6: канва заголовок FAQ не правит — ключа нет в `SECTION_TITLE_KEYS`."""
    from apps.core.tests.test_fb33_m35b_faq_writers import _inline
    from apps.core.tests.test_fb33_m35b_faq_writers import _tenant as _wt

    assert "faq" not in siteconfig.SECTION_TITLE_KEYS
    tenant = _wt()
    assert _inline(tenant, "section_titles.faq", "X").status_code == 400
    assert "faq" not in (Tenant.objects.get(pk=tenant.pk).site_config.get("section_titles") or {})


def test_open_draft_fingerprint_unchanged():
    """№11: заголовок вне `_saved_state` — открытый черновик не конфликтует от его записи."""
    b = Browser(_tenant())
    b.post(seite="home", ref="t1", op="toggle")
    _set_saved_title(b.tenant, "Von woanders")
    info = aufbau_draft.info(SimpleNamespace(session=b.session), _saved(b), "home")
    assert info["conflict"] is False


def test_storefront_default_title_bytes(settings):
    """№15: без своего заголовка витрина — прежний msgid байт-в-байт."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    home = ref_html("catalog")
    # msgid «Frequently asked questions» — по-немецки «Häufig gestellte Fragen»
    assert '<h2 class="text-xl md:text-2xl font-bold mb-4">Häufig gestellte Fragen</h2>' in home
    detail = ref_html("service_detail")
    assert '<h2 class="text-xl md:text-2xl font-bold mb-4">Allgemeine Fragen</h2>' in detail


@pytest.mark.parametrize("scope", ["object", "each", "noaccess"])
def test_ofaq_translations_by_scope(scope, monkeypatch, settings):
    """№6: переводы своих вопросов в окне — поля у `object`; у `each`/`noaccess` ни полей,
    ни подписи. Подпись «Übersetzungen ändern Sie im Formular des Angebots» — у `object`,
    когда полей перевода нет (вопросов ещё нет)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr("apps.core.view_perms.allowed", lambda *a, **k: True)
    tenant, svc, code = _object_html(scope, monkeypatch)
    form = _form(Browser(tenant).get(f"?seite={code}&block=faqown01&tab=texte"))
    note = "Übersetzungen ändern Sie im Formular des Angebots"
    if scope == "object":
        assert 'name="faq_0_q_ru"' in form and 'lang="ru"' in form and note not in form
        svc.faq, svc.faq_i18n = [], {}
        svc.save(update_fields=["faq", "faq_i18n"])
        bare = _form(Browser(tenant).get(f"?seite={code}&block=faqown01&tab=texte"))
        assert note in bare
    else:
        assert re.search(r'name="faq_\d+_[qa]_ru"', form) is None and note not in form


def test_ofaq_conflict_before_write(monkeypatch, settings):
    """№10: свои вопросы объекта успели сменить — «Speichern» ничего не пишет (и заголовок)."""
    from apps.core import object_faq

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr("apps.core.view_perms.allowed", lambda *a, **k: True)
    tenant, svc, code = _ow._setup([_ow.own_block(), {"key": "faq_ref", "id": "fsh", "enabled": 1}])
    b = Browser(tenant)
    _faq_post(b, seite=code, ref="fsh", faq_title="Neu")
    _ow._post(b, code, svc, faq_remove="0")
    svc.faq = [{"q": "Anders?", "a": ""}]
    svc.save(update_fields=["faq"])
    _resp, msgs = b.post(seite=code, op="save")
    assert object_faq.error_note("ofaq_conflict") in msgs
    assert _title(_saved(b)) == "" and code in _drafts(b)
