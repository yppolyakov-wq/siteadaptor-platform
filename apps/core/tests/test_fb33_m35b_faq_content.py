"""FB-33 M3-5b: один писатель вопросов FAQ (`apps/core/faq_content.py`).

Замки L3: перестановка, удаление и вставка не сдвигают переводы; правка немецкого текста
снимает перевод только этого поля; старые данные (оверлей короче базы, частичный перевод,
дыры, два одинаковых вопроса); устаревший источник — по тексту и в лог; лимиты на вводе.
"""

import copy
import logging

import pytest

from apps.core import faq_content as fc

BASE = [
    {"q": "Wann offen?", "a": "Mo–Fr."},
    {"q": "Vorbestellen?", "a": "Ja."},
    {"q": "Liefern?", "a": "5 km."},
]
RU = [
    {"q": "Когда?", "a": "Пн–Пт."},
    {"q": "Заранее?", "a": "Да."},
    {"q": "Доставка?", "a": "5 км."},
]
EN = [{"q": "When?", "a": "Mon–Fri."}, {}, {"q": "Delivery?"}]


def cfg():
    return {
        "faq": copy.deepcopy(BASE),
        "i18n": {"ru": {"faq": copy.deepcopy(RU)}, "en": {"faq": copy.deepcopy(EN)}},
    }


def put(config, order, edit=None):
    items = [copy.deepcopy(BASE[i]) if i is not None else {"q": "Neu?", "a": "N"} for i in order]
    for j, (field, value) in (edit or {}).items():
        items[j][field] = value
    fc.put(config, items, list(order), fc.fingerprint(BASE))
    return config


def test_reorder_moves_translations_with_their_question():
    c = put(cfg(), [2, 0, 1])
    assert [f["q"] for f in c["faq"]] == ["Liefern?", "Wann offen?", "Vorbestellen?"]
    assert c["i18n"]["ru"]["faq"] == [RU[2], RU[0], RU[1]]
    assert c["i18n"]["en"]["faq"] == [{"q": "Delivery?"}, EN[0]]  # дыра в хвосте не хранится


def test_remove_and_insert_keep_the_neighbours():
    c = put(cfg(), [0, None, 2])
    assert c["i18n"]["ru"]["faq"] == [RU[0], {}, RU[2]]
    c = put(cfg(), [1, 2])
    assert c["i18n"]["ru"]["faq"] == [RU[1], RU[2]]


def test_german_edit_drops_only_that_field():
    c = put(cfg(), [0, 1, 2], edit={1: ("a", "Ja, bis 18 Uhr.")})
    assert c["i18n"]["ru"]["faq"] == [RU[0], {"q": "Заранее?"}, RU[2]]
    c = put(cfg(), [0, 1, 2], edit={0: ("q", "Wann geöffnet?")})
    assert c["i18n"]["ru"]["faq"][0] == {"a": "Пн–Пт."}
    assert c["i18n"]["ru"]["faq"][1:] == RU[1:]


def test_overlay_shorter_than_base_and_partial_entries():
    c = {"faq": copy.deepcopy(BASE), "i18n": {"ru": {"faq": [{"q": "Когда?"}]}}}
    fc.put(c, [BASE[2], BASE[0]], [2, 0], fc.fingerprint(BASE))
    assert c["i18n"]["ru"]["faq"] == [{}, {"q": "Когда?"}]


def test_garbage_in_overlay_is_not_carried():
    c = {"faq": copy.deepcopy(BASE), "i18n": {"ru": {"faq": ["x", None, {"q": 5, "a": "Да."}]}}}
    fc.put(c, BASE, [0, 1, 2], fc.fingerprint(BASE))
    assert c["i18n"]["ru"]["faq"] == [{}, {}, {"a": "Да."}]


def test_all_translations_gone_drops_the_key():
    c = put(cfg(), [None])
    assert "faq" not in c["i18n"]["ru"] and "faq" not in c["i18n"]["en"]


def test_two_equal_questions_do_not_share_a_translation():
    """Сегодняшний `index_of.setdefault` дал бы обоим первый перевод."""
    base = [{"q": "Preis?", "a": "1"}, {"q": "Preis?", "a": "2"}]
    c = {
        "faq": copy.deepcopy(base),
        "i18n": {"ru": {"faq": [{"q": "Цена?", "a": "1"}, {"q": "Цена 2?", "a": "2"}]}},
    }
    fc.put(c, [base[1], base[0]], [1, 0], fc.fingerprint(base))
    assert c["i18n"]["ru"]["faq"] == [{"q": "Цена 2?", "a": "2"}, {"q": "Цена?", "a": "1"}]
    c = {
        "faq": copy.deepcopy(base),
        "i18n": {"ru": {"faq": [{"q": "Цена?", "a": "1"}, {"q": "Цена 2?", "a": "2"}]}},
    }
    fc.put(c, [base[1], base[0]], None)  # без источника — по тексту, каждый не больше раза
    assert c["i18n"]["ru"]["faq"][0] != c["i18n"]["ru"]["faq"][1]


def test_stale_base_matches_by_text_and_warns(caplog):
    c = cfg()
    with caplog.at_level(logging.WARNING, logger="apps.core.faq_content"):
        # индексы от другого списка: «0» больше не «Wann offen?» — сопоставляем по тексту
        fc.put(c, [BASE[2], BASE[0]], [0, 1], base_fp="0000")
    assert c["i18n"]["ru"]["faq"] == [RU[2], RU[0]]
    assert "matched by text" in caplog.text


def test_duplicate_src_gives_the_translation_once():
    c = cfg()
    fc.put(c, [BASE[0], BASE[0]], [0, 0], fc.fingerprint(BASE))
    assert c["i18n"]["ru"]["faq"] == [RU[0]]


def test_storefront_after_reorder_shows_right_pairs():
    from apps.tenants import siteconfig

    c = put(siteconfig.normalize(cfg()), [2, 0, 1])
    site = siteconfig.localize(siteconfig.normalize(c), "ru")
    assert [(f["q"], f["a"]) for f in site["faq"]] == [
        ("Доставка?", "5 км."),
        ("Когда?", "Пн–Пт."),
        ("Заранее?", "Да."),
    ]


def test_set_text_base_drops_only_that_field_in_every_language():
    c = cfg()
    assert fc.set_text(c, 2, "q", "Liefern Sie?")
    assert c["i18n"]["ru"]["faq"][2] == {"a": "5 км."}
    assert "faq" in c["i18n"]["en"] and c["i18n"]["en"]["faq"][:1] == [EN[0]]
    assert c["i18n"]["ru"]["faq"][:2] == RU[:2]


def test_set_text_translation_and_bad_input():
    c = cfg()
    assert fc.set_text(c, 1, "a", "Да, до 18.", locale="ru")
    assert c["i18n"]["ru"]["faq"][1] == {"q": "Заранее?", "a": "Да, до 18."}
    assert c["faq"] == BASE
    assert not fc.set_text(c, 3, "q", "x")
    assert not fc.set_text(c, 0, "q", "  ")
    assert not fc.set_text(c, 0, "z", "x")


def test_input_limits_cut_with_a_note_and_saved_is_not_cut():
    notes = []
    rows = [{"q": "x" * 300, "a": "y" * 3000, "src": 0}] + [
        {"q": f"Q{i}", "src": None} for i in range(20)
    ]
    items, src = fc.clean_input(rows, notes)
    assert len(items) == fc.MAX_ITEMS and len(items[0]["q"]) == fc.MAX_Q
    assert len(items[0]["a"]) == fc.MAX_A and len(notes) == 2
    long = {"faq": [{"q": "x" * 300, "a": ""}]}
    assert fc.base_items(long)[0]["q"] == "x" * 300  # сохранённое не режется


def test_from_form_reads_studio_pairs_with_their_index():
    post = {
        "faq_present": "1",
        "faq_q_0": "A?",
        "faq_a_0": "a",
        "faq_q_1": "",
        "faq_q_2": "C?",
        "faq_q_3": "Neu",
    }
    items, src = fc.from_form(post.get)
    assert [i["q"] for i in items] == ["A?", "C?", "Neu"] and src == [0, 2, 3]
    assert fc.from_form({}.get) is None


def test_apply_ops_texts_then_button():
    items, src = [copy.deepcopy(b) for b in BASE], [0, 1, 2]
    post = {"faq_0_q": "Wann?", "faq_move": "0:down", "faq_new_q": "Neu?", "faq_new_a": "N"}
    new, new_src = fc.apply_ops(items, src, post)
    assert [i["q"] for i in new] == ["Vorbestellen?", "Wann?", "Liefern?", "Neu?"]
    assert new_src == [1, 0, 2, None]
    new, new_src = fc.apply_ops(items, src, {"faq_remove": "1"})
    assert new_src == [0, 2]
    new, new_src = fc.apply_ops(items, src, {"faq_remove": "9", "faq_move": "x:up"})
    assert new_src == [0, 1, 2]


@pytest.mark.parametrize("value", ["<script>alert(1)</script>", "\x00", "a" * 5000])
def test_apply_ops_is_plain_text(value):
    new, _src = fc.apply_ops([], [], {"faq_new_q": value, "faq_new_a": value})
    assert all(isinstance(i["q"], str) for i in new)
    assert len(new[0]["a"]) <= fc.MAX_A if new else True
