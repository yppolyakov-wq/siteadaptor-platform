"""FB-33 стопка 16 T6 (S15-item-i18n): переводы шагов, команды и отзывов во «Texte» окна.

План — `docs/fb33-stack16-plan-2026-11-26.md` §2 «T6», замки §4 «T6», артборд M16SchritteTeam.
Решение владельца: шаг — Titel и Text, команда — Rolle, отзыв — Zitat; имена людей не
переводятся. Писатель переводов — `block_i18n` (ключи `item.<место в сохранённом списке>.<поле>`);
поле перевода — по позиции пункта в окне при показе (снимок `htx_of`), пункт узнаётся по ключу
(`title` шага, `name` человека) правилом D9 `siteconfig._match_items` (дубли — по порядку
вхождения, переименование — по месту); хранение — тот же позиционный оверлей
`i18n.<язык>.<секция>`, что у Студии.
"""

from __future__ import annotations

import copy
import re
from collections import Counter

import pytest
from django.utils import translation

from apps.core import aufbau_draft, block_i18n, home_texts
from apps.core.tests.form_post import form_post
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

FORM = "bw-form-hometext"
WOPEN = "openT6"
#: замок до кода (снимается в коммите реализации)
_T6 = pytest.mark.xfail(strict=True, reason="T6: переводы пунктов ещё не в окне")

PROCESS = [{"title": "Wählen", "text": "Online"}, {"title": "Abholen", "text": "Laden"}]
PROCESS_RU = [{"title": "Выбрать", "text": "Онлайн"}, {"title": "Забрать", "text": "В магазине"}]
TEAM = [
    {"name": "Anna", "role": "Chefin", "photo": ""},
    {"name": "Anna", "role": "Bäckerin", "photo": ""},
]
TEAM_RU = [{"role": "Шеф"}, {"role": "Пекарь"}]
TESTI = [{"name": "Eva", "text": "Super!"}, {"name": "Max", "text": "Lecker"}]
TESTI_RU = [{"text": "Супер!"}, {"text": "Вкусно"}]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _browser(ru=True, locales=("de", "ru")):
    tenant = _tenant()
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["process"] = copy.deepcopy(PROCESS)
    cfg["team"] = copy.deepcopy(TEAM)
    cfg["testimonials"] = copy.deepcopy(TESTI)
    for s in cfg["sections"]:
        if s["key"] in ("process", "team", "testimonials", "about"):
            s["enabled"] = True
    if ru:
        cfg["i18n"] = {
            "ru": {
                "process": copy.deepcopy(PROCESS_RU),
                "team": copy.deepcopy(TEAM_RU),
                "testimonials": copy.deepcopy(TESTI_RU),
            }
        }
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.enabled_locales = list(locales)
    tenant.default_locale = "de"
    tenant.save()
    return Browser(tenant)


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _get(b, ref, extra=""):
    with translation.override("de"):
        return b.get(f"?seite=home&block={ref}&tab=texte&wopen={WOPEN}{extra}")


def _form(html):
    m = re.search(rf'<form[^>]*id="{FORM}".*?</form>', _panel(html), flags=re.S)
    return m.group(0) if m else ""


def _post(b, ref, **change):
    """Форма «Texte» окна так, как её шлёт браузер, плюс правка."""
    data, _p = form_post(_panel(_get(b, ref)), FORM)
    assert data, "формы bw-form-hometext нет"
    data["seite"], data["wopen"] = ["home"], [WOPEN]
    data.setdefault("op", ["update"])
    for name, value in change.items():
        data[name] = [value]
    with translation.override("de"):
        return b.post(**data)


def _save(b, **extra):
    with translation.override("de"):
        return b.post(seite="home", op="save", **extra)


def _ru(cfg, key, *fields):
    return [
        tuple(it.get(f, "") for f in fields)
        for it in siteconfig.localize(copy.deepcopy(cfg), "ru")[key]
    ]


def _value(form, name):
    m = re.search(rf'<(?:input|textarea)\b[^>]*name="{name}"[^>]*>([^<]*)', form)
    if not m:
        return None
    tag = m.group(0)
    v = re.search(r'value="([^"]*)"', tag)
    return v.group(1) if v and tag.startswith("<input") else m.group(1)


# --- №12: перестановка ------------------------------------------------------------------------


@_T6
def test_item_translation_by_key_survives_move():
    b = _browser()
    _post(
        b,
        "process",
        f_htx_process_0_title="Abholen",
        f_htx_process_0_text="Laden",
        f_htx_process_1_title="Wählen",
        f_htx_process_1_text="Online",
    )
    form = _form(_get(b, "process"))
    assert _value(form, "f_tr_htx_process_0_title_ru") == "Забрать", "поле едет за шагом"
    assert _value(form, "f_tr_htx_process_1_text_ru") == "Онлайн"
    _save(b)
    cfg = _saved(b)
    assert [p["title"] for p in cfg["process"]] == ["Abholen", "Wählen"]
    assert _ru(cfg, "process", "title", "text") == [
        ("Забрать", "В магазине"),
        ("Выбрать", "Онлайн"),
    ]


# --- №17: правка немецкого, новый пункт ----------------------------------------------------------


@_T6
def test_item_key_edit_drops_translation():
    b = _browser()
    _resp, msgs = _post(b, "process", f_htx_process_0_title="Aussuchen")
    assert any(m.startswith("Übersetzung entfernt") for m in msgs), msgs
    _save(b)
    cfg = _saved(b)
    assert _ru(cfg, "process", "title", "text") == [
        ("Aussuchen", "Онлайн"),
        ("Забрать", "В магазине"),
    ], "снят только перевод изменённого поля, перевод текста шага остался (по месту, D9)"


@_T6
def test_new_item_has_no_translation_fields():
    b = _browser()
    form = _form(_get(b, "process"))
    assert 'name="f_tr_htx_process_0_title_ru"' in form
    assert "f_tr_htx_process_2_" not in form, "пустой пункт «neu» — без перевода"
    _post(b, "process", f_htx_process_2_title="Genießen", f_htx_process_2_text="Zuhause")
    form = _form(_get(b, "process"))
    assert 'name="f_htx_process_2_title" value="Genießen"' in form
    assert "f_tr_htx_process_2_" not in form, "новый пункт — поля перевода после «Speichern»"
    _save(b)
    form = _form(_get(b, "process"))
    assert 'name="f_tr_htx_process_2_title_ru"' in form


# --- architect №3: правка немецкого и ввод перевода в одной форме --------------------------------


@_T6
def test_step_title_edit_keeps_typed_translation():
    b = _browser()
    _post(
        b,
        "process",
        f_htx_process_0_title="Aussuchen",
        f_tr_htx_process_0_title_ru="Подобрать",
    )
    form = _form(_get(b, "process"))
    assert _value(form, "f_tr_htx_process_0_title_ru") == "Подобрать"
    _save(b)
    assert _ru(_saved(b), "process", "title", "text") == [
        ("Подобрать", "Онлайн"),
        ("Забрать", "В магазине"),
    ]


# --- architect №4: дубли ключа -------------------------------------------------------------------


@_T6
def test_duplicate_name_items_no_shared_field():
    b = _browser()
    form = _form(_get(b, "team"))
    assert _value(form, "f_tr_htx_team_0_role_ru") == "Шеф"
    assert _value(form, "f_tr_htx_team_1_role_ru") == "Пекарь", "вторая «Anna» — своё поле"
    _post(b, "team", f_htx_team_0_role="Inhaberin", f_tr_htx_team_1_role_ru="Пекарша")
    _save(b)
    cfg = _saved(b)
    assert [(m["name"], m["role"]) for m in cfg["team"]] == [
        ("Anna", "Inhaberin"),
        ("Anna", "Bäckerin"),
    ]
    assert _ru(cfg, "team", "name", "role") == [("Anna", "Inhaberin"), ("Anna", "Пекарша")]


@_T6
def test_duplicate_names_realign_by_order_on_move():
    """Дубли — k-й ↔ k-й (D9), не все на первый (`realign_list_overlays` — первое вхождение)."""
    b = _browser()
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["team"].append({"name": "Ben", "role": "Lehrling", "photo": ""})
    cfg["i18n"]["ru"]["team"].append({"role": "Ученик"})
    tenant.site_config = cfg
    tenant.save()
    _post(b, "team", f_htx_team_2_name="", f_htx_team_2_role="")
    _save(b)
    assert _ru(_saved(b), "team", "role") == [("Шеф",), ("Пекарь",)]


# --- architect №11: CRLF ---------------------------------------------------------------------


def test_item_crlf_keeps_translation():
    b = _browser()
    _post(
        b,
        "process",
        f_htx_process_0_text="Online\r\n",
        f_htx_process_1_text="Im Laden",
        f_tr_htx_process_0_text_ru="Онлайн\r\n",
    )
    _save(b)
    cfg = _saved(b)
    assert _ru(cfg, "process", "text") == [("Онлайн",), ("Im Laden",)]


@_T6
def test_item_translation_one_line():
    """Пункт Студии — строка «A | B»: перевод без переноса строки и без «|»."""
    b = _browser()
    _post(b, "testimonials", f_tr_htx_testimonials_0_text_ru="Очень\r\nхорошо | да")
    _save(b)
    assert _ru(_saved(b), "testimonials", "text")[0] == ("Очень хорошо / да",)


# --- №10/№9: конфликт со Студией ------------------------------------------------------------


@_T6
def test_item_translation_conflict_with_studio():
    b = _browser()
    _post(b, "process", f_tr_htx_process_0_title_ru="Подобрать")
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["i18n"]["ru"]["process"][0]["title"] = "Студия"
    tenant.site_config = cfg
    tenant.save()
    _resp, msgs = _save(b)
    assert block_i18n.conflict_note() in msgs
    assert _ru(_saved(b), "process", "title")[0] == ("Студия",)
    _resp, msgs = _save(b, force="1")
    assert _ru(_saved(b), "process", "title")[0] == ("Подобрать",)


# --- №1: один формат хранения со Студией ---------------------------------------------------------


@_T6
def test_studio_and_window_same_overlay():
    b = _browser()
    _post(b, "testimonials", f_tr_htx_testimonials_1_text_ru="Очень вкусно")
    _save(b)
    cfg = _saved(b)
    assert cfg["i18n"]["ru"]["testimonials"][1] == {"text": "Очень вкусно"}
    # Студия в режиме ru видит перевод окна (localize) и её Save его не уносит в базу
    shown = siteconfig.localize(copy.deepcopy(cfg), "ru")
    assert shown["testimonials"][1]["text"] == "Очень вкусно"
    payload = copy.deepcopy(shown)
    payload["testimonials"][0]["text"] = "Супер-пупер!"
    payload["i18n"] = copy.deepcopy(cfg["i18n"])
    split = siteconfig.split_translation(payload, cfg, "ru")
    assert [t["text"] for t in split["testimonials"]] == ["Super!", "Lecker"]
    # …и окно видит перевод Студии
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    tenant.site_config = siteconfig.normalize(split)
    tenant.save()
    form = _form(_get(b, "testimonials"))
    assert _value(form, "f_tr_htx_testimonials_0_text_ru") == "Супер-пупер!"


# --- a11y №11: разметка пункта -------------------------------------------------------------


@_T6
def test_item_translation_fieldset_legend():
    b = _browser()
    with translation.override("de"):
        form = _form(_get(b, "process"))
    assert re.search(r'<legend[^>]*>Schritt 1 · <span lang="de">„Wählen“</span></legend>', form)
    assert "Schritt 3 – neu – leer lassen, wenn nicht benötigt</legend>" in form
    labels = re.findall(r'<label for="schema-f-htx_process_0_title-ru"[^>]*>(.*?)</label>', form)
    assert labels and re.sub(r"<[^>]+>", "", labels[0]) == "Titel – Übersetzung (Русский)"
    names = re.findall(r'name="(f_tr_[^"]+)"', form)
    assert names and len(names) == len(set(names))
    assert set(names) == {
        "f_tr_htx_process_0_title_ru",
        "f_tr_htx_process_0_text_ru",
        "f_tr_htx_process_1_title_ru",
        "f_tr_htx_process_1_text_ru",
    }
    assert "data-form-langs" in form and 'id="htx-process-lang-title"' in form
    assert 'name="lang_ns" value="htx-process"' in form


# --- a11y №13: потолки ---------------------------------------------------------------------


@_T6
def test_item_caps_crlf_and_focus():
    b = _browser()
    form = _form(_get(b, "process"))
    assert re.search(r'id="schema-f-htx_process_0_title-ru"[^>]*maxlength="120"', form)
    assert re.search(r'id="schema-f-htx_process_0_text-ru"[^>]*maxlength="2000"', form)
    # 1000 строк по «\r\n» — 2000 символов в браузере (maxlength считает перенос за один)
    text = "\r\n".join(["x"] * 1000)
    _resp, msgs = _post(b, "process", f_tr_htx_process_0_text_ru=text)
    assert siteconfig.cap_note() not in msgs
    _resp, msgs = _post(b, "process", f_tr_htx_process_0_title_ru="я" * 130)
    assert siteconfig.cap_note() in msgs
    _save(b)
    assert _ru(_saved(b), "process", "title")[0] == ("я" * 120,)


# --- §9 №5: имена не переводятся --------------------------------------------------------------


@_T6
def test_names_not_translatable():
    assert home_texts.TR_ITEM_FIELDS == {
        "process": ("title", "text"),
        "team": ("role",),
        "testimonials": ("text",),
    }
    b = _browser()
    for key in ("team", "testimonials"):
        form = _form(_get(b, key))
        assert f"f_tr_htx_{key}_0_name_" not in form
        assert "Name wird nicht übersetzt." in form
        assert re.search(
            rf'name="f_htx_{key}_0_name"[^>]*aria-describedby="[^"]*schema-f-htx_{key}_0_name-nt',
            form,
        )
    _post(b, "team", f_tr_htx_team_0_name_ru="Анна")
    assert "btr" not in (b.session.get(aufbau_draft.SESSION_KEY) or {}).get("home", {})


def test_one_language_window_unchanged():
    b = _browser(ru=False, locales=("de",))
    form = _form(_get(b, "team"))
    assert "f_tr_" not in form and "Name wird nicht übersetzt." not in form
    assert "<legend" in form and " · " not in form


# --- a11y №4: уникальность id -------------------------------------------------------------


@pytest.mark.parametrize("ref", ["process", "team", "testimonials", "about"])
def test_no_duplicate_ids_across_home_parts(ref):
    b = _browser()
    html = _get(b, ref)
    ids = Counter(re.findall(r'\sid="([^"]+)"', html))
    assert [i for i, n in ids.items() if n > 1] == []


# --- «Übersetzen» (T3): источник текста ---------------------------------------------------


@_T6
def test_translate_button_source(monkeypatch):
    from apps.core.tests import test_fb33_m2i5c_translate as m2i5c

    m2i5c._ai(monkeypatch)
    b = m2i5c._ScreenBrowser(_browser().tenant)
    form = _form(_get(b, "process"))
    assert "data-i18n-translate" in form
    tag = re.search(r'<input[^>]*name="f_tr_htx_process_1_title_ru"[^>]*>', form).group(0)
    assert 'data-i18n-of="f_htx_process_1_title"' in tag
    assert 'id="bwtr-status-htx-process"' in form


# --- a11y №14: витрина ru ------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="T6: признак «без перевода» — тег siteui (T1b, apps/tenants/templatetags/siteui.py "
    "вне строки T6 плана §3) — нужен plan_check --add",
)
def test_storefront_items_untranslated_lang_de(rf):
    from django.template.loader import render_to_string

    b = _browser()
    tenant = Tenant.objects.get(pk=b.tenant.pk)
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["i18n"]["ru"]["process"][1] = {}
    tenant.site_config = cfg
    tenant.save()
    req = rf.get("/")
    req.tenant = tenant
    with translation.override("ru"):
        html = render_to_string(
            "storefront/sections/_process.html",
            {"site": siteconfig.localize(copy.deepcopy(cfg), "ru"), "section_row": {}},
            request=req,
        )
    assert re.search(r'<h3[^>]*lang="de"[^>]*>Abholen', html)
    assert not re.search(r'<h3[^>]*lang="de"[^>]*>Выбрать', html)
