"""Закрытие стопки одной командой (T-14.4): список ✓/✗ вместо «не забыть».

    uv run python scripts/stack_close.py --stack 13                      # метка «FB-33 стопка 13»
    uv run python scripts/stack_close.py --stack 13 --plan docs/fb33-stack13-plan-….md --base <P0>
    uv run python scripts/stack_close.py --stack 13 --label "FB-33 стопка 13" --ref HEAD

Проверяет (ничего не меняет): снимок в `docs/dev-stats-history.md`, строка тренда в
`docs/skill-feedback.md`, запись в `docs/build-log.md`, упоминание в `CLAUDE.md` §3, в `docs/wip/`
нет файлов этой стопки, план сверен с фактом (`plan_check --verify`, если дан `--plan`), ветка
сведена в `origin/main`, статус в карте `docs/fb33-map.md`. Всё ✓ — ставь статус:
`uv run python scripts/work_map.py --set 13 "в main"`. До свода в main все пункты, кроме «ветка в
main», уже должны быть ✓ — так видно, что осталось только слово владельца.
Проверки — чистая функция `checks`, замок `apps/core/tests/test_stack_close.py`.
"""

import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)  # dataclass при импорте по пути ищет свой модуль здесь
    spec.loader.exec_module(mod)
    return mod


def _mentions(text: str, label: str) -> bool:
    """Метка целиком: «стопка 13» не находится в «стопка 130», «13a», «13б», «13.1»."""
    return bool(re.search(re.escape(label) + r"(?![\w]|\.\d)", text))


def checks(label: str, stack: str, state: dict) -> list[tuple[bool | None, str, str]]:
    """(пройдено | None — не проверялось, что проверяли, что сделать)."""
    journal = state["journal"]
    trend = journal.split("## Находки")[0].split("## Тренд")[-1] if "## Тренд" in journal else ""
    wip = [f for f in state["wip"] if re.search(rf"stack-?0*{re.escape(stack)}(?!\d)", f)]
    in_map = state["map_status"]
    return [
        (
            any(
                _mentions(line, label)
                for line in state["history"].splitlines()
                if line.startswith("|")
            ),
            "снимок статистики",
            f'uv run python scripts/dev_stats.py --snapshot "{label}" --range origin/main..HEAD --red-ci N',
        ),
        (
            _mentions(trend, label),
            "тренд журнала",
            "строка в таблицу «Тренд» docs/skill-feedback.md",
        ),
        (
            any(
                _mentions(line, label)
                for line in state["build_log"].splitlines()
                if line.startswith("#")
            ),
            "build-log",
            f"запись «## дата — {label}: …» в docs/build-log.md",
        ),
        (_mentions(state["claude"], label), "CLAUDE.md §3", f"строка «Сейчас» про «{label}»"),
        (not wip, "docs/wip пуст", "снять незакоммиченное: " + ", ".join(wip)),
        (
            # None — сверка не выполнялась: это «не проверено», а не ✓.
            None if state["plan_problems"] is None else not state["plan_problems"],
            "план сверен с фактом",
            "; ".join(
                (state["plan_problems"] or ["план не задан (--plan) — сверка не выполнена"])[:5]
            ),
        ),
        (
            state["merged"],
            "ветка в main",
            "git не ответил (нет origin/main или клон обрезан) — проверить вручную: git fetch origin main"
            if state["merged"] is None
            else "FF в main по «делай» владельца после зелёного CI",
        ),
        (
            in_map in ("в работе", "в main"),
            "статус в карте",
            f"стопки нет в docs/fb33-map.md или она не взята в работу (сейчас: {in_map or 'нет строки'})",
        ),
    ]


def _merged(ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ref, "origin/main"],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def read_state(
    label: str, stack: str, merged: bool | None, plan: str, base: str = "origin/main"
) -> dict:
    docs = ROOT / "docs"
    work_map = _load("work_map")
    rows = {r.stack: r for r in work_map.parse((docs / "fb33-map.md").read_text(encoding="utf-8"))}
    plan_problems: list[str] | None = None
    if plan:
        plan_check = _load("plan_check")
        slices = plan_check.parse(pathlib.Path(plan).read_text(encoding="utf-8"))
        if not slices:
            plan_problems = ["в плане нет проверяемой таблицы срезов (docs/stack-plan-template.md)"]
        else:
            text = pathlib.Path(plan).read_text(encoding="utf-8")
            touched = {s.name: plan_check._touched(base, s.branch) for s in slices if s.branch}
            # И проверка «до кода» тоже: таблица могла измениться после раздачи срезов.
            plan_problems = (
                plan_check.table_errors(text)
                + plan_check.check(slices)
                + plan_check.verify(slices, touched)
            )
            missing = [s.name for s in slices if not s.branch]
            if missing:
                plan_problems.append("нет ветки для сверки: " + ", ".join(missing))
    wip_dir = docs / "wip"
    return {
        "history": (docs / "dev-stats-history.md").read_text(encoding="utf-8"),
        "journal": (docs / "skill-feedback.md").read_text(encoding="utf-8"),
        "build_log": (docs / "build-log.md").read_text(encoding="utf-8"),
        "claude": (ROOT / "CLAUDE.md").read_text(encoding="utf-8"),
        "wip": sorted(str(p.relative_to(ROOT)) for p in wip_dir.rglob("*") if p.is_file())
        if wip_dir.exists()
        else [],
        "merged": merged,
        "map_status": rows[stack].status if stack in rows else None,
        "plan_problems": plan_problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Закрытие стопки (T-14.4)")
    ap.add_argument("--stack", required=True, help="номер стопки, как в карте")
    ap.add_argument("--label", help="метка стопки в документах; по умолчанию «FB-33 стопка N»")
    ap.add_argument("--plan", default="", help="план стопки — для сверки факта с планом")
    ap.add_argument("--base", default="origin/main", help="коммит P0 для сверки плана")
    ap.add_argument("--ref", default="HEAD", help="верхушка стопки")
    ap.add_argument(
        "--no-plan",
        action="store_true",
        help="у стопки нет проверяемого плана (до T-14) — не считать ошибкой",
    )
    args = ap.parse_args()
    label = args.label or f"FB-33 стопка {args.stack}"
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT)
    state = read_state(label, args.stack, _merged(args.ref), args.plan, args.base)
    results = checks(label, args.stack, state)
    print(f"закрытие «{label}»:")
    for ok, name, todo in results:
        mark = "✓" if ok else ("–" if ok is None else "✗")
        print(f"  {mark} {name}" + ("" if ok else f" — {todo}"))
    failed = [
        name
        for ok, name, _ in results
        if ok is False or (ok is None and not (args.no_plan and name == "план сверен с фактом"))
    ]
    if not failed:
        print(f'всё закрыто: uv run python scripts/work_map.py --set {args.stack} "в main"')
    elif failed == ["ветка в main"]:
        print("осталось только слово владельца и FF в main")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
