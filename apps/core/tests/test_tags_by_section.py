"""T-8.23e: Merkmale по разделам (решение владельца 2026-10-11)."""

from apps.core import city_categories as cc


def test_every_section_has_its_tags_and_all_known():
    known = {k for k, _l in cc.TAGS}
    for s in cc.SECTIONS:
        tags = cc.TAGS_BY_SECTION.get(s.key)
        assert tags, s.key
        assert set(tags) <= known, s.key


def test_every_tag_belongs_to_some_section():
    used = {t for tags in cc.TAGS_BY_SECTION.values() for t in tags}
    assert used == {k for k, _l in cc.TAGS}


def test_tags_for_category_section_and_unknown():
    assert "vegan" in cc.tags_for("brot-backwaren")
    assert "vegan" not in cc.tags_for("damenmode")
    assert "gebraucht" in cc.tags_for("mode-accessoires")
    assert cc.tags_for("") == [k for k, _l in cc.TAGS]


def test_allowed_tags_drop_foreign_ones():
    assert cc.allowed_tags(["vegan", "gebraucht"], "damenmode") == ["gebraucht"]
    assert cc.allowed_tags(["vegan", "yoga"], "") == ["vegan", "yoga"]
