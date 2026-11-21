"""Финальный гейт перед пушем (T-13.1): один запуск вместо списка «не забыть» из CLAUDE.md §5.

Смотрит, что изменено относительно `origin/main` (коммиты ветки + рабочее дерево + новые
файлы), и гоняет ровно те проверки, которые CI прогонит на этих путях:

    uv run python scripts/preflight.py            # всё по изменённым путям
    uv run python scripts/preflight.py --fast     # без pytest (ruff, i18n, CSS)
    uv run python scripts/preflight.py --plan     # только показать, что будет запущено
    uv run python scripts/preflight.py --jobs 4   # pytest в 4 процесса (xdist)
    uv run python scripts/preflight.py --base origin/claude/x

Шаг, который нельзя выполнить (нет npm-пакетов и т.п.), считается НЕ пройденным: гейт не
должен молча зеленеть. `msgfmt --check-format` и `i18n_gap.py` локально не запускаются
(нет gettext) — это остаётся за CI, скрипт об этом напоминает при правке `.po`.

Таблица «путь → проверки» — чистая функция `plan()`, замок
`apps/core/tests/test_preflight_plan.py`.
"""

import argparse
import dataclasses
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Локально виснет (среда), на CI зелёный — CLAUDE.md §5.
HANGING = "apps/billing/tests/test_tasks.py"

LOCKS = {
    "claude_md": "apps/core/tests/test_claude_md_budget.py",
    "rules": "apps/core/tests/test_claude_rules_budget.py",
    "skills": "apps/core/tests/test_project_skills.py",
    "template_comments": "apps/core/tests/test_template_comments.py",
    "preflight": "apps/core/tests/test_preflight_plan.py",
}

# Источники сборки Tailwind (tailwind.config.js: content + сам конфиг).
CSS_SOURCES = ("tailwind.config.js", "package.json", "package-lock.json", "static/src/")


@dataclasses.dataclass
class Plan:
    steps: list[str]
    pytest_targets: list[str]
    create_db: bool
    notes: list[str]


def _apps() -> set[str]:
    return {p.name for p in (ROOT / "apps").iterdir() if (p / "__init__.py").exists()}


def plan(files: list[str]) -> Plan:
    apps = _apps()
    steps = ["ruff_check", "ruff_format"]
    targets: set[str] = set()
    notes: list[str] = []
    create_db = False

    def step(name: str) -> None:
        if name not in steps:
            steps.append(name)

    for f in files:
        parts = f.split("/")
        is_html = f.endswith(".html")
        is_template = is_html and (parts[0] == "templates" or "/templates/" in f)
        in_code = parts[0] in ("apps", "templates", "config")

        if in_code and (f.endswith(".py") or is_html):
            step("i18n")
        if is_template or f.startswith(CSS_SOURCES):
            step("css")
        if is_template:
            targets.add(LOCKS["template_comments"])

        if parts[0] == "apps" and len(parts) > 2 and parts[1] in apps:
            targets.add(f"apps/{parts[1]}")
            if "migrations" in parts:
                create_db = True
        elif parts[0] == "templates":
            if len(parts) > 2 and parts[1] in apps:
                targets.add(f"apps/{parts[1]}")
            else:  # общие шаблоны (base, storefront, konto…) рендерят ядро и главная
                targets.update({"apps/core", "apps/tenants"})
        elif parts[0] == "config":
            targets.add("apps/core")
        elif parts[0] == "locale":
            notes.append("locale/: msgfmt --check-format и i18n_gap.py проверит только CI")
        elif f == "CLAUDE.md" or parts[0] == "docs":
            targets.add(LOCKS["claude_md"])
        elif f.startswith(".claude/rules/"):
            targets.add(LOCKS["rules"])
        elif f.startswith(".claude/skills/"):
            targets.add(LOCKS["skills"])
        elif f == "scripts/preflight.py":
            targets.add(LOCKS["preflight"])

    # Урок CI 1145: главная рендерит карточки через стабы контрактов ядра.
    if "apps/core" in targets:
        targets.add("apps/tenants")
    # Каталог приложения уже включает свои отдельные файлы.
    whole = {t for t in targets if t.count("/") == 1}
    targets = {t for t in targets if t in whole or not any(t.startswith(w + "/") for w in whole)}

    if targets:
        step("pytest")
    return Plan(steps, sorted(targets), create_db, sorted(set(notes)))


def pytest_command(p: Plan, jobs: int = 0) -> list[str]:
    cmd = ["uv", "run", "pytest", "-q", "-ra", *p.pytest_targets]
    cmd.append("--create-db" if p.create_db else "--reuse-db")
    cmd.append(f"--ignore={HANGING}")
    if jobs:
        cmd += ["-n", str(jobs), "--dist", "loadscope"]
    return cmd


def changed_files(base: str) -> list[str]:
    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        return [line for line in out.splitlines() if line]

    merge_base = git("merge-base", base, "HEAD")[0]
    files = git("diff", "--name-only", merge_base)
    files += git("ls-files", "--others", "--exclude-standard")
    return sorted(set(files))


def _run(cmd: list[str]) -> bool:
    print("    $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def _css() -> tuple[bool, str]:
    if not shutil.which("npm"):
        return False, "npm не найден — свежесть app.css не проверена"
    if not (ROOT / "node_modules" / ".bin" / "tailwindcss").exists() and not _run(["npm", "ci"]):
        return False, "npm ci не прошёл — свежесть app.css не проверена"
    if not _run(["npm", "run", "--silent", "build:css"]):
        return False, "npm run build:css упал"
    fresh = subprocess.run(
        ["git", "diff", "--quiet", "--", "static/css/app.css"], cwd=ROOT
    ).returncode
    if fresh != 0:
        return False, "static/css/app.css пересобран и отличается — закоммитьте его"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Финальный гейт перед пушем (T-13.1)")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--fast", action="store_true", help="без pytest")
    ap.add_argument("--plan", action="store_true", help="только показать набор проверок")
    ap.add_argument("--jobs", type=int, default=0, help="pytest -n N")
    args = ap.parse_args()

    files = changed_files(args.base)
    p = plan(files)
    print(f"preflight: {len(files)} изменённых путей относительно {args.base}")
    print("  шаги: " + ", ".join(p.steps))
    if p.pytest_targets:
        print(
            "  pytest: " + " ".join(p.pytest_targets) + ("  [--create-db]" if p.create_db else "")
        )
    if args.plan:
        return 0

    runners = {
        "ruff_check": lambda: (_run(["uv", "run", "ruff", "check", "."]), ""),
        "ruff_format": lambda: (_run(["uv", "run", "ruff", "format", "--check", "."]), ""),
        "i18n": lambda: (
            _run(["uv", "run", "python", "scripts/i18n_quickcheck.py"])
            and _run(["uv", "run", "python", "scripts/i18n_untranslated.py", "--check"]),
            "",
        ),
        "css": _css,
        "pytest": lambda: (_run(pytest_command(p, args.jobs)), ""),
    }
    results: list[tuple[str, str, str]] = []
    for name in p.steps:
        if name == "pytest" and args.fast:
            results.append((name, "–", "пропущен по --fast (не проверено)"))
            continue
        print(f"\n== {name}", flush=True)
        ok, why = runners[name]()
        results.append((name, "✓" if ok else "✗", why))

    print("\npreflight — итог:")
    for name, mark, why in results:
        print(f"  {mark} {name}" + (f" — {why}" if why else ""))
    for note in p.notes:
        print(f"  ! {note}")
    failed = [n for n, mark, _ in results if mark == "✗"]
    if failed:
        print("НЕ пушить: " + ", ".join(failed))
        return 1
    print("Чисто." if not args.fast else "Чисто без pytest — полный прогон перед пушем обязателен.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
