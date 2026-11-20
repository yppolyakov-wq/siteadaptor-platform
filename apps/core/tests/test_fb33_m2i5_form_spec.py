"""FB-33 M2i-5 C1: ядро вкладки «Felder» — `form_spec.edit_state/canonical/parse_post/put/panel`.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i-5» (security-reviewer M1, M4–M6, M8).
"""

import copy

import pytest

from apps.core import form_answers, form_spec
from apps.core.tests.test_fb33_m2i5_before import CONFIGS, CUSTOM
from apps.tenants import siteconfig


def _site(cfg):
    return siteconfig.normalize(copy.deepcopy(cfg))


ROUND = {
    **CONFIGS,
    # событийное поле в прежнем `anfrage.fields`, но явно выключено режимом
    "legacy-off": {
        "anfrage": {"fields": ["date", "guests"]},
        "form_fields": {"anfrage": {"mode": {"guest_count": "off"}}},
    },
}


@pytest.mark.parametrize("name", sorted(ROUND))
def test_saved_state_round_trips_byte_for_byte(name):
    site = _site(ROUND[name])
    state = form_spec.edit_state(site)
    assert form_spec.canonical(state) == state
    out = form_spec.put(copy.deepcopy(site), "anfrage", copy.deepcopy(state))
    assert siteconfig.normalize(out) == site


def _parse(cfg, post, preset=None):
    site = _site(cfg)
    return form_spec.parse_post(post, form_spec.edit_state(site), preset=preset)


def test_mode_and_label_change():
    state, notes = _parse({}, {"mode_description": "req", "label_description": "  Was genau? "})
    assert state["mode"]["description"] == "req"
    assert state["labels"]["description"] == "Was genau?"
    assert notes == []


def test_pinned_fields_cannot_be_switched_off():
    state, _notes = _parse({}, {"mode_title": "off", "mode_name": "off"})
    assert "title" not in state["mode"] and "name" not in state["mode"]
    site = form_spec.put(_site({}), "anfrage", state)
    assert form_spec.mode_of(site, "anfrage", "title") == "req"
    assert form_spec.mode_of(site, "anfrage", "name") == "req"


def test_contact_cannot_be_removed_completely():
    state, notes = _parse({}, {"mode_email": "off", "mode_phone": "off"})
    assert state["mode"]["email"] == "off" and state["mode"]["phone"] == "opt"
    assert any("Telefon" in n for n in notes)


@pytest.mark.parametrize(
    "post",
    [
        {"q_q1_type": "__proto__", "q_q1_label": "Budget"},
        {"mode_phone": "admin"},
        {"do": "del:q0"},
        {"do": "del:q10000"},
        {"do": "del:../"},
        {"do": "up:n999999"},
        {"do": "del:q3"},  # не вопрос этого черновика
        {"q_q3_label": "fremd", "q_q3_type": "text"},
        {"__proto__": "x", "constructor": "y"},
    ],
)
def test_garbage_is_dropped(post):
    before = form_spec.edit_state(_site(CUSTOM))
    state, _notes = _parse(CUSTOM, post)
    assert state == before


def test_limits_are_cut():
    long = "x" * 500
    state, _n = _parse(
        CUSTOM,
        {
            "label_phone": long,
            "q_q2_label": "Raum",
            "q_q2_type": "choice",
            "q_q2_options": "\n".join(f"O{i}" for i in range(60)),
            "event_types": "\n".join(f"T{i}" for i in range(40)),
        },
    )
    assert len(state["labels"]["phone"]) == form_spec.LABEL_MAX
    q2 = next(q for q in state["custom"] if q["id"] == "q2")
    assert len(q2["options"]) == form_answers.MAX_OPTIONS
    assert len(state["event_types"]) == 12


def test_add_question_gets_temporary_id_and_cap():
    state, notes = _parse(CUSTOM, {"do": "add", "new_label": "Anlass", "new_type": "textarea"})
    assert notes == []
    assert state["custom"][-1] == {"id": "n1", "type": "textarea", "label": "Anlass"}
    full = {**CUSTOM["form_fields"]["anfrage"]}
    full["custom"] = [{"id": f"q{i}", "type": "text", "label": f"F{i}"} for i in range(1, 11)]
    cfg = {"form_fields": {"anfrage": full}}
    state, notes = _parse(cfg, {"do": "add", "new_label": "Elf"})
    assert len(state["custom"]) == 10 and any("10" in n for n in notes)


def test_add_needs_text_and_choice_needs_options():
    _s, notes = _parse({}, {"do": "add", "new_label": " "})
    assert notes and not _s["custom"]
    _s, notes = _parse({}, {"do": "add", "new_label": "Raum", "new_type": "choice"})
    assert notes and not _s["custom"]
    state, notes = _parse(
        {}, {"do": "add", "new_label": "Raum", "new_type": "choice", "new_options": "A\nB\nA"}
    )
    assert state["custom"] == [
        {"id": "n1", "type": "choice", "label": "Raum", "options": ["A", "B"]}
    ]


def test_type_change_to_choice_without_options_is_refused():
    state, notes = _parse(CUSTOM, {"q_q1_label": "Budget", "q_q1_type": "choice"})
    assert next(q for q in state["custom"] if q["id"] == "q1")["type"] == "text"
    assert notes


def test_up_down_delete():
    state, _n = _parse(CUSTOM, {"do": "up:q2"})
    assert [q["id"] for q in state["custom"]] == ["q2", "q1", "q4"]
    state, _n = _parse(CUSTOM, {"do": "down:q4"})
    assert [q["id"] for q in state["custom"]] == ["q1", "q2", "q4"]
    state, _n = _parse(CUSTOM, {"do": "del:q2"})
    assert [q["id"] for q in state["custom"]] == ["q1", "q4"]


def test_put_assigns_ids_from_saved_counter_never_reusing():
    site = _site(CUSTOM)  # next_id 5, q4 — последний
    state, _n = form_spec.parse_post({"do": "del:q4"}, form_spec.edit_state(site))
    state, _n = form_spec.parse_post({"do": "add", "new_label": "Neu"}, state)
    out = form_spec.put(copy.deepcopy(site), "anfrage", state)
    ids = [q["id"] for q in out["form_fields"]["anfrage"]["custom"]]
    assert ids == ["q1", "q2", "q6"]
    assert out["form_fields"]["anfrage"]["next_id"] == 6


def test_put_reassigns_unknown_real_ids():
    """id `q<n>`, которого нет среди сохранённых (подделка, вопрос удалён в другом месте), —
    новый номер, а не чужой/удалённый."""
    site = _site(CUSTOM)
    state = form_spec.edit_state(site)
    state["custom"].append({"id": "q3", "type": "text", "label": "Alt"})
    out = form_spec.put(copy.deepcopy(site), "anfrage", state)
    assert [q["id"] for q in out["form_fields"]["anfrage"]["custom"]][-1] == "q6"


def test_id_max_is_a_clear_refusal():
    cfg = {"form_fields": {"anfrage": {"next_id": form_answers.ID_MAX}}}
    with pytest.raises(form_spec.FormSpecError):
        _parse(cfg, {"do": "add", "new_label": "Zu viel"})
    site = _site(cfg)
    state = form_spec.edit_state(site)
    state["custom"] = [{"id": "n1", "type": "text", "label": "X"}]
    with pytest.raises(form_spec.FormSpecError):
        form_spec.put(copy.deepcopy(site), "anfrage", state)


def test_event_fields_follow_legacy_list():
    state, _n = _parse({}, {"mode_guest_count": "req", "mode_event_type": "opt"})
    state, _n = form_spec.parse_post({"event_types": "Hochzeit\nGeburtstag"}, state)
    out = siteconfig.normalize(form_spec.put(_site({}), "anfrage", state))
    assert out["anfrage"] == {
        "fields": ["guests", "event_type"],
        "event_types": ["Hochzeit", "Geburtstag"],
    }
    assert out["form_fields"]["anfrage"]["mode"] == {"guest_count": "req"}
    assert form_spec.view(out, "anfrage")["event_type"].on


def test_event_type_without_options_warns():
    _s, notes = _parse({}, {"mode_event_type": "opt"})
    assert any("Auswahlliste" in n for n in notes)
    assert form_spec.panel(_site({}), state=_s)["event_hint"]


def test_preset_goes_to_state_only():
    preset = {"fields": ["date", "guests", "event_type"], "event_types": ["Hochzeit"]}
    state, notes = _parse(
        {"form_fields": {"anfrage": {"mode": {"phone": "req"}}}}, {"do": "preset"}, preset
    )
    assert state["mode"]["event_date"] == "opt" and state["mode"]["event_type"] == "opt"
    assert state["event_types"] == ["Hochzeit"] and notes
    _s, notes = _parse({}, {"do": "preset"}, None)
    assert notes and _s == form_spec.edit_state(_site({}))


def test_panel_model():
    model = form_spec.panel(_site(CUSTOM))
    keys = [f["key"] for f in model["fields"]]
    assert keys[0] == "title" and model["fields"][0]["pinned"]
    assert [q["id"] for q in model["custom"]] == ["q1", "q2", "q4"]
    assert model["custom"][0]["first"] and model["custom"][-1]["last"]
    assert model["can_add"] and model["event_types_text"] == "Hochzeit\nFirmenfeier"


def test_temp_ids_only_in_draft_normalization():
    raw = [{"id": "n1", "type": "text", "label": "A"}, {"id": "q2", "type": "text", "label": "B"}]
    assert [q["id"] for q in form_answers.normalize_questions(raw)[0]] == ["q2"]
    got, counter = form_answers.normalize_questions(raw, temp=True)
    assert [q["id"] for q in got] == ["n1", "q2"] and counter == 2


# --- ревью M2i-5 (silent-failure-hunter) ---------------------------------------------------


def test_typed_new_question_is_added_on_apply_and_told_otherwise():
    state, notes = _parse({}, {"new_label": "Allergien", "commit_new": "1"})
    assert [q["label"] for q in state["custom"]] == ["Allergien"] and notes == []
    state, notes = _parse({}, {"new_label": "Allergien"})  # правка поля (без «Übernehmen»)
    assert state["custom"] == [] and any("+ Frage" in n for n in notes)


def test_cuts_are_told():
    _s, notes = _parse({}, {"label_phone": "x" * 200})
    assert any("gekürzt" in n for n in notes)
    _s, notes = _parse({}, {"event_types": "\n".join(f"T{i}" for i in range(13))})
    assert len(_s["event_types"]) == 12 and any("gekürzt" in n for n in notes)
    _s, notes = _parse({}, {"event_types": "y" * 61})
    assert any("gekürzt" in n for n in notes)
    _s, notes = _parse(
        CUSTOM,
        {
            "q_q2_label": "Raum",
            "q_q2_type": "choice",
            "q_q2_options": "\n".join(f"O{i}" for i in range(21)),
        },
    )
    assert any("gekürzt" in n for n in notes)
    _s, notes = _parse(CUSTOM, {"label_phone": "Handy"})
    assert notes == []


def test_choice_to_text_tells_options_are_dropped():
    state, notes = _parse(CUSTOM, {"q_q2_label": "Raum", "q_q2_type": "text"})
    q2 = next(q for q in state["custom"] if q["id"] == "q2")
    assert q2["type"] == "text" and "options" not in q2 and notes


def test_garbage_type_and_mode_are_logged_without_values(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="apps.core.form_spec")
    _parse(CUSTOM, {"q_q1_label": "Budget", "q_q1_type": "GEHEIM", "mode_phone": "GEHEIM2"})
    assert "ignored type for question q1" in caplog.text
    assert "ignored mode for field phone" in caplog.text
    assert "GEHEIM" not in caplog.text


def test_merge_keeps_untouched_from_saved():
    base = form_spec.edit_state(_site(CUSTOM))
    mine = copy.deepcopy(base)
    mine["mode"]["description"] = "req"
    theirs = copy.deepcopy(base)
    theirs["event_types"] = ["Neu"]
    theirs["mode"]["guest_count"] = "off"
    got = form_spec.merge(base, mine, theirs)
    assert got["mode"]["description"] == "req" and got["mode"]["guest_count"] == "off"
    assert got["event_types"] == ["Neu"]
    mine["event_types"] = ["Meins"]
    assert form_spec.merge(base, mine, theirs)["event_types"] == ["Meins"]


def test_event_types_without_fields_are_kept_but_form_unchanged():
    out = siteconfig.normalize_anfrage({"fields": [], "event_types": ["Hochzeit"]})
    assert out == {"event_types": ["Hochzeit"]}
    site = _site({"anfrage": out})
    view = form_spec.view(site, "anfrage")
    assert not view["any_event"] and not view["event_type"].on
