"""FB-33 M2i-5b C1: ядро переводов полей формы заявки по ключу (`form_spec`, `form_answers`).

Переводы подписей полей (`labels_i18n`), своих вопросов (`label_i18n`, `options_i18n`) и
вариантов «Art der Veranstaltung» (`event_types_i18n`) — по ключу/тексту на основном языке,
не по позиции. Показ: перевод → своя немецкая подпись → подпись по умолчанию; на основном
языке переводы не читаются. Запись — только `form_spec.put`; трёхстороннее слияние — по
(ключ, язык); старый позиционный оверлей — запасное чтение и перенос при записи.
"""

import copy

from django.utils import translation

from apps.core import form_answers, form_spec
from apps.core.tests.test_fb33_m2i5_before import CUSTOM
from apps.tenants import siteconfig


def _site(cfg):
    return siteconfig.normalize(copy.deepcopy(cfg))


def _with(**entry):
    cfg = copy.deepcopy(CUSTOM)
    cfg["form_fields"]["anfrage"].update(entry)
    return cfg


TR = _with(
    labels_i18n={
        "phone": {"ru": "Мобильный", "en": "Mobile", "de": "X", "xx": "Y"},
        "email": {"ru": "Почта", "en": "  "},
        "nope": {"ru": "мусор"},
        "event_date": {"ru": "Wann?"},  # равен своей немецкой — не хранится
    },
    event_types_i18n={"Hochzeit": {"ru": "Свадьба"}, "Weg": {"ru": "нет такого"}},
)
TR["form_fields"]["anfrage"]["custom"][1].update(
    label_i18n={"ru": "Зал", "en": "Raum"},
    options_i18n={"Garten": {"ru": "Сад"}, "Keller": {"ru": "нет"}},
)
TR["form_fields"]["anfrage"]["custom"][0].update(options_i18n={"x": {"ru": "y"}})


def test_normalize_keeps_only_known_keys_languages_and_real_translations():
    entry = _site(TR)["form_fields"]["anfrage"]
    assert entry["labels_i18n"] == {
        "email": {"ru": "Почта"},
        "phone": {"en": "Mobile", "ru": "Мобильный"},
    }
    assert entry["event_types_i18n"] == {"Hochzeit": {"ru": "Свадьба"}}
    q1, q2 = entry["custom"][0], entry["custom"][1]
    assert "options_i18n" not in q1 and "label_i18n" not in q1  # не выбор — вариантов нет
    assert q2["label_i18n"] == {"ru": "Зал"}  # en равен основному
    assert q2["options_i18n"] == {"Garten": {"ru": "Сад"}}


def test_no_translations_is_byte_for_byte_old_config():
    assert _site(CUSTOM) == siteconfig.normalize(copy.deepcopy(CUSTOM))
    assert "labels_i18n" not in _site(CUSTOM)["form_fields"]["anfrage"]


def test_duplicate_options_collapse_keeping_order():
    raw = {"event_types": ["Hochzeit", " Hochzeit ", "Feier", "Hochzeit"]}
    assert siteconfig.normalize_anfrage(raw)["event_types"] == ["Hochzeit", "Feier"]
    qs, _n = form_answers.normalize_questions(
        [{"id": "q1", "type": "choice", "label": "A", "options": ["b", "a", " b", "a"]}]
    )
    assert qs[0]["options"] == ["b", "a"]


def test_view_on_main_language_ignores_translations():
    with translation.override("de"):
        plain = form_spec.view(_site(CUSTOM), "anfrage")
        shown = form_spec.view(_site(TR), "anfrage")
    assert {k: v for k, v in plain.items() if k != "custom"} == {
        k: v for k, v in shown.items() if k != "custom"
    }
    assert [q["label"] for q in shown["custom"]] == ["Budget", "Raum", "Vegan?"]
    assert shown["custom"][1]["choices"] == [("Saal", "Saal", ""), ("Garten", "Garten", "")]


def test_view_translates_label_then_own_label_then_default():
    with translation.override("ru"):
        shown = form_spec.view(_site(TR), "anfrage")
    assert shown["phone"].label == "Мобильный"  # перевод
    assert shown["email"].label == "Почта"  # перевод без своей немецкой подписи
    assert shown["event_date"].label == "Wann?"  # своя немецкая без перевода — немецкая
    q2 = shown["custom"][1]
    assert q2["label"] == "Зал"
    assert q2["choices"] == [("Saal", "Saal", "de"), ("Garten", "Сад", "")]  # value — основной язык
    assert q2["options"] == ["Saal", "Garten"]
    assert "options_i18n" not in q2 and "label_i18n" not in q2


def test_event_type_choices_value_always_main_language():
    site = _site(TR)
    assert form_spec.event_type_choices(site, "ru") == [
        ("Hochzeit", "Свадьба", ""),
        ("Firmenfeier", "Firmenfeier", "de"),  # непереведённый — lang основного
    ]
    assert form_spec.event_type_choices(site, "de") == [
        ("Hochzeit", "Hochzeit", ""),
        ("Firmenfeier", "Firmenfeier", ""),
    ]


def test_positional_overlay_is_fallback_keyed_wins():
    cfg = copy.deepcopy(TR)
    cfg["i18n"] = {"ru": {"anfrage": {"event_types": ["Старая свадьба", "Корпоратив"]}}}
    assert form_spec.event_type_choices(_site(cfg), "ru") == [
        ("Hochzeit", "Свадьба", ""),
        ("Firmenfeier", "Корпоратив", ""),
    ]


def test_edit_state_shows_and_put_moves_positional_translations():
    cfg = _site(dict(CUSTOM, i18n={"ru": {"anfrage": {"event_types": ["Свадьба", "Корп"]}}}))
    state = form_spec.edit_state(cfg)
    assert state["event_types_i18n"] == {
        "Hochzeit": {"ru": "Свадьба"},
        "Firmenfeier": {"ru": "Корп"},
    }
    same = copy.deepcopy(cfg)
    form_spec.put(same, "anfrage", state)
    assert same == cfg  # без правки — ни байта (нормализация уже впитала старый оверлей)
    assert "i18n" not in cfg  # ревью: впитан нормализацией (по НЕдедуплицированному списку)
    state["event_types"] = ["Firmenfeier", "Hochzeit"]  # переставили
    form_spec.put(cfg, "anfrage", state)
    out = siteconfig.normalize(cfg)
    assert "i18n" not in out
    assert out["form_fields"]["anfrage"]["event_types_i18n"] == {
        "Firmenfeier": {"ru": "Корп"},
        "Hochzeit": {"ru": "Свадьба"},
    }
    assert form_spec.event_type_choices(out, "ru") == [
        ("Firmenfeier", "Корп", ""),
        ("Hochzeit", "Свадьба", ""),
    ]


def test_put_writes_translations_and_equal_state_is_noop():
    cfg = _site(CUSTOM)
    state = form_spec.edit_state(cfg)
    state["labels_i18n"] = {"phone": {"ru": "Мобильный"}}
    state["custom"][1]["options_i18n"] = {"Saal": {"ru": "Зал"}}
    form_spec.put(cfg, "anfrage", state)
    entry = siteconfig.normalize(cfg)["form_fields"]["anfrage"]
    assert entry["labels_i18n"] == {"phone": {"ru": "Мобильный"}}
    assert entry["custom"][1]["options_i18n"] == {"Saal": {"ru": "Зал"}}
    again = copy.deepcopy(cfg)
    form_spec.put(again, "anfrage", form_spec.edit_state(again))
    assert again == cfg


def test_merge_by_key_and_language():
    base = form_spec.edit_state(_site(TR))
    mine = copy.deepcopy(base)
    mine["labels_i18n"]["phone"]["en"] = "Cell"  # владелец во вкладке
    theirs_cfg = copy.deepcopy(TR)
    theirs_cfg["form_fields"]["anfrage"]["labels_i18n"]["phone"]["ru"] = "Сотовый"  # другой путь
    theirs = form_spec.edit_state(_site(theirs_cfg))
    out = form_spec.merge(base, mine, theirs)
    assert out["labels_i18n"]["phone"] == {"en": "Cell", "ru": "Сотовый"}


def test_merge_reports_translation_of_renamed_option():
    base = form_spec.edit_state(_site(TR))
    mine = copy.deepcopy(base)
    mine["event_types_i18n"]["Firmenfeier"] = {"ru": "Корпоратив"}
    theirs_cfg = copy.deepcopy(TR)
    theirs_cfg["anfrage"]["event_types"] = ["Hochzeit", "Betriebsfeier"]  # старая панель
    notes: list = []
    out = form_spec.merge(base, mine, form_spec.edit_state(_site(theirs_cfg)), notes=notes)
    assert "Firmenfeier" not in out["event_types_i18n"]
    assert out["event_types_i18n"] == {"Hochzeit": {"ru": "Свадьба"}}
    assert any("„Firmenfeier“" in n for n in notes)


def test_absorb_legacy_moves_and_cleans():
    cfg = copy.deepcopy(CUSTOM)
    cfg["i18n"] = {
        "ru": {"anfrage": {"event_types": ["Свадьба", "Корп"]}, "hero_title": "Привет"},
        "en": {"anfrage": {"event_types": ["Wedding"]}},
    }
    cfg["form_fields"]["anfrage"]["event_types_i18n"] = {"Hochzeit": {"ru": "Венчание"}}
    assert form_spec.absorb_legacy_event_i18n(cfg) is True
    assert cfg["i18n"] == {"ru": {"hero_title": "Привет"}}
    assert cfg["form_fields"]["anfrage"]["event_types_i18n"] == {
        "Hochzeit": {"en": "Wedding", "ru": "Венчание"},  # ключевой перевод главнее
        "Firmenfeier": {"ru": "Корп"},
    }
    assert form_spec.absorb_legacy_event_i18n(cfg) is False  # повтор — ничего


def test_snapshot_stays_on_main_language():
    site = _site(TR)
    with translation.override("ru"):
        qs = form_spec.questions(site, "anfrage")
        snap = form_answers.snapshot(qs, form_answers.collect(qs, {"q2": "Garten"}))
    assert snap["q2"]["label"] == "Raum" and snap["q2"]["value"] == "Garten"


def test_translated_label_is_not_a_valid_answer():
    qs = form_spec.questions(_site(TR), "anfrage")
    assert form_answers.collect(qs, {"q2": "Сад"}) == {}  # value варианта — основной язык
    assert form_answers.collect(qs, {"q2": "Garten"}) == {"q2": "Garten"}


def test_positional_transfer_uses_undeduplicated_list():
    """Ревью M2i-5b п.2: дубль варианта занимал свою позицию в старом оверлее — сопоставление
    по НЕдедуплицированному списку (C получает свой перевод, а не перевод дубля A)."""
    cfg = {
        "anfrage": {"fields": ["event_type"], "event_types": ["A", "B", "A", "C"]},
        "i18n": {"ru": {"anfrage": {"event_types": ["а", "б", "а2", "ц"]}}},
    }
    assert form_spec.legacy_event_i18n(cfg) == {
        "A": {"ru": "а"},
        "B": {"ru": "б"},
        "C": {"ru": "ц"},
    }
    assert form_spec.legacy_mismatch(cfg)  # дубли — сомнительный перенос
    assert form_spec.event_type_choices(siteconfig.normalize(cfg), "ru") == [
        ("A", "а", ""),
        ("B", "б", ""),
        ("C", "ц", ""),
    ]
    short = {
        "anfrage": {"event_types": ["A", "B"]},
        "i18n": {"ru": {"anfrage": {"event_types": ["а"]}}},
    }
    assert form_spec.legacy_mismatch(short)
    ok = {"anfrage": {"event_types": ["A"]}, "i18n": {"ru": {"anfrage": {"event_types": ["а"]}}}}
    assert not form_spec.legacy_mismatch(ok)


def test_hash_collision_skips_second_option(monkeypatch):
    """Ревью п.5: два варианта с одним h — перевод второго не рисуется и не пишется."""
    monkeypatch.setattr(form_spec, "text_hash", lambda text: "deadbeef")
    assert form_spec.hashed(["Saal", "Garten"]) == [("Saal", "deadbeef")]
    state = form_spec.edit_state(_site(CUSTOM))
    out, _notes = form_spec.parse_post({"q_q2_label": "Raum", "q_q2_odeadbeef_ru": "Зал"}, state)
    assert out["custom"][1]["options_i18n"] == {"Saal": {"ru": "Зал"}}  # не «Garten»


def test_preset_keeps_label_translations_and_notes_dropped_variants():
    cfg = copy.deepcopy(TR)
    state = form_spec.edit_state(_site(cfg))
    preset = {"fields": ["event_type"], "event_types": ["Geburtstag"]}
    out, notes = form_spec.parse_post({"do": "preset"}, state, preset=preset)
    assert out["labels_i18n"]["phone"] == {"en": "Mobile", "ru": "Мобильный"}
    assert out["event_types_i18n"] == {}
    assert any("„Hochzeit“" in n for n in notes)


def test_merge_question_option_notes_only_for_kept_questions():
    """Ревью п.6: сообщение о выпавших переводах вариантов своих вопросов — только у вопросов,
    что остались (удалённый вопрос — не повод); свои вопросы сливаются списком целиком."""
    base = form_spec.edit_state(_site(TR))
    mine = copy.deepcopy(base)
    mine["custom"].pop(1)  # вопрос с переводами вариантов удалён во вкладке
    notes: list = []
    out = form_spec.merge(base, mine, form_spec.edit_state(_site(TR)), notes=notes)
    assert [q["id"] for q in out["custom"]] == ["q1", "q4"] and notes == []
