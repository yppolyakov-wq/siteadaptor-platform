"""Замок карты работ `docs/fb33-map.md` и её разбора `scripts/work_map.py` (T-14.1, 2026-11-24).

Порядок оставшихся стопок FB-33 жил в прозе двух документов одного дня и разошёлся (переводы
USP/SEO: стопка 16 в одном, 14 в другом). Карта — единственное место порядка и статуса; этот
замок не даёт ей устареть молча и не даёт начать стопку раньше её зависимостей.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
MAP = ROOT / "docs" / "fb33-map.md"


def _mod():
    spec = importlib.util.spec_from_file_location("work_map", ROOT / "scripts" / "work_map.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HEAD = "| Стопка | Статус | Зависит от | Срезы | Что | До кода нужно |\n|---|---|---|---|---|---|\n"


def _rows(*lines):
    return _mod().parse(HEAD + "\n".join(lines) + "\n")


def test_parse_reads_stack_status_dependencies_and_slices():
    rows = _rows(
        "| 12 | в main | — | M5d-2, M5d-3 | окно «Inhalt» | — |",
        "| 13 | дальше | 12 | M7-0, D1 | учёт и деньги | решение D6 |",
    )
    assert [r.stack for r in rows] == ["12", "13"]
    assert rows[1].status == "дальше" and rows[1].deps == ["12"]
    assert rows[1].slices == ["M7-0", "D1"] and rows[1].needs == "решение D6"


def test_clean_map_has_no_problems():
    rows = _rows("| 12 | в main | — | A | a | — |", "| 13 | в работе | 12 | B | b | — |")
    assert _mod().problems(rows, catalog="A B") == []


def test_unknown_status_and_unknown_dependency_are_reported():
    rows = _rows("| 13 | скоро | 99 | B | b | — |")
    text = " ".join(_mod().problems(rows, catalog="B"))
    assert "статус" in text and "99" in text


def test_cycle_is_reported():
    rows = _rows("| 13 | дальше | 14 | B | b | — |", "| 14 | дальше | 13 | C | c | — |")
    assert any("цикл" in p for p in _mod().problems(rows, catalog="B C"))


def test_only_one_stack_may_be_in_progress():
    rows = _rows("| 13 | в работе | — | B | b | — |", "| 14 | в работе | — | C | c | — |")
    assert any("в работе" in p and "13" in p and "14" in p for p in _mod().problems(rows, "B C"))


def test_stack_cannot_start_before_its_dependencies_are_in_main():
    # Сама ошибка «потери последовательности»: стопка в работе, а зависимость не сведена.
    rows = _rows("| 17 | дальше | — | M6-0 | план | — |", "| 18 | в работе | 17 | M6a | код | — |")
    assert any("18" in p and "17" in p for p in _mod().problems(rows, catalog="M6-0 M6a"))


def test_slices_of_a_started_stack_must_have_catalog_ids():
    rows = _rows("| 13 | в работе | — | M7-0, D1 | учёт | — |")
    problems = _mod().problems(rows, catalog="есть только M7-0")
    assert any("D1" in p and "task-catalog" in p for p in problems)
    planned = _rows("| 16 | дальше | — | T1, T2 | переводы | — |")
    assert _mod().problems(planned, catalog="") == [], "у будущей стопки метки ещё рабочие"


def test_ready_lists_stacks_whose_dependencies_are_done():
    rows = _rows(
        "| 12 | в main | — | A | a | — |",
        "| 13 | дальше | 12 | B | b | — |",
        "| 18 | дальше | 17 | C | c | — |",
        "| 17 | дальше | — | D | d | — |",
        "| M2i-7b | ждёт решения | — | M2i-7b | адрес из оплаты | решение |",
    )
    assert [r.stack for r in _mod().ready(rows)] == ["13", "17"]


def test_graph_shows_every_stack_and_every_dependency():
    rows = _rows("| 12 | в main | — | A | a | — |", "| 13 | дальше | 12 | B | учёт и деньги | — |")
    graph = _mod().mermaid(rows)
    assert graph.startswith("```mermaid\nflowchart LR")
    assert "s12 --> s13" in graph and "учёт и деньги" in graph


def test_real_map_is_clean_and_its_graph_is_fresh():
    mod = _mod()
    text = MAP.read_text(encoding="utf-8")
    rows = mod.parse(text)
    assert len(rows) >= 10, "карта пуста или таблица не разобрана"
    catalog = (ROOT / "docs" / "task-catalog.md").read_text(encoding="utf-8")
    assert mod.problems(rows, catalog) == []
    assert mod.with_graph(text, rows) == text, (
        "граф в docs/fb33-map.md устарел — uv run python scripts/work_map.py --graph"
    )


def test_order_lives_only_in_the_map():
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "docs/fb33-map.md" in claude, "CLAUDE.md §3 должен вести на карту"
    for name in ("fb33-handoff-2026-11-24.md", "fb33-remaining-plan-2026-11-24.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "fb33-map.md" in text, f"{name}: порядок стопок — ссылкой на карту"
