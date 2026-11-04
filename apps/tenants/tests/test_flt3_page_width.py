"""FLT-3a: ширина витрины (план `docs/flt3-storefront-filters-plan-2026-11-04.md` §1)."""

import pytest

from apps.tenants import siteconfig


@pytest.mark.parametrize(
    "raw, kept",
    [
        ({"page_width": "normal"}, "normal"),
        ({"page_width": "full"}, "full"),
        ({}, None),
        ({"page_width": "x"}, None),
    ],
)
def test_page_width_is_presence_minimal(raw, kept):
    out = siteconfig.normalize_site_defaults(raw)
    assert out.get("page_width") == kept


def test_width_classes():
    assert siteconfig.PAGE_WIDTH_CLASSES[""] == "max-w-screen-2xl"  # решение владельца: 1536
    assert siteconfig.PAGE_WIDTH_CLASSES["normal"] == "max-w-7xl"  # прежний вид
    assert siteconfig.PAGE_WIDTH_CLASSES["full"] == "max-w-none"


def test_base_template_has_no_fixed_width_left():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[3] / "templates/storefront/_base.html").read_text()
    assert "max-w-7xl" not in html
    assert html.count("storefront_page_width") == 4  # верх шапки (2 вида), main, подвал
