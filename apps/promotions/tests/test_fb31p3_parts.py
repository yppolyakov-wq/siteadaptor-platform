"""FB-31 P3 R1: оси блоков трёх страниц акций (ядро `apps/core/page_parts.py`)."""

import pytest

from apps.core import compositions
from apps.core import page_parts as pp
from apps.promotions import promo_parts as P

_CODES = {
    P.PROMOS: "promos",
    P.PROMO_GROUP: "promo_group",
    P.PROMO_DETAIL: "promo",
}


@pytest.mark.parametrize("surface", list(_CODES), ids=lambda s: s.name)
def test_every_registry_code_is_known_and_reversible(surface):
    codes = [c for c, _l, _h in compositions.styles_for(_CODES[surface])]
    assert sorted(codes) == sorted(surface.codes), "карта кодов = реестр шаблонов"
    for code in codes:
        parts = pp.from_code(surface, code)
        assert pp.legacy_code(surface, parts) == code
        rows = pp.rows_for(surface, parts)
        assert pp.from_rows(surface, rows) == parts, code
        assert pp.effective_rows(surface, rows, code="") == parts, code


def test_junk_code_and_junk_rows_fall_back_to_standard():
    s = P.PROMOS
    assert pp.from_code(s, "quatsch") == s.standard
    assert pp.from_code(s, None) == s.standard
    rows = [{"key": "groups", "style": "evil"}, {"key": "main", "style": "x"}, "junk"]
    assert not pp.has_parts(s, rows)
    assert pp.effective_rows(s, rows, code="tabs") == pp.from_code(s, "tabs")


def test_rows_override_only_their_axes():
    s = P.PROMOS
    rows = [{"key": "page_head", "style": "titelbild"}, {"key": "main"}]
    got = pp.effective_rows(s, rows, code="tabs")
    assert got.head == "titelbild" and got.groups == "tabs", "Kopfbild + Reiter — новое сочетание"
    assert pp.legacy_code(s, got) == "tabs", "ближайший код по главной оси"


def test_explicit_standard_beats_the_code():
    s = P.PROMOS
    rows = [{"key": "groups", "style": "auto"}, {"key": "page_head", "style": "aus"}]
    assert pp.has_parts(s, rows)
    assert pp.effective_rows(s, rows, code="regale").groups == ""


def test_hidden_row_sets_nothing_but_star_fields_always_count():
    s = P.PROMOS
    hidden = [{"key": "groups", "style": "tabs", "enabled": False}]
    assert not pp.has_parts(s, hidden)
    star = [{"key": "main", "style": "magazin", "grouping": "ohne"}]
    assert pp.legacy_code(s, pp.effective_rows(s, star)) == "magazin"


def test_own_block_with_the_same_key_is_not_a_part_row():
    s = P.PROMOS
    rows = [{"key": "groups", "id": "own", "style": "tabs"}]
    assert not pp.has_parts(s, rows)


def test_group_and_detail_surfaces():
    g = pp.effective_rows(P.PROMO_GROUP, [{"key": "page_head", "style": "prospekt"}])
    assert g.head == "prospekt" and pp.legacy_code(P.PROMO_GROUP, g) == "prospekt"
    d = pp.effective_rows(P.PROMO_DETAIL, [{"key": "offer", "style": "plakat"}], code="kompakt")
    assert pp.legacy_code(P.PROMO_DETAIL, d) == "plakat"
    assert P.PROMO_DETAIL.keys() == ("offer",)
    assert P.PROMOS.keys() == ("page_head", "groups")


def test_two_codes_with_one_set_of_parts_are_refused():
    with pytest.raises(ValueError):
        pp.surface(
            "x", (pp.Axis("a", "k", ("v",)),), {"": {}, "one": {"a": "v"}, "two": {"a": "v"}}
        )
