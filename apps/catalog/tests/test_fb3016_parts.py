"""FB-30.16 R1 (стратегия FB-31): шаблон страницы каталога → блоки страницы, без изменения
витрины. Замки: каждый код любой поверхности раскладывается и собирается обратно в тот же код;
сохранённые блоки сильнее кода; мусор → обычный вид."""

import pytest

from apps.catalog import catalog_parts as cp
from apps.core import compositions

CODES = {
    surface: [code for code, _l, _h in compositions.styles_for(surface)]
    for surface in ("catalog", "category")
}


@pytest.mark.parametrize("surface", ["catalog", "category"])
def test_every_code_round_trips(surface):
    for code in [*CODES[surface], *(["preisliste"] if surface == "category" else [])]:
        parts = cp.from_code(code)
        assert cp.legacy_code(parts) == code, (surface, code, parts)


def test_codes_land_on_the_block_they_shape():
    assert cp.from_code("kopfbild").head == "titelbild"
    assert cp.from_code("regale").categories == "regale"
    assert cp.from_code("tabs").categories == "tabs"
    assert cp.from_code("navigator").categories == "side"
    assert cp.from_code("kompakt").categories == "index"
    assert cp.from_code("wegweiser").categories == "wegweiser"
    assert cp.from_code("wegweiser").focus is True
    assert cp.from_code("sets").sets == "above"
    assert cp.from_code("mosaik").products == "mosaik"
    assert cp.from_code("magazin").products == "magazin"
    assert cp.from_code("schaufenster").products == "schaufenster"
    assert cp.from_code("").head == "" and cp.from_code("").sets == "below"


def test_grid_hints_follow_the_products_block():
    assert cp.from_code("mosaik").grid == "cols4"
    assert cp.from_code("magazin").grid == "cols2"
    assert cp.from_code("kompakt").grid == "cols6"
    assert cp.from_code("preisliste").grid == "preisliste"
    assert cp.from_code("regale").grid == ""


def test_junk_code_is_the_standard_view():
    assert cp.from_code("gold") == cp.from_code("")


def test_rows_round_trip_and_stored_rows_win():
    for code in CODES["catalog"]:
        rows = cp.rows_for(cp.from_code(code))
        assert cp.from_rows(rows) == cp.from_code(code), code
    stored = [{"key": "categories", "style": "tabs"}, {"key": "main", "style": "mosaik"}]
    cfg = {"page_blocks": {"catalog": stored}}
    parts = cp.effective(cfg, "catalog", code="regale")
    assert parts.categories == "tabs" and parts.products == "mosaik"
    assert cp.effective({}, "catalog", code="regale") == cp.from_code("regale")


def test_rows_order_matches_the_page():
    rows = cp.rows_for(cp.from_code("sets"))
    keys = [r["key"] for r in rows]
    assert keys.index("combos") < keys.index("main"), "сеты над товарами"
    rows = cp.rows_for(cp.from_code(""))
    keys = [r["key"] for r in rows]
    assert keys.index("categories") < keys.index("main") < keys.index("combos")
