"""Замок проверяемого плана стопки `scripts/plan_check.py` (T-14.2 / T-14.3, 2026-11-24).

Планы стопок подробны, но это проза: кто какие файлы правит, от чего зависит срез и сколько эталонов
изменится — с фактом никто не сверял. Расхождения всплывали при своде и в CI (журнал находок:
«предпосылка-без-grep» — 11 из 105; правка ядра после старта срезов; эталоны вне прогноза).
Таблица срезов в плане теперь читается программой: до кода — зависимости, пересечения, существование
названного; после кода — что срез тронул на самом деле.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod():
    spec = importlib.util.spec_from_file_location("plan_check", ROOT / "scripts" / "plan_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HEAD = (
    "## 3. Срезы\n\n| Срез | Зависит от | Свои файлы | Общие файлы | Эталоны | Ветка |\n"
    "|---|---|---|---|---|---|\n"
)


def _plan(*lines):
    return _mod().parse(HEAD + "\n".join(lines) + "\n")


def _exists(*present):
    return lambda path: path in present


def test_parse_reads_dependencies_files_ranges_and_forecast():
    (p0, g3) = _plan(
        "| P0 | — | `apps/core/a.py`, `+apps/core/new.py` | `static/css/app.css` | 2 | claude/s-p0 |",
        "| G3 | P0 | `apps/core/a.py:137-141,213-216` | — | 0 | |",
    )
    assert p0.name == "P0" and p0.deps == [] and p0.goldens == 2 and p0.branch == "claude/s-p0"
    assert [f.path for f in p0.own] == ["apps/core/a.py", "apps/core/new.py"]
    assert p0.own[1].new and not p0.own[0].new
    assert g3.deps == ["P0"] and g3.own[0].ranges == [(137, 141), (213, 216)]
    assert [f.path for f in p0.shared] == ["static/css/app.css"]


def test_clean_plan_has_no_problems():
    slices = _plan(
        "| P0 | — | `apps/core/a.py` | — | 0 | |",
        "| G1 | P0 | `apps/core/a.py:10-20` | — | 0 | |",
        "| G2 | P0 | `apps/core/a.py:30-40` | — | 1 | |",
    )
    assert _mod().check(slices, _exists("apps/core/a.py")) == []


def test_unknown_dependency_and_cycle_are_reported():
    text = " ".join(_mod().check(_plan("| A | Z | `x.py` | — | 0 | |"), _exists("x.py")))
    assert "Z" in text
    loop = _plan("| A | B | `x.py` | — | 0 | |", "| B | A | `y.py` | — | 0 | |")
    assert any("цикл" in p for p in _mod().check(loop, _exists("x.py", "y.py")))


def test_parallel_slices_may_not_share_a_file_or_overlapping_lines():
    whole = _plan("| A | — | `x.py` | — | 0 | |", "| B | — | `x.py:5-9` | — | 0 | |")
    assert any("A" in p and "B" in p and "x.py" in p for p in _mod().check(whole, _exists("x.py")))
    lines = _plan("| A | — | `x.py:1-10` | — | 0 | |", "| B | — | `x.py:8-20` | — | 0 | |")
    assert any("x.py" in p for p in _mod().check(lines, _exists("x.py")))
    apart = _plan("| A | — | `x.py:1-10` | — | 0 | |", "| B | — | `x.py:11-20` | — | 0 | |")
    assert _mod().check(apart, _exists("x.py")) == []


def test_dependent_slices_may_touch_the_same_file():
    # Срез после P0 правит тот же файл по очереди — это не пересечение.
    chain = _plan("| P0 | — | `x.py` | — | 0 | |", "| A | P0 | `x.py` | — | 0 | |")
    assert _mod().check(chain, _exists("x.py")) == []


def test_file_reserved_for_the_coordinator_is_not_a_slice_file():
    slices = _plan(
        "| P0 | — | `x.py` | `static/css/app.css` | 0 | |",
        "| A | P0 | `static/css/app.css` | — | 0 | |",
    )
    found = _mod().check(slices, _exists("x.py", "static/css/app.css"))
    assert any("app.css" in p and "координатор" in p for p in found)


def test_named_file_that_does_not_exist_is_a_premise_without_grep():
    slices = _plan("| A | — | `apps/core/gone.py`, `+apps/core/new.py` | — | 0 | |")
    found = _mod().check(slices, _exists())
    assert any("gone.py" in p for p in found)
    assert not any("new.py" in p for p in found), "новый файл помечен «+» — его ещё нет"


def test_missing_golden_forecast_is_reported():
    assert any(
        "прогноз" in p for p in _mod().check(_plan("| A | — | `x.py` | — | ? | |"), _exists("x.py"))
    )


def test_waves_show_what_can_run_in_parallel():
    slices = _plan(
        "| P0 | — | `a.py` | — | 0 | |",
        "| G1 | P0 | `b.py` | — | 0 | |",
        "| G2 | P0 | `c.py` | — | 0 | |",
        "| K | G1 | `d.py` | — | 0 | |",
    )
    assert _mod().waves(slices) == [["P0"], ["G1", "G2"], ["K"]]


def test_verify_reports_files_outside_the_plan_and_golden_surprises():
    slices = _plan(
        "| P0 | — | `apps/core/a.py`, `templates/tenant/_bw_*.html` | `static/css/app.css` | 0 | |",
        "| G1 | P0 | `apps/core/b.py:10-20` | — | 2 | |",
    )
    touched = {
        "P0": ["apps/core/a.py", "templates/tenant/_bw_inhalt.html"],
        "G1": [
            "apps/core/b.py",
            "apps/core/a.py",
            "static/css/app.css",
            "apps/core/tests/test_b.py",
            "apps/core/tests/golden_x/one.html",
            "apps/core/tests/golden_x/two.html",
            "apps/core/tests/golden_y/three.html",
        ],
    }
    found = _mod().verify(slices, touched)
    text = " ".join(found)
    assert "G1" in text and "apps/core/a.py" in text, "правка чужого файла ядра после старта срезов"
    assert "app.css" in text and "координатор" in text
    assert "эталон" in text and "3" in text and "2" in text
    assert "test_b.py" not in text, "свои тесты срез пишет без записи в плане"
    assert not any(p.startswith("P0") for p in found)


def test_template_is_a_valid_plan_table():
    text = (ROOT / "docs" / "stack-plan-template.md").read_text(encoding="utf-8")
    slices = _mod().parse(text)
    assert len(slices) >= 3
    assert [p for p in _mod().check(slices, lambda path: True) if "прогноз" not in p] == []


# --- ревью silent-failure-hunter (2026-11-24): где скрипт молча говорил «в порядке» ---------------


def test_row_with_wrong_number_of_cells_is_an_error_not_a_skipped_slice():
    text = HEAD + "| A | — | `x.py` | — | 0 | |\n| B | — | `y.py` | a | b | 0 | |\n"
    errors = _mod().table_errors(text)
    assert any("B" in e and "6" in e for e in errors), errors
    assert _mod().table_errors(HEAD + "| A | — | `x.py` | — | 0 | |\n") == []


def test_rows_after_a_blank_line_are_reported_not_lost():
    text = HEAD + "| A | — | `x.py` | — | 0 | |\n\n| B | — | `y.py` | — | 0 | |\n"
    assert [s.name for s in _mod().parse(text)] == ["A"]
    assert any("разрыв" in e and "B" in e for e in _mod().table_errors(text))


def test_slice_without_files_or_with_files_outside_backticks_is_reported():
    bare = _plan("| A | — | a.py | — | 0 | |", "| B | — | a.py | — | 0 | |")
    found = _mod().check(bare, _exists("a.py"))
    assert any("A" in p and "бэктик" in p for p in found), found
    empty = _plan("| A | — | — | — | 0 | |")
    assert any("A" in p and "файл" in p for p in _mod().check(empty, _exists()))


def test_directory_and_file_inside_it_overlap():
    slices = _plan("| A | — | `apps/core/` | — | 0 | |", "| B | — | `apps/core/x.py` | — | 0 | |")
    found = _mod().check(slices, _exists("apps/core/", "apps/core/x.py"))
    assert any("A" in p and "B" in p for p in found), found


def test_verify_does_not_pass_a_slice_it_could_not_compare():
    slices = _plan("| A | — | `x.py` | — | 0 | |", "| B | — | `y.py` | — | ? | |")
    found = _mod().verify(slices, {"A": [], "B": ["y.py"]})
    assert any("A" in p and "не отличается" in p for p in found), found
    assert any("B" in p and "прогноз" in p for p in found), found


def test_verify_compares_a_chained_slice_by_its_own_range():
    """FB-33 стопка 13: ветки срезов шли цепочкой (d4b от d4a от d3) — сверка «база...ветка»
    приписывала срезу файлы предшественников (52 ложных ✗). В колонке «Ветка» — диапазон
    `откуда..куда`: сверяется только он; простая ветка — как раньше, от `--base`."""
    m = _mod()
    assert m.diff_spec("P0", "claude/x-d4a..claude/x-d4b") == "claude/x-d4a...claude/x-d4b"
    assert m.diff_spec("P0", "claude/x-d3") == "P0...claude/x-d3"
