"""FB-33 стопка 16 T1a: переводы полосы доверия (USP) в окне блока «Vorteile» → «Texte».

План — `docs/fb33-stack16-plan-2026-11-26.md` §2 «T1a», замки §4 «T1a». Писатель переводов —
`block_i18n` (вид `usp`); поле перевода — по позиции пункта в окне НА МОМЕНТ ПОКАЗА, ключ
пункта в черновике — его место в сохранённом списке (`src`, едет с пунктом при ↑/↓/✕); на сайт
переводы выравнивает подъём USP (`site_schema.lift_hero_choice` → `block_i18n.realign_usp`).
"""

import ast
import copy
import re
from collections import Counter
from pathlib import Path

import pytest
from django.utils import translation

from apps.core import aufbau_draft, block_i18n, home_texts
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _tenant
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.xfail(strict=True, reason="T1a: переводы USP в окне — ещё нет"),
]

USP = [
    {"icon": "bio", "label": "Frisch", "text": "Jeden Tag"},
    {"icon": "local", "label": "Regional", "text": "aus Solingen"},
]
RU = [
    {"label": "Свежо", "text": "Каждый день"},
    {"label": "Местное", "text": "из Золингена"},
]
WOPEN = "openT1a"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(usp=None, ru=None, locales=("de", "ru", "en")):
    tenant = _tenant()
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["usp_bar"] = copy.deepcopy(USP if usp is None else usp)
    for s in cfg["sections"]:
        if s["key"] == "usp_bar":
            s["enabled"] = True
    if ru is not False:
        cfg["i18n"] = {"ru": {"usp_bar": copy.deepcopy(RU if ru is None else ru)}}
    tenant.site_config = cfg
    tenant.enabled_locales = list(locales)
    tenant.default_locale = "de"
    tenant.save()
    return Browser(tenant)


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _items_of(b):
    draft = ((b.session or {}).get(aufbau_draft.SESSION_KEY) or {}).get("home") or {}
    row = next((r for r in draft.get("items") or [] if r.get("key") == "usp_bar"), None)
    if row:
        return (row.get("data") or {}).get("items") or []
    return siteconfig.clean_usp(_saved(b).get("usp_bar"))


def _post(b, items=None, **extra):
    """Форма USP окна: все пункты (как их показывает окно сейчас) и пустой «＋ Punkt»."""
    items = _items_of(b) if items is None else items
    data = {
        "seite": "home",
        "op": "update",
        "ref": "usp_bar",
        "panel_present": "1",
        "wopen": WOPEN,
    }
    for i, it in enumerate(items):
        data[f"f_usp_{i}_icon"] = it.get("icon", "check")
        data[f"f_usp_{i}_label"] = it.get("label", "")
        data[f"f_usp_{i}_text"] = it.get("text", "")
    data[f"f_usp_{len(items)}_icon"] = "check"
    data[f"f_usp_{len(items)}_label"] = ""
    data[f"f_usp_{len(items)}_text"] = ""
    data.update(extra)
    return b.post(**data)


def _save(b, **extra):
    return b.post(seite="home", op="save", **extra)


def _shown(cfg, lang):
    return [
        (it["label"], it.get("text", ""))
        for it in siteconfig.localize(copy.deepcopy(cfg), lang)["usp_bar"]
    ]


def _form(b, query="?seite=home&block=usp_bar&tab=texte"):
    with translation.override("de"):
        html = b.get(query)
    m = re.search(r'<form[^>]*id="bw-form-usp".*?</form>', html, flags=re.S)
    return html, (m.group(0) if m else "")


# --- №12: перестановка, удаление, новый пункт ---------------------------------------------


def test_usp_move_keeps_translation_on_its_item():
    b = _browser()
    _post(b, f_usp_move="0:down")
    draft = (b.session or {})[aufbau_draft.SESSION_KEY]["home"]
    preview = siteconfig.normalize(aufbau_draft.overlay(_saved(b), draft))
    assert _shown(preview, "ru") == [("Местное", "из Золингена"), ("Свежо", "Каждый день")]
    _save(b)
    cfg = _saved(b)
    assert [u["label"] for u in cfg["usp_bar"]] == ["Regional", "Frisch"]
    assert _shown(cfg, "ru") == [("Местное", "из Золингена"), ("Свежо", "Каждый день")]


def test_usp_remove_drops_its_translation():
    b = _browser()
    _post(b, f_usp_remove="0")
    _save(b)
    cfg = _saved(b)
    assert [u["label"] for u in cfg["usp_bar"]] == ["Regional"]
    assert _shown(cfg, "ru") == [("Местное", "из Золингена")]


def test_usp_new_item_has_no_translation_fields():
    b = _browser()
    _html, form = _form(b)
    assert 'id="bw-usp-0-label-ru"' in form and 'name="f_tr_usp_0_label_ru"' in form
    assert 'name="f_tr_usp_2_label_ru"' not in form, "пустая строка «＋ Punkt» — без перевода"
    _post(b, **{"f_usp_2_label": "Neu", "f_usp_2_icon": "clock"})
    _html, form = _form(b, f"?seite=home&block=usp_bar&tab=texte&wopen={WOPEN}")
    assert 'value="Neu"' in form
    assert "bw-usp-2-label" not in form, "новый пункт — поля перевода после «Speichern»"
    assert 'name="f_tr_usp_1_label_ru"' in form


# --- №17: правка немецкого снимает перевод своего поля ----------------------------------------


def test_usp_label_edit_drops_translation():
    b = _browser()
    items = copy.deepcopy(USP)
    items[0]["label"] = "Frischer"
    _resp, msgs = _post(b, items=items)
    assert any("Übersetzung entfernt" in m and "Русский" in m for m in msgs)
    _save(b)
    assert _shown(_saved(b), "ru") == [("Frischer", "Каждый день"), ("Местное", "из Золингена")]


def test_usp_text_edit_drops_text_translation_only():
    b = _browser()
    items = copy.deepcopy(USP)
    items[0]["text"] = "Täglich"
    _post(b, items=items)
    _save(b)
    assert _shown(_saved(b), "ru") == [("Свежо", "Täglich"), ("Местное", "из Золингена")]


# --- architect №3, №4: ключ пункта — сам переводимый текст; дубли -----------------------------


def test_usp_label_edit_keeps_typed_translation():
    b = _browser()
    items = copy.deepcopy(USP)
    items[0]["label"] = "Frischer"
    _resp, msgs = _post(b, items=items, f_tr_usp_0_label_ru="Свежее")
    assert not any("Übersetzung entfernt" in m for m in msgs)
    _save(b)
    assert _shown(_saved(b), "ru") == [("Свежее", "Каждый день"), ("Местное", "из Золингена")]
    # то же со «↓» в той же форме: поле перевода — по позиции показа, пункт уехал вниз
    b = _browser()
    _post(b, items=items, f_tr_usp_0_label_ru="Свежее", f_usp_move="0:down")
    _save(b)
    cfg = _saved(b)
    assert [u["label"] for u in cfg["usp_bar"]] == ["Regional", "Frischer"]
    assert _shown(cfg, "ru") == [("Местное", "из Золингена"), ("Свежее", "Каждый день")]


def test_duplicate_key_items_no_shared_field():
    usp = [{"icon": "bio", "label": "Gleich"}, {"icon": "local", "label": "Gleich"}]
    b = _browser(usp=usp, ru=False)
    html, form = _form(b)
    names = re.findall(r'name="(f_tr_usp_\d+_label_ru)"', form)
    assert names == ["f_tr_usp_0_label_ru", "f_tr_usp_1_label_ru"]
    ids = Counter(re.findall(r'\bid="([^"]+)"', _panel(html)))
    assert [i for i, n in ids.items() if n > 1] == []
    _post(b, f_tr_usp_1_label_ru="Второй")
    _save(b)
    assert _shown(_saved(b), "ru") == [("Gleich", ""), ("Второй", "")]
    _post(b, f_usp_move="1:up")
    _save(b)
    assert _shown(_saved(b), "ru") == [("Второй", ""), ("Gleich", "")]


# --- architect №11: CRLF из формы перевод не снимает ------------------------------------------


def test_usp_crlf_text_keeps_translation():
    usp = [{"icon": "bio", "label": "Frisch", "text": "Zeile eins\nZeile zwei"}]
    b = _browser(usp=usp, ru=[{"label": "Свежо", "text": "Строка"}])
    items = copy.deepcopy(usp)
    items[0]["text"] = "Zeile eins\r\nZeile zwei"
    _resp, msgs = _post(b, items=items)
    assert not any("Übersetzung entfernt" in m for m in msgs)
    _save(b)
    assert _shown(_saved(b), "ru") == [("Свежо", "Строка")]
    # общая функция снятия (`home_texts.drop_changed`) сверяет после `_nl`
    cfg = {"i18n": {"ru": {"about_text": "Привет"}}, "about_text": "a\nb"}
    home_texts.drop_changed(cfg, "about", {"about_text": "a\nb"}, {"about_text": "a\r\nb"})
    assert cfg["i18n"]["ru"].get("about_text") == "Привет"


# --- №1/№2: один писатель ----------------------------------------------------------------------


_OVERLAY_WRITERS = {"set_overlay_value", "_set_path", "drop_changed", "realign_list_overlays"}
_OVERLAY_NODES = {"node", "overlay", "ov", "tr", "lang_node"}


def _has_usp(node) -> bool:
    return any(isinstance(n, ast.Constant) and n.value == "usp_bar" for n in ast.walk(node))


def _writes_usp_overlay(tree) -> list[str]:
    """Функции, которые пишут перевод `i18n.<язык>.usp_bar`: запись оверлея по пути с
    «usp_bar» или присваивание `<узел языка>["usp_bar"] = …`."""
    hits = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "attr", getattr(n.func, "id", ""))
                if name in _OVERLAY_WRITERS and any(_has_usp(a) for a in n.args):
                    hits.append(fn.name)
                    break
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if (
                        isinstance(t, ast.Subscript)
                        and isinstance(t.slice, ast.Constant)
                        and t.slice.value == "usp_bar"
                        and (
                            "i18n" in ast.unparse(t.value)
                            or (isinstance(t.value, ast.Name) and t.value.id in _OVERLAY_NODES)
                        )
                    ):
                        hits.append(fn.name)
    return sorted(set(hits))


def test_usp_translation_written_by_block_i18n_only():
    root = Path(__file__).resolve().parents[3] / "apps"
    found = {}
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        hits = _writes_usp_overlay(ast.parse(path.read_text(encoding="utf-8")))
        if hits:
            found[str(path.relative_to(root))] = sorted(hits)
    assert set(found) <= {"core/block_i18n.py"}, found
    assert "realign_usp" in found.get("core/block_i18n.py", []), found


# --- №9/№10: конфликт ---------------------------------------------------------------------------


def test_usp_translation_conflict():
    b = _browser()
    _post(b, f_tr_usp_0_label_ru="Моё")
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["i18n"]["ru"]["usp_bar"][0]["label"] = "Студия"
    tenant.site_config = cfg
    tenant.save()
    _resp, msgs = _save(b)
    assert block_i18n.conflict_note() in msgs
    assert _shown(_saved(b), "ru")[0][0] == "Студия"
    _resp, msgs = _save(b, force="1")
    assert "Gespeichert." in msgs and _shown(_saved(b), "ru")[0][0] == "Моё"


# --- №26 / a11y №13: потолки ---------------------------------------------------------------------


def test_usp_translation_caps():
    b = _browser()
    _html, form = _form(b)
    assert re.search(r'id="bw-usp-0-label-ru"[^>]*maxlength="120"', form)
    assert re.search(r'id="bw-usp-0-text-ru"[^>]*maxlength="200"', form)
    _resp, msgs = _post(b, f_tr_usp_0_label_ru="Л" * 130)
    assert siteconfig.cap_note() in msgs
    # `\r\n` формы — один символ, как у `maxlength`: 200 после нормализации — без обрезки
    text = "а" * 100 + "\r\n" + "б" * 99
    _resp, msgs = _post(b, f_tr_usp_0_label_ru="Л" * 120, f_tr_usp_0_text_ru=text)
    assert siteconfig.cap_note() not in msgs
    _save(b)
    ru = _saved(b)["i18n"]["ru"]["usp_bar"][0]
    assert ru["label"] == "Л" * 120 and ru["text"] == "а" * 100 + "\n" + "б" * 99


# --- №13: витрина на языке посетителя ----------------------------------------------------------


def test_storefront_usp_in_ru():
    b = _browser(ru=False)
    _post(b, f_tr_usp_0_label_ru="Свежо", f_tr_usp_1_text_ru="из Золингена")
    _save(b)
    cfg = _saved(b)
    assert _shown(cfg, "ru") == [("Свежо", "Jeden Tag"), ("Regional", "из Золингена")]
    assert _shown(cfg, "de") == [("Frisch", "Jeden Tag"), ("Regional", "aus Solingen")]
    assert _shown(cfg, "en") == [("Frisch", "Jeden Tag"), ("Regional", "aus Solingen")]


# --- №22 / a11y №12: кнопка по умолчанию; a11y №4: свой ns блока языков ------------------------


def test_usp_default_button_window_default():
    """Enter в поле перевода — «Übernehmen» (первая кнопка формы), не ↓/✕ первого пункта и не
    кнопка языка. Невидимая кнопка — вне Tab (`tabindex="-1"`) и без `aria-hidden`: правило
    M3-5a разрешает `aria-hidden` только кнопке окна `data-window-default`, а её в форме USP
    нет (охранный замок `test_fb33_e3_wie_nojs`: у `usp_bar` вкладки — ссылки)."""
    _html, form = _form(_browser())
    first = re.search(r"<button[^>]*>", form).group(0)
    assert 'value="update"' in first and "sr-only" in first and 'tabindex="-1"' in first
    assert "aria-hidden" not in first
    assert form.index(first) < form.index('name="f_sprache"') < form.index('name="f_usp_move"')


def test_usp_form_passes_own_lang_ns():
    b = _browser()
    html, form = _form(b)
    assert 'id="usp-lang-title"' in form and 'id="schema-tab-lang-usp-ru"' in form
    assert 'aria-describedby="bw-usp-0-label-ru-src usp-lang-hint"' in form
    ids = Counter(re.findall(r'\bid="([^"]+)"', _panel(html)))
    assert [i for i, n in ids.items() if n > 1] == []
    resp, _msgs = _post(b, f_sprache="en", lang_ns="usp")
    assert resp["Location"].endswith("#schema-tab-lang-usp-en")
    resp, _msgs = _post(b, f_sprache="en", lang_ns="evil")
    assert resp["Location"].endswith("#schema-tab-lang-en")


# --- черновик до среза --------------------------------------------------------------------------


def test_usp_open_drafts_fingerprint_unchanged():
    b = _browser()
    # сохранённое состояние строки USP — прежней формы (отпечаток черновиков до среза)
    state = aufbau_draft._saved_state(_saved(b), True, "")
    row = next(r for r in state["items"] if r.get("key") == "usp_bar")
    assert row["data"] == {"items": siteconfig.clean_usp(USP)}
    # кнопка языка без правок — черновика нет
    _post(b, f_sprache="en", lang_ns="usp")
    assert aufbau_draft.get(type("R", (), {"session": b.session})(), "home") is None
    # черновик до среза: пункты переставлены без `src` — «Speichern» без конфликта, переводы
    # узнаются по ключу (правило D9 `_match_items`)
    _post(b, f_usp_move="0:down")
    drafts = copy.deepcopy(b.session[aufbau_draft.SESSION_KEY])
    row = next(r for r in drafts["home"]["items"] if r.get("key") == "usp_bar")
    row["data"] = {"items": row["data"]["items"]}  # так черновик писал до T1a
    b.session[aufbau_draft.SESSION_KEY] = drafts
    _resp, msgs = _save(b)
    assert "Gespeichert." in msgs
    assert _shown(_saved(b), "ru") == [("Местное", "из Золингена"), ("Свежо", "Каждый день")]
