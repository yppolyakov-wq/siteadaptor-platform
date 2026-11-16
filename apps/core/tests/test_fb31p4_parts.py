"""FB-31 P4 R1: оси блоков девяти листингов, «Team» и «Galerie» (`apps/core/listing_parts.py`)."""

import pytest

from apps.core import compositions, listing_parts
from apps.core import page_parts as pp


@pytest.mark.parametrize("surface", sorted(compositions.LISTING_SURFACES))
def test_every_code_reads_back_or_falls_to_standard_like_today(surface):
    s = listing_parts.LISTINGS[surface]
    for code in compositions.valid_for(surface):
        parts = pp.from_code(s, code)
        if surface in listing_parts.NAV_SURFACES or code in ("", "kopfbild"):
            assert pp.legacy_code(s, parts) == code, code
            assert pp.from_rows(s, pp.rows_for(s, parts)) == parts
        else:
            assert parts == s.standard, "без подразделов навигация — обычная сетка"


def test_stays_live_on_the_stay_rooms_host():
    assert listing_parts.HOST_OF["stays"] == "stay_rooms"
    assert listing_parts.BY_HOST["stay_rooms"] is listing_parts.LISTINGS["stays"]
    cfg = {"page_blocks": {"stay_rooms": [{"key": "groups", "style": "tabs"}]}}
    assert listing_parts.code_for(cfg, "stays") == "tabs"


def test_banner_and_navigation_combine_with_navigation_first():
    cfg = {
        "page_styles": {"services": "kopfbild"},
        "page_blocks": {"services": [{"key": "groups", "style": "side"}]},
    }
    parts = listing_parts.effective(cfg, "services")
    assert parts.head == "titelbild" and parts.groups == "side"
    assert listing_parts.code_for(cfg, "services") == "navigator", "CSS колонки — по коду"


def test_listings_without_subsections_offer_only_the_banner():
    assert listing_parts.LISTINGS["tours"].keys() == ("page_head",)
    assert listing_parts.LISTINGS["events"].keys() == ("page_head", "groups")


def test_team_and_gallery_views_are_the_home_section_styles():
    from apps.tenants import siteconfig

    for s, key in ((listing_parts.TEAM, "team"), (listing_parts.GALLERY, "gallery")):
        assert s.axis("view").values == siteconfig.SECTION_STYLES[key]
        assert s.keys() == ()


def test_junk_config_reads_as_the_old_code():
    assert listing_parts.code_for({"page_styles": "x", "page_blocks": []}, "blog") == ""
    assert listing_parts.code_for(None, "services") == ""
