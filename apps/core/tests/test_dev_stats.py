"""Замок разбора `scripts/dev_stats.py` (T-13.8, 2026-11-21).

Отчёт — индикатор «помогают ли скиллы и гейт»: доля коммитов «правки ревью» и находки журнала.
Если разбор тем коммитов или журнала тихо сломается, индикатор покажет ноль и «всё хорошо».
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod():
    spec = importlib.util.spec_from_file_location("dev_stats", ROOT / "scripts" / "dev_stats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


COMMITS = [
    ("2026-11-21", "FB-33 M3-7: правки ревью (сервер) — whole_page"),
    ("2026-11-21", "FB-33 M3-7: замки ревью — точный якорь"),
    ("2026-11-21", "FB-33 M3-7: Vorschau в окне блока"),
    ("2026-11-20", "FB-33 M4b: находки ревью — устаревшая вкладка"),
    ("2026-11-20", "FB-33 M4b: снятие дублей"),
    ("2026-11-20", "FB-33 M4b: стенд"),
    ("2026-11-10", "T-13.1: scripts/preflight.py"),
]


def test_review_commit_is_recognised_by_subject():
    mod = _mod()
    assert mod.is_review("FB-33 M3-5c ревью django-reviewer: удалённый блок")
    assert mod.is_review("FB-33 M4b: находки ревью — a11y")
    assert not mod.is_review("FB-33 M4b: снятие дублей старой панели")


def test_step_is_the_task_prefix():
    mod = _mod()
    assert mod.step_of("FB-33 M3-7: правки ревью (сервер)") == "FB-33 M3-7"
    assert mod.step_of("FB-33 M3-5c ревью: замки") == "FB-33 M3-5c"
    assert mod.step_of("FB-33 стопка 5: ревью — сняты") == "FB-33 стопка 5"
    assert mod.step_of("T-13.1: scripts/preflight.py") == "T-13.1"
    assert mod.step_of("Merge branch") == "прочее"


def test_weekly_counts_total_and_review_in_order():
    weeks = _mod().weekly(COMMITS)
    assert weeks == [("2026-W46", 1, 0), ("2026-W47", 6, 3)]


def test_by_step_keeps_recent_first_and_hides_small_steps():
    steps = _mod().by_step(COMMITS)
    assert steps == [("FB-33 M3-7", 3, 2), ("FB-33 M4b", 3, 1)]


def test_journal_counts_classes_skills_and_answers():
    text = (
        "## Находки\n\n| Дата | Шаг | Когда | Кто | Класс | Что | Скилл | Скилл покрывал? | Что сделано |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| 2026-11-22 | FB-33 M5 | план | planner | a11y | x | sa-block-editor | нет правила | строка |\n"
        "| 2026-11-22 | FB-33 M5 | дифф | CI | i18n | y | — | было, не сработало | замок test_x |\n"
    )
    j = _mod().journal(text)
    assert j["total"] == 2
    assert j["by_class"]["a11y"] == 1 and j["by_class"]["i18n"] == 1
    assert j["by_skill"]["—"] == 1
    assert j["by_answer"]["было, не сработало"] == 1
    assert j["by_when"]["план"] == 1 and j["by_when"]["дифф"] == 1


def test_snapshot_row_joins_commits_with_journal_findings_of_the_same_steps():
    mod = _mod()
    found = mod.journal(
        "## Находки\n\n| h |\n|---|\n"
        "| 2026-11-22 | FB-33 M3-7 | план | planner | a11y | x | sa-block-editor | нет правила | строка |\n"
        "| 2026-11-22 | FB-33 M3-7 | дифф | CI | i18n | y | — | нет правила | строка |\n"
        "| 2026-11-22 | FB-33 M3-7 | дифф | стенд | стенд | z | sa-stand | нет правила | строка |\n"
        "| 2026-11-22 | T-99 | после мержа | владелец | другое | q | — | нет правила | строка |\n"
    )
    row = mod.snapshot_row("FB-33 стопка 5", COMMITS[:6], found, "2", "2026-11-22")
    assert row == "| 2026-11-22 | FB-33 стопка 5 | 6 | 3 | 50 % | 1 | 2 | 0 | 2 |"


def test_real_report_builds_and_names_the_indicator():
    text = _mod().report("2026-11-19")
    assert "Индикатор: доля «правок ревью»" in text
    assert "CLAUDE.md" in text and "sa-*" in text


def test_datasets_rows_carry_share_and_match_the_report():
    data = _mod().datasets("2026-11-19")
    assert {"steps", "weeks", "context", "journal"} == set(data)
    for row in data["steps"] + data["weeks"]:
        assert row["share"] == round(100 * row["review"] / row["commits"])
    assert all(row["kb"] > 0 for row in data["context"])
