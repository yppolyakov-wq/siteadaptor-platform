"""Замок закрытия стопки `scripts/stack_close.py` (T-14.4, 2026-11-24).

«Закрыть стопку 12» стояло шагом 0 следующей стопки: снимок статистики, тренд журнала, build-log,
`docs/wip/`, свод в main держались на памяти сессии. Теперь это одна команда со списком ✓/✗.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "stack_close", ROOT / "scripts" / "stack_close.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _state(**over):
    state = {
        "history": "| 2026-11-24 | FB-33 стопка 13 | 40 | 6 | 15 % | 2 | 9 | 5 | 0 | 0 |\n",
        "journal": "## Тренд\n| FB-33 стопка 13 (2026-11-25) | 40 | 6 |\n## Находки\n",
        "build_log": "## 2026-11-25 — FB-33 стопка 13: учёт, данные и деньги\n",
        "claude": "- **Сейчас** (2026-11-25): FB-33 стопка 13 сделана\n",
        "wip": [],
        "merged": True,
        "map_status": "в работе",
        "plan_problems": [],
    }
    state.update(over)
    return state


def _failed(**over):
    return [
        name for ok, name, _ in _mod().checks("FB-33 стопка 13", "13", _state(**over)) if not ok
    ]


def test_a_finished_stack_passes_every_check():
    assert _failed() == []


def test_each_forgotten_step_is_named():
    assert _failed(history="") == ["снимок статистики"]
    assert _failed(journal="## Тренд\n## Находки\n") == ["тренд журнала"]
    assert _failed(build_log="## 2026-11-25 — что-то другое\n") == ["build-log"]
    assert _failed(claude="- **Сейчас**: стопка 12\n") == ["CLAUDE.md §3"]
    assert _failed(wip=["docs/wip/fb33-stack13-d1-wip.patch"]) == ["docs/wip пуст"]
    assert _failed(merged=False) == ["ветка в main"]
    assert _failed(plan_problems=["G1: тронул x.py вне плана"]) == ["план сверен с фактом"]


def test_plan_that_was_not_compared_is_not_reported_as_passed():
    # Сверка без плана — «не проверено», а не ✓: молчаливое прохождение хуже отсутствия проверки.
    results = _mod().checks("FB-33 стопка 13", "13", _state(plan_problems=None))
    assert [ok for ok, name, _ in results if name == "план сверен с фактом"] == [None]


def test_label_of_another_stack_does_not_count():
    # «стопка 13» не должна находиться в строке «стопка 130» или «стопки 13–14 (план)».
    assert _failed(history="| 2026-11-24 | FB-33 стопка 130 | 1 | 0 | 0 % |\n") == [
        "снимок статистики"
    ]


def test_map_status_is_checked():
    assert _failed(map_status="дальше") == ["статус в карте"]
    assert _failed(map_status=None) == ["статус в карте"]
    assert _failed(map_status="в main") == []


def test_wip_of_other_stacks_does_not_block():
    assert _failed(wip=["docs/wip/fb33-stack14-e1-wip.patch"]) == []


def test_stack_12_closed_by_hand_passes_the_real_check():
    # Стопка 12 закрыта вручную до появления команды — на ней скрипт проверяется вхолостую.
    mod = _mod()
    state = mod.read_state("FB-33 стопка 12", "12", merged=True, plan="")
    failed = [name for ok, name, _ in mod.checks("FB-33 стопка 12", "12", state) if ok is False]
    assert failed == [], failed


# --- ревью silent-failure-hunter (2026-11-24) ---------------------------------------------------


def test_label_does_not_match_a_sub_stack():
    for other in ("FB-33 стопка 13a", "FB-33 стопка 13б", "FB-33 стопка 13.1"):
        row = f"| 2026-11-24 | {other} | 1 | 0 | 0 % |\n"
        assert _failed(history=row) == ["снимок статистики"], other
    assert _failed(history="| 2026-11-24 | FB-33 стопка 13 | 1 |\n") == []
    assert _failed(build_log="## 2026-11-25 — FB-33 стопка 13.\n") == [], (
        "точка в конце фразы — та же стопка"
    )


def test_git_failure_is_not_reported_as_not_merged():
    # Обрезанный клон или недоступный origin: «не знаю» — не то же, что «не сведено».
    results = _mod().checks("FB-33 стопка 13", "13", _state(merged=None))
    hit = [(ok, todo) for ok, name, todo in results if name == "ветка в main"]
    assert hit[0][0] is None and "git" in hit[0][1]
