"""FB-33 стопка 15 M5e-1b: «Texte» секций главной в окне блока и S14-E3-wie.

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.2 M5eTexte, §2 «M5e-1» (окно и черновик),
§4 «M5e-1», §14.1 A3/A4/A12/A17, §14.2 Y1/Y2/Y5/Y6/Y8. Замки шли первым коммитом (strict xfail), сняты в коммитах реализации.

Окно — второй вход к тем же данным, что Студия: часть `hometext` (вкладка «Texte», форма
`bw-form-hometext`), правка — в черновик (`htx`, `htx_base`), в `site_config` её пишет
«Speichern» тем же писателем `home_texts.put` под блокировкой строки.
"""

from __future__ import annotations

import copy
import re

import pytest
from django.utils import translation

from apps.core import aufbau_draft, block_i18n, block_window, home_texts
from apps.core.tests.form_post import form_post
from apps.core.tests.test_fb27_r2_draft import Browser, _tenant
from apps.core.tests.test_fb33_m3_window_before import _panel
from apps.tenants import siteconfig
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

FORM = "bw-form-hometext"
WOPEN = "openH1"

CFG = {
    "sections": [
        {"key": "hero"},
        {"key": "about", "enabled": True},
        {"key": "cta", "enabled": True},
        {"key": "process", "enabled": True},
        {"key": "team", "enabled": True},
        {"key": "testimonials", "enabled": True},
        {"key": "trust", "enabled": True},
        {"key": "archetypes", "enabled": True},
        {"key": "faq", "enabled": True},
        {"key": "usp_bar", "enabled": True},
        {"key": "stats", "id": "st1", "enabled": True, "data": {"rows": "12 | Jahre"}},
    ],
    "hero_title": "Willkommen",
    "hero_text": "Frisch",
    "about_title": "Über uns",
    "about_text": "Seit 1998.",
    "cta": {"title": "Jetzt", "text": "", "button_label": "Los", "button_url": "/termin/"},
    "process": [{"title": "Wählen", "text": "Online"}, {"title": "Abholen", "text": "Laden"}],
    "team": [
        {"name": "Anna", "role": "Chefin", "photo": "https://cdn.example/anna.jpg"},
        {"name": "Ben", "role": "Bäcker", "photo": "https://cdn.example/ben.jpg"},
    ],
    "testimonials": [{"name": "Eva", "text": "Super!", "stars": "5", "photo": ""}],
    "trust": {"since": "1998", "marks": ["Bio"]},
    "faq": [{"q": "A?", "a": "1"}],
}


def _shop(**extra):
    tenant = _tenant()
    cfg = copy.deepcopy(CFG)
    cfg.update(copy.deepcopy(extra))
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save()
    return tenant


def _saved(b):
    return siteconfig.normalize(Tenant.objects.get(pk=b.tenant.pk).site_config)


def _draft(b):
    return copy.deepcopy(((b.session or {}).get(aufbau_draft.SESSION_KEY) or {}).get("home") or {})


def _get(b, ref, tab="texte", extra=""):
    with translation.override("de"):
        return _panel(b.get(f"?seite=home&block={ref}&tab={tab}&wopen={WOPEN}{extra}"))


def _form(panel, form_id=FORM):
    m = re.search(rf'<form[^>]*id="{form_id}".*?</form>', panel, flags=re.S)
    return m.group(0) if m else ""


def _post(b, ref, **change):
    """Форма «Texte» окна так, как её шлёт браузер, плюс правка."""
    data = _post_data(b, ref, **change)
    with translation.override("de"):
        return b.post(**data)


def _post_data(b, ref, **change):
    panel = _get(b, ref)
    data, _p = form_post(panel, FORM)
    assert data, "формы bw-form-hometext нет"
    data["seite"], data["wopen"] = ["home"], [WOPEN]
    data.setdefault("op", ["update"])  # кнопка «Übernehmen»
    for name, value in change.items():
        data[name] = [value]
    return data


def _save(b, **extra):
    with translation.override("de"):
        return b.post(seite="home", op="save", **extra)


# ───────────── реестры ─────────────


def test_registry_rows():
    assert block_window.PART_TAB["hometext"] == "texte"
    assert block_window.PANEL_KEYS["home_texts"] == "hometext"
    assert "hometext" in block_window.APPLY_FORM_PARTS
    assert ("htx", ("htx", "htx_base")) in aufbau_draft.SIDE_PARTS


def test_wie_applies_listview_and_fields_without_extra_condition():
    """S14-E3-wie (A17): «Wie» применяет вид списка и форму `fields` — без второго условия."""
    assert block_window.APPLY_TAB_PARTS["wie"] == ("listview", "fields")


# ───────────── окно: поля, подписи, a11y ─────────────


@pytest.mark.parametrize("key", ["hero", "about", "cta", "trust"])
def test_window_fields_equal_studio_names(key):
    b = Browser(_shop())
    form = _form(_get(b, key))
    assert form, key
    with translation.override("de"):
        for name, label, _kind, _cap in home_texts.FIELDS[key]:
            assert f'name="f_{name}"' in form, name
            assert f'for="schema-f-{name}"' in form and f">{label}<" in form, name
    assert "Dieselben Felder wie im Studio." in form


@pytest.mark.parametrize(
    "key,legend", [("process", "Schritt"), ("team", "Mitglied"), ("testimonials", "Stimme")]
)
def test_repeated_items_fieldset_legend(key, legend):
    """Y2: пункт — fieldset с legend «Schritt N», видимые метки полей; новый пункт — пустой."""
    b = Browser(_shop())
    form = _form(_get(b, key))
    # стопка 16 T6 (a11y №11, ревью D5): у пункта с переводами — цитата ключа в legend
    assert "<legend" in form and re.search(
        rf"{legend} 1 · <span lang=\"de\">„[^<]+“</span></legend>", form
    )
    count = len(CFG[key]) + 1  # и пустой новый пункт с меткой (ревью E)
    assert f"{legend} {count} – neu – leer lassen, wenn nicht benötigt</legend>" in form
    assert "Text 1" not in form
    for i in range(count):
        for field, _label in home_texts.ITEM_FIELDS[key]:
            assert f'for="schema-f-htx_{key}_{i}_{field}"' in form


def test_caps_server_and_maxlength():
    b = Browser(_shop())
    form = _form(_get(b, "about"))
    assert re.search(r'name="f_about_title"[^>]*maxlength="120"', form)
    assert re.search(r'name="f_about_text"[^>]*maxlength="2000"', form)
    _resp, msgs = _post(b, "about", f_about_title="Ü" * 130)
    assert siteconfig.cap_note() in msgs
    assert _draft(b)["htx"]["about"]["about_title"] == "Ü" * 120


def test_old_long_value_has_no_maxlength():
    b = Browser(_shop(about_title="L" * 300))
    form = _form(_get(b, "about"))
    assert 'name="f_about_title"' in form
    assert not re.search(r'name="f_about_title"[^>]*maxlength', form)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "/\\evil.example"])
def test_cta_url_rejected_and_error_bound_to_field(url):
    """№6/№26, Y1: ссылка не записана; ошибка у поля (id, aria-describedby, aria-invalid),
    набранное видно."""
    b = Browser(_shop())
    _resp, msgs = _post(b, "cta", f_cta_button_url=url)
    assert any("https://" in m for m in msgs)
    assert "cta" not in (_draft(b).get("htx") or {})
    form = _form(_get(b, "cta"))
    field = re.search(r'<input[^>]*name="f_cta_button_url"[^>]*>', form).group(0)
    assert 'aria-invalid="true"' in field and "schema-f-cta_button_url-err" in field
    assert 'id="schema-f-cta_button_url-err"' in form
    # Y1: поле ссылки — не `type="url"`: браузер отверг бы относительную «/termin/», которую
    # писатель принимает; клавиатура ссылки — `inputmode`
    assert 'inputmode="url"' in field and 'autocomplete="off"' in field


def test_default_button_and_no_aria_hidden_on_focusable():
    b = Browser(_shop())
    panel = _get(b, "about")
    form = _form(panel)
    buttons = re.findall(r"<button\b[^>]*>", form)
    assert buttons and all("aria-hidden" not in btn for btn in buttons)
    assert 'value="update"' in buttons[0], "Enter — «Übernehmen», не кнопка вкладки"
    default = re.search(r"<button[^>]*data-window-default[^>]*>", panel)
    assert default and f'form="{FORM}"' in default.group(0)
    assert panel.index("data-window-default") < panel.index('name="zu_tab"')


def test_no_fixed_px_height_textareas():
    b = Browser(_shop())
    for key in ("about", "process", "testimonials"):
        found = re.findall(r"<textarea\b[^>]*>", _form(_get(b, key)))
        assert found, key
        for ta in found:
            assert "height" not in ta and 'rows="' in ta, ta


def test_texte_lang_only_when_differs():
    """Y8: у полей текста на языке окна `lang` нет."""
    b = Browser(_shop())
    form = _form(_get(b, "about"))
    assert form
    for tag in re.findall(r"<(?:input|textarea)\b[^>]*>", form):
        if "f_tr_" in tag or " disabled" in tag:
            continue  # поле перевода — на своём языке (`_bw_tr.html`)
        assert " lang=" not in tag, tag


def test_hero_texte_only_when_title_shown(monkeypatch):
    """Витрина: при показанном баннере библиотеки заголовок главной не показывается
    (`siteui.hero_lead`) — и полей в окне нет (ревью C: тот же предикат, баннер активен)."""
    b = Browser(_shop())
    assert _form(_get(b, "hero"))
    _hero_inactive(monkeypatch, active=True)
    b2 = Browser(_shop(hero_banners={"pick": ["0f8d2a4e-6b1c-4d3e-9a2b-1c2d3e4f5a6b"]}))
    assert not _form(_get(b2, "hero"))


def test_other_rows_have_no_hometext():
    b = Browser(_shop())
    for ref in ("faq", "usp_bar", "st1"):
        assert 'id="bw-form-hometext"' not in _get(b, ref), ref


# ───────────── черновик и «Speichern» ─────────────


def test_edit_goes_to_draft_and_save_writes_through_home_texts(monkeypatch):
    b = Browser(_shop())
    resp, msgs = _post(b, "about", f_about_title="Wer wir sind")
    assert resp.status_code == 302 and msgs == []
    assert _saved(b)["about_title"] == "Über uns", "на сайте ничего"
    assert _draft(b)["htx"]["about"]["about_title"] == "Wer wir sind"
    assert _draft(b)["htx_base"]["about"] == home_texts.fingerprint(_saved(b), "about")
    form = _form(_get(b, "about"))
    assert 'value="Wer wir sind"' in form, "окно показывает черновик"
    seen = []
    real = home_texts.put

    def spy(config, key, get, **kw):
        seen.append(key)
        return real(config, key, get, **kw)

    monkeypatch.setattr(home_texts, "put", spy)
    _resp, msgs = _save(b)
    assert "about" in seen
    assert _saved(b)["about_title"] == "Wer wir sind"
    assert not _draft(b)


def test_same_as_saved_keeps_no_draft():
    b = Browser(_shop())
    _post(b, "about")
    assert "htx" not in _draft(b)


def test_changes_counts_sections():
    b = Browser(_shop())
    _post(b, "about", f_about_title="A")
    _post(b, "cta", f_cta_title="B")
    _post(b, "about", f_about_text="C")
    saved = _saved(b)
    draft = aufbau_draft.get(SimpleReq(b), "home")
    state = aufbau_draft._saved_state(saved, True, "")
    assert aufbau_draft.changes(state, draft) == 2


class SimpleReq:
    def __init__(self, b):
        self.session = b.session


def test_cancel_restores_texts_of_that_window_only():
    b = Browser(_shop())
    _post(b, "cta", f_cta_title="Bleibt")
    _post(b, "about", f_about_title="Weg")
    with translation.override("de"):
        b.post(seite="home", op="revert", ref="about", wopen=WOPEN)
    htx = _draft(b).get("htx") or {}
    assert "about" not in htx and htx["cta"]["cta_title"] == "Bleibt"


def test_open_draft_fingerprint_unchanged():
    """№11: тексты — вне `_saved_state`: отпечаток открытого черновика не меняется."""
    b = Browser(_shop())
    with translation.override("de"):
        b.post(seite="home", op="toggle", ref="trust")
    base = _draft(b)["base"]
    _post(b, "about", f_about_title="Neu")
    assert _draft(b)["base"] == base
    assert "about_title" not in aufbau_draft._saved_state(_saved(b), True, "")


def test_commit_conflict_logged_and_noted(caplog):
    b = Browser(_shop())
    _post(b, "about", f_about_title="Aus dem Fenster")
    cfg = _saved(b)
    cfg["about_title"] = "Aus dem Studio"
    Tenant.objects.filter(pk=b.tenant.pk).update(site_config=cfg)
    with translation.override("de"):
        info = aufbau_draft.info(SimpleReq(b), _saved(b), "home")
    assert info["conflict"] is True
    _resp, msgs = _save(b)
    assert any(m.startswith("Die Texte von") for m in msgs)
    assert _saved(b)["about_title"] == "Aus dem Studio", "без «Trotzdem speichern» не пишет"
    assert _draft(b)["htx"]["about"]["about_title"] == "Aus dem Fenster", "черновик цел"


def test_htx_checked_under_lock_before_write():
    """№9: отказ — до записи остального черновика (блоки страницы не записаны)."""
    b = Browser(_shop())
    with translation.override("de"):
        b.post(seite="home", op="toggle", ref="trust")
    _post(b, "about", f_about_title="Fenster")
    cfg = _saved(b)
    cfg["about_title"] = "Studio"
    Tenant.objects.filter(pk=b.tenant.pk).update(site_config=cfg)
    _save(b)
    trust = next(s for s in _saved(b)["sections"] if s["key"] == "trust")
    assert trust["enabled"] is True


def test_htx_force_symmetric_with_faq():
    b = Browser(_shop())
    _post(b, "about", f_about_title="Fenster")
    cfg = _saved(b)
    cfg["about_title"] = "Studio"
    Tenant.objects.filter(pk=b.tenant.pk).update(site_config=cfg)
    _resp, msgs = _save(b, force="1")
    assert _saved(b)["about_title"] == "Fenster"
    assert any("Gespeichert" in m for m in msgs)


def test_team_photo_kept_by_name_after_reorder():
    b = Browser(_shop())
    _post(
        b,
        "team",
        f_htx_team_0_name="Ben",
        f_htx_team_0_role="Meister",
        f_htx_team_1_name="Anna",
        f_htx_team_1_role="Chefin",
    )
    _save(b)
    team = _saved(b)["team"]
    assert [(m["name"], m["photo"]) for m in team] == [
        ("Ben", "https://cdn.example/ben.jpg"),
        ("Anna", "https://cdn.example/anna.jpg"),
    ]


def test_new_and_removed_items():
    b = Browser(_shop())
    _post(b, "process", f_htx_process_0_title="", f_htx_process_2_title="Genießen")
    _save(b)
    assert [p["title"] for p in _saved(b)["process"]] == ["Abholen", "Genießen"]


def test_testimonials_keep_stars_and_photo():
    b = Browser(_shop())
    _post(b, "testimonials", f_htx_testimonials_0_text="Sehr gut!")
    _save(b)
    t = _saved(b)["testimonials"][0]
    assert (t["name"], t["text"], str(t["stars"])) == ("Eva", "Sehr gut!", "5")


def test_list_overlays_realigned_on_save():
    b = Browser(_shop(i18n={"ru": {"process": [{"title": "Выбрать"}, {"title": "Забрать"}]}}))
    _post(b, "process", f_htx_process_0_title="")
    _save(b)
    assert _saved(b)["i18n"]["ru"]["process"] == [{"title": "Забрать"}]


def test_texte_tab_applies_without_js():
    """№19: на «Texte» прочие вкладки — кнопки формы `bw-form-hometext`; переход применяет."""
    b = Browser(_shop())
    panel = _get(b, "about")
    assert re.search(rf'<button[^>]*form="{FORM}"[^>]*name="zu_tab"[^>]*value="wie"', panel)
    data, _p = form_post(panel, FORM)
    data.update(seite=["home"], wopen=[WOPEN], f_about_title=["Neu"], zu_tab=["wie"])
    tabs = re.search(rf'form="{FORM}" name="bw_tabs" value="([^"]*)"', panel).group(1)
    data["bw_tabs"] = [tabs]
    resp, msgs = b.post(**data)
    assert msgs == [] and "tab=wie" in resp["Location"]
    assert _draft(b)["htx"]["about"]["about_title"] == "Neu"


@pytest.mark.parametrize("ref", ["faq", "cta", "about", "testimonials"])
def test_wie_fields_apply(ref):
    """S14-E3-wie: на «Wie» с формой вида (`fields`) вкладки — кнопки этой формы. Переписка
    охранного замка стопки 14 `test_wie_fields_style_tab_unchanged` — осознанно."""
    b = Browser(_shop())
    panel = _get(b, ref, tab="wie")
    if 'id="bw-form-fields"' not in panel:
        pytest.skip("у строки нет формы вида на «Wie»")
    assert re.search(r'<button[^>]*form="bw-form-fields"[^>]*name="zu_tab"', panel), ref


# ───────────── переводы (A4) ─────────────


def test_hometext_lang_buttons_like_block():
    b = Browser(_shop(i18n={"ru": {"about_title": "О нас", "about_text": "С 1998."}}))
    b.tenant.enabled_locales = ["de", "ru"]
    b.tenant.save()
    form = _form(_get(b, "about"))
    assert 'name="f_sprache"' in form and "data-form-langs" in form
    assert 'name="f_tr_about_title_ru" value="О нас"' in form
    _post(b, "about", f_tr_about_title_ru="Кто мы")
    _save(b)
    assert _saved(b)["i18n"]["ru"]["about_title"] == "Кто мы"
    assert _saved(b)["about_title"] == "Über uns"


def test_german_edit_drops_only_that_field():
    b = Browser(_shop(i18n={"ru": {"about_title": "О нас", "about_text": "С 1998."}}))
    b.tenant.enabled_locales = ["de", "ru"]
    b.tenant.save()
    _post(b, "about", f_about_title="Wer wir sind")
    _save(b)
    ru = _saved(b)["i18n"]["ru"]
    assert "about_title" not in ru and ru["about_text"] == "С 1998."


# ───────────── stats (A12) ─────────────


def _stats_form(b):
    return _form(_get(b, "st1"), "bw-form-fields")


def test_stats_rows_roundtrip():
    b = Browser(_shop())
    form = _stats_form(b)
    m = re.search(r'<textarea[^>]*name="f_rows"[^>]*>([^<]*)</textarea>', form)
    assert m and m.group(1) == "12 | Jahre"
    assert "Wert | Bezeichnung, eine Zeile je Eintrag" in form
    data, _p = form_post(_get(b, "st1"), "bw-form-fields")
    data.update(seite=["home"], wopen=[WOPEN], f_rows=["12 | Jahre\r\n500+ | Kunden"])
    with translation.override("de"):
        b.post(**data)
    _save(b)
    st = next(s for s in _saved(b)["sections"] if s.get("id") == "st1")
    assert st["data"]["rows"] == [
        {"value": "12", "label": "Jahre"},
        {"value": "500+", "label": "Kunden"},
    ]


def test_stats_cap_noted():
    b = Browser(_shop())
    data, _p = form_post(_get(b, "st1"), "bw-form-fields")
    data.update(seite=["home"], wopen=[WOPEN], f_rows=["1234567890123 | Jahre"])
    with translation.override("de"):
        _resp, msgs = b.post(**data)
    assert siteconfig.cap_note() in msgs


def test_stats_translatable():
    assert "stats" in block_i18n.TEXT_FIELDS


# ───────────── ревью круга 1 M5e-1b ─────────────

R1 = "ревью M5e-1b круг 1"
BANNER = "0f8d2a4e-6b1c-4d3e-9a2b-1c2d3e4f5a6b"


def test_invalid_field_autofocus_without_anchor():
    b = Browser(_shop())
    resp, _msgs = _post(b, "cta", f_cta_button_url="javascript:alert(1)")
    assert "#" not in resp["Location"], "якорь отменил бы autofocus"
    form = _form(_get(b, "cta"))
    field = re.search(r'<input[^>]*name="f_cta_button_url"[^>]*>', form).group(0)
    assert " autofocus" in field


def test_refusal_alert_names_field():
    from django.contrib.messages import get_messages

    from apps.core.site_schema_views import site_schema_view

    b = Browser(_shop())
    data = _post_data(b, "cta", f_cta_button_url="javascript:alert(1)")
    with translation.override("de"):
        req = b._request("post", data)
        site_schema_view(req)
        got = [(m.tags, str(m)) for m in get_messages(req)]
    # уровень error — в разметке `role="alert"` (`site_schema.html`)
    assert any(tag == "error" and "Button-Link" in text for tag, text in got), got


def test_htx_malformed_draft_is_ignored_and_counted_consistently():
    b = Browser(_shop())
    _post(b, "about", f_about_title="Gut")
    store = b.session[aufbau_draft.SESSION_KEY]
    store["home"]["htx"].update({"bogus": {"x": "1"}, "cta": "kaputt"})
    store["home"]["htx_base"].update({"bogus": "0", "cta": "0"})
    b.session[aufbau_draft.SESSION_KEY] = store
    saved = _saved(b)
    draft = aufbau_draft.get(SimpleReq(b), "home")
    state = aufbau_draft._saved_state(saved, True, "")
    assert aufbau_draft.changes(state, draft) == 1
    assert home_texts.conflicts(saved, draft) == []
    shown = aufbau_draft.overlay(saved, draft)
    assert shown["about_title"] == "Gut" and shown["cta"] == saved["cta"]
    _resp, msgs = _save(b)
    assert _saved(b)["about_title"] == "Gut"
    assert any("nicht möglich" in m for m in msgs)


def _hero_inactive(monkeypatch, active):
    from apps.core import banners

    slide = {"title": "B", "image": "/x.jpg", "starts": "2000-01-01" if active else "2999-01-01"}
    monkeypatch.setattr(banners, "resolve", lambda pick, *a, **k: [slide])


def test_hero_texte_shown_when_banner_picked_but_inactive(monkeypatch):
    _hero_inactive(monkeypatch, active=False)
    b = Browser(_shop(hero_banners={"pick": [BANNER]}))
    assert _form(_get(b, "hero")), "баннер не показывается — витрина берёт заголовок главной"


def test_hero_texte_hidden_when_banner_shown(monkeypatch):
    _hero_inactive(monkeypatch, active=True)
    b = Browser(_shop(hero_banners={"pick": [BANNER]}))
    assert not _form(_get(b, "hero"))
    draft = {"home": True, "items": [{"key": "hero", "data": {"pick": [BANNER]}}]}
    assert not aufbau_draft.is_htx_edit(draft, "hero", "update", {"htx_present": "1"}, {})
    assert "htx" not in block_i18n.kinds(draft, "hero")


def test_htx_for_removed_row_or_nonhome_not_silent(caplog):
    cfg = siteconfig.normalize(CFG)
    notes = []
    draft = {"home": False, "host": "info", "items": [], "htx": {"about": {"about_title": "X"}}}
    home_texts.commit(cfg, draft, False, notes, home=False)
    assert cfg["about_title"] == "Über uns" and notes


def test_htx_orphan_section_not_committed():
    cfg = siteconfig.normalize(CFG)
    notes = []
    draft = {"home": True, "items": [{"key": "cta"}], "htx": {"about": {"about_title": "X"}}}
    home_texts.commit(cfg, draft, False, notes, home=True)
    assert cfg["about_title"] == "Über uns" and notes


def test_htx_conflict_lists_all_sections():
    b = Browser(_shop())
    _post(b, "about", f_about_title="A")
    _post(b, "cta", f_cta_title="B")
    cfg = _saved(b)
    cfg["about_title"], cfg["cta"]["title"] = "S1", "S2"
    Tenant.objects.filter(pk=b.tenant.pk).update(site_config=cfg)
    _resp, msgs = _save(b)
    assert sum(m.startswith("Die Texte von") for m in msgs) == 2


def test_htx_missing_fp_refused():
    b = Browser(_shop())
    _resp, msgs = _post(b, "about", f_htx_fp="", f_about_title="Ohne")
    assert "htx" not in _draft(b) and any(m.startswith("Die Texte von") for m in msgs)


def test_htx_error_value_capped():
    b = Browser(_shop())
    _post(b, "cta", f_cta_button_url="javascript:" + "x" * 900)
    assert len(b.session[home_texts.ERROR_KEY]["value"]) <= home_texts.URL_MAX


def test_stats_rows_translation_cut_notes():
    b = Browser(_shop())
    data, _p = form_post(_get(b, "st1"), "bw-form-fields")
    data.update(seite=["home"], wopen=[WOPEN], op=["update"])
    data["f_tr_rows_en"] = ["1234567890123 | x"]
    with translation.override("de"):
        _resp, msgs = b.post(**data)
    assert siteconfig.cap_note() in msgs


def test_field_hints_and_link_attrs():
    b = Browser(_shop())
    form = _form(_get(b, "cta"))
    assert form.count("bw-htx-hint") == 2, "id подсказки и только у первого поля"
    field = re.search(r'<input[^>]*name="f_cta_button_url"[^>]*>', form).group(0)
    assert 'autocapitalize="off"' in field and 'spellcheck="false"' in field
    assert "z. B. /kontakt oder https://…" in form
    assert "max-h-[60vh]" in _form(_get(b, "about"))


def test_new_item_slot_marked():
    b = Browser(_shop())
    with translation.override("de"):
        form = _form(_get(b, "process"))
    assert "Schritt 3 – neu – leer lassen, wenn nicht benötigt</legend>" in form


def test_window_op_without_fields_notes():
    b = Browser(_shop())
    with translation.override("de"):
        _resp, msgs = b.post(
            seite="home",
            ref="about",
            op="update",
            panel_present="1",
            f_htx_present="1",
            wopen=WOPEN,
        )
    assert msgs


@pytest.mark.parametrize("ref,ceiling", [("archetypes", 16), ("process", 16)])
def test_home_window_queries(ref, ceiling, django_assert_max_num_queries):
    """№31: потолок запросов окна (замер стенда тестов + запас)."""
    b = Browser(_shop())
    with django_assert_max_num_queries(ceiling):
        panel = _get(b, ref)
    assert _form(panel), "окно с «Texte»"


def test_storefront_after_commit_with_page_cache(settings):
    """№13: «Speichern» сбрасывает кэш витрины; новый текст на de и во втором языке."""
    from django.core.cache import cache
    from django.template.loader import render_to_string
    from django.test import override_settings

    from apps.core import pagecache

    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        PUBLIC_PAGE_CACHE_TTL=300,
    ):
        cache.clear()
        b = Browser(_shop(i18n={"en": {"about_text": "Since 1998."}}))
        _post(b, "about", f_about_title="Wer wir sind", f_tr_about_title_en="Who we are")
        before = pagecache._sf_version(b.tenant.schema_name)
        _save(b)
        assert pagecache._sf_version(b.tenant.schema_name) > before
    cfg = _saved(b)
    de = render_to_string("storefront/sections/_about.html", {"site": cfg, "section_row": {}})
    en = render_to_string(
        "storefront/sections/_about.html",
        {"site": siteconfig.localize(cfg, "en"), "section_row": {}},
    )
    assert "Wer wir sind" in de and "Who we are" in en and "Since 1998." in en
