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
    assert row == "| 2026-11-22 | FB-33 стопка 5 | 6 | 3 | 50 % | 0 | 1 | 2 | 0 | 2 |"


def test_real_report_builds_and_names_the_indicator():
    text = _mod().report("2026-11-19")
    assert "Индикатор: доля «правок ревью»" in text
    assert "CLAUDE.md" in text and "sa-*" in text


def test_datasets_rows_carry_share_and_match_the_report():
    data = _mod().datasets("2026-11-19")
    assert {"steps", "weeks", "context", "journal", "history", "map"} == set(data)
    assert len(data["map"]) >= 10 and {"stack", "status", "depends", "what"} <= set(data["map"][0])
    assert data["history"], "история снимков пуста — страница-панель потеряет сравнение по стопкам"
    assert {"stack", "share", "plan_commits", "plan", "diff", "after", "red_ci"} <= set(
        data["history"][0]
    )
    for row in data["steps"] + data["weeks"]:
        assert row["share"] == round(100 * row["review"] / row["commits"])
    assert all(row["kb"] > 0 for row in data["context"])


# --- T-13.8b (2026-11-23): счётчик считает переделкой только правки ПОСЛЕ кода --------------


def test_preview_is_not_review():
    # «превью» содержит «ревью»: срезы «Vorschau» и страница 404 с превью считались переделкой.
    mod = _mod()
    assert mod.kind("FB-33 M5a: страница 404 с блоками, тип и превью") == "work"
    assert mod.kind("FB-33 M3-7: стенд «Vorschau» — превью черновика") == "work"
    assert not mod.is_review("FB-33 M5a: замки страницы 404 — cookie и кэш, превью")


def test_plan_review_is_counted_apart_from_rework():
    # Ревью плана — работа ДО кода, которой мы и добивались; в долю переделки она не входит.
    mod = _mod()
    for subject in (
        "FB-33 стопка 10: план — правки по ревью architect и a11y-architect (§8: 7 HIGH)",
        "FB-33 стопка 8: план — поправки ревью planner к срезу M5a (R1–R8)",
        "FB-33 стопка 10: черновик плана (planner) — M5b-2 W0–W3 по V4",
        "FB-33 стопка 8: P0 — план (docs/fb33-stack8-plan), ID срезов в каталоге, якоря",
    ):
        assert mod.kind(subject) == "plan", subject
        assert not mod.is_review(subject), subject


def test_journal_docs_and_skill_updates_are_not_rework():
    mod = _mod()
    for subject in (
        "FB-33 стопка 8: журнал находок — девять находок ревью плана и разведки (до кода)",
        "FB-33 стопка 9: журнал находок — ревью планов и диффов срезов M3-9d, M5a-2, M5b-1",
        "FB-33 стопка 8: скиллы sa-* — правила по находкам стопки",
        "FB-33 стопка 10: снимок статистики стопки (dev_stats --snapshot)",
        "FB-33 стопка 7: доки — срезы M4c, M3-9a/b (журнал, каталог, ревью)",
        "FB-33: передача стопки 11 — очередь срезов, находки ревью",
        "FB-33 стопка 8: ретро — строка тренда в журнале находок (план 11, дифф 18)",
    ):
        assert mod.kind(subject) == "docs", subject


def test_rework_is_a_fix_or_lock_after_code_review():
    mod = _mod()
    for subject in (
        "FB-33 M5b-2 ревью: замки по ревью, раунд 2 (strict xfail до правки)",
        "FB-33 M5a: правки ревью — третий рубеж 404 (ответ без шаблона)",
        "FB-33 M3-9c: цели 24 px — остальные ссылки секций главной (находка стенда)",
        "FB-33 стопка 8: правки финального ревью — замки 404 не зависят от кэша",
        # хвост темы упоминает журнал и скиллы — это всё равно правка ревью, а не запись о ней
        "FB-33 M5a: правки ревью — третий рубеж 404, одна запись; строка в журнал находок, скиллы sa-*",
        "FB-33 M2i-6: правка ревью — нетронутый пресет уходит с типом (журнал находок, документы)",
    ):
        assert mod.kind(subject) == "rework", subject
        assert mod.is_review(subject), subject


def test_snapshot_row_reports_plan_review_commits_in_their_own_column():
    mod = _mod()
    commits = [
        ("2026-11-22", "FB-33 стопка 8: план — поправки ревью planner к срезу M5a"),
        ("2026-11-22", "FB-33 стопка 8: журнал находок — девять находок ревью плана"),
        ("2026-11-22", "FB-33 M5a: страница 404 с блоками и превью"),
        ("2026-11-22", "FB-33 M5a: правки ревью — третий рубеж 404"),
    ]
    row = mod.snapshot_row("FB-33 стопка 8", commits, {"rows": []}, "1", "2026-11-22")
    assert row == "| 2026-11-22 | FB-33 стопка 8 | 4 | 1 | 25 % | 1 | 0 | 0 | 0 | 1 |"
