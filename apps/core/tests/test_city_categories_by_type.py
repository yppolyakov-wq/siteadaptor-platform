"""Категории каталога города привязаны к типу бизнеса (решение владельца 2026-10-19)."""

import pytest

from apps.core import city_categories as cc
from apps.tenants.models import Tenant


def _keys(groups):
    return {key for _label, items in groups for key, _lbl in items}


def _sections(groups):
    return {cc._CATEGORY[key].section for key in _keys(groups)}


def test_every_mapped_section_and_type_exists():
    types = {v for v, _l in Tenant.BUSINESS_TYPES}
    known = {s.key for s in cc.SECTIONS}
    for btype, sections in cc.SECTIONS_BY_BUSINESS_TYPE.items():
        assert btype in types, btype
        assert sections and set(sections) <= known, btype


@pytest.mark.parametrize("btype", sorted(cc.SECTIONS_BY_BUSINESS_TYPE))
def test_type_suggestion_is_allowed_for_its_type(btype):
    """Подсказка категории по типу не может оказаться вне его разделов."""
    suggestion = cc.BY_BUSINESS_TYPE.get(btype, "")
    assert cc.category_allowed(suggestion, btype)


def test_grouped_choices_only_types_sections_main_first():
    groups = cc.grouped_choices("bakery")
    assert _sections(groups) == {"lebensmittel-getraenke", "essen-gastronomie"}
    first_key = groups[0][1][0][0]
    assert cc._CATEGORY[first_key].section == "lebensmittel-getraenke"


def test_universal_and_unknown_types_see_everything():
    everything = _keys(cc.grouped_choices())
    assert _keys(cc.grouped_choices("retail")) == everything
    assert _keys(cc.grouped_choices("")) == everything


def test_keep_preserves_saved_foreign_category():
    """Уже сохранённая категория вне разделов остаётся — Save её молча не сбросит."""
    assert "kunst" not in _keys(cc.grouped_choices("bakery"))
    assert "kunst" in _keys(cc.grouped_choices("bakery", keep="kunst"))
    assert "kunst" in _keys(cc.grouped_choices("bakery", keep={"kunst"}))


def test_category_allowed():
    assert cc.category_allowed("", "bakery")
    assert cc.category_allowed("brot-backwaren", "bakery")
    assert not cc.category_allowed("kunst", "bakery")
    assert cc.category_allowed("kunst", "retail")
    assert not cc.category_allowed("unbekannt", "retail")


def test_allowed_by_type_matches_category_allowed():
    for btype, keys in cc.allowed_by_type().items():
        for c in cc.CATEGORIES:
            assert (c.key in keys) == cc.category_allowed(c.key, btype)
