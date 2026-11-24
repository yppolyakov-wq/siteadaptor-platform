"""Справка по коду (T-15): связи файла по запросу — вместо десятка поисков в начале среза.

    uv run python scripts/codemap.py apps/core/form_spec.py     # файл
    uv run python scripts/codemap.py apps.core.fsm              # модуль
    uv run python scripts/codemap.py form_spec                  # голое имя — модуль ядра
    uv run python scripts/codemap.py apps/core/fsm.py::StateMachine   # имя в файле
    uv run python scripts/codemap.py --plan docs/<план>.md      # по таблице срезов плана стопки
    uv run python scripts/codemap.py --core-index               # пересобрать docs/codemap-core.md
    uv run python scripts/codemap.py --mutual                   # взаимные зависимости приложений

Отчёт: кто импортирует (по приложениям), что импортирует сам, тесты и наборы эталонов, скиллы,
строки памяти проекта (в т.ч. «единственный писатель»), находки журнала, последние шаги в git,
упоминания в передаче FB-33. Связи считаются из кода в момент запроса (AST импортов, включая ленивые
внутри функций и относительные) — справка не хранится и не устаревает.

Чего справка НЕ видит: вызовы по строке (`import_string`, `reverse`, имена задач Celery, сигналы),
шаблоны `{% include %}`, обращения через `getattr`. Пустой список импортёров — не «никто не зовёт».
Замок — `apps/core/tests/test_codemap.py`.
"""

import argparse
import ast
import collections
import functools
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_INDEX = "docs/codemap-core.md"
MUTUAL_BASELINE = "docs/codemap-mutual-baseline.txt"
_SKIP = ("/migrations/", "/node_modules/")
# Тесты самих инструментов упоминают слово «golden», но эталонов приложения не держат.
_TOOL_TESTS = (
    "test_preflight_plan.py",
    "test_codemap.py",
    "test_plan_check.py",
    "test_dev_stats.py",
)


def _has_goldens(root: pathlib.Path, test: str) -> bool:
    if test.rsplit("/", 1)[-1] in _TOOL_TESTS:
        return False
    return "golden" in (root / test).read_text(encoding="utf-8")


def _is_test(path: str) -> bool:
    return "/tests/" in path or path.rsplit("/", 1)[-1].startswith("test_")


@functools.cache
def _module_file(root: pathlib.Path, dotted: str) -> str | None:
    """`apps.core.fsm` → `apps/core/fsm.py` (или `…/__init__.py` пакета); нет такого — None."""
    base = dotted.replace(".", "/")
    for cand in (f"{base}.py", f"{base}/__init__.py"):
        if (root / cand).is_file():
            return cand
    return None


def _imports(root: pathlib.Path, path: str, tree: ast.AST) -> set[str]:
    out: set[str] = set()
    package = path.rsplit("/", 1)[0].replace("/", ".")

    def add(dotted: str, names=()):
        hit = False
        for name in names:  # `from apps.core import fsm` — имя может быть модулем
            sub = _module_file(root, f"{dotted}.{name}")
            if sub:
                out.add(sub)
                hit = True
        if not hit or not names:
            target = _module_file(root, dotted)
            if target:
                out.add(target)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apps"):
                    add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # относительный: `from . import models`, `from .models import X`
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                dotted = f"{base}.{node.module}" if node.module else base
            else:
                dotted = node.module or ""
            if dotted.startswith("apps"):
                add(dotted, [a.name for a in node.names])
    out.discard(path)
    return out


def build_index(root: pathlib.Path = ROOT) -> dict[str, set[str]]:
    """Файл → файлы, которые он импортирует. Битый файл не роняет индекс, но попадает в `__broken__`."""
    index: dict[str, set[str]] = {}
    broken: set[str] = set()
    for file in sorted((root / "apps").rglob("*.py")):
        path = file.relative_to(root).as_posix()
        if any(skip in f"/{path}" for skip in _SKIP):
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            broken.add(path)
            continue
        index[path] = _imports(root, path, tree)
    index["__broken__"] = broken
    return index


def importers(index: dict[str, set[str]], path: str, tests: bool = False) -> list[str]:
    return sorted(
        f
        for f, deps in index.items()
        if f != "__broken__" and path in deps and _is_test(f) == tests
    )


def imports_of(index: dict[str, set[str]], path: str) -> list[str]:
    return sorted(index.get(path, ()))


def _app(path: str) -> str:
    return path.split("/")[1]


def mutual_pairs(index: dict[str, set[str]]) -> list[tuple[str, str]]:
    """Пары приложений, импортирующих друг друга (тесты не считаются)."""
    edges = {
        (_app(f), _app(d))
        for f, deps in index.items()
        if f != "__broken__" and not _is_test(f)
        for d in deps
        if _app(f) != _app(d)
    }
    return sorted({tuple(sorted(e)) for e in edges if (e[1], e[0]) in edges})


def resolve(root: pathlib.Path, target: str) -> tuple[str, str] | None:
    """Запрос → (файл, имя). Понимает путь, `a.b.c`, `путь::имя`, голое имя модуля ядра."""
    target, _, name = target.partition("::")
    target = target.strip()
    candidates = [target, _module_file(root, target) or "", f"apps/core/{target}.py"]
    for cand in candidates:
        if cand and (root / cand).is_file():
            return cand, name.strip()
    return None


def _grep(root: pathlib.Path, needle: str, *paths: str) -> list[str]:
    out = subprocess.run(
        ["git", "grep", "-l", "-F", needle, "--", *paths], cwd=root, capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line]


def _lines(
    root: pathlib.Path, doc: str, needles: tuple[str, ...], limit: int
) -> tuple[int, list[str]]:
    path = root / doc
    if not path.is_file():
        return 0, []
    hits = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if any(n in line for n in needles)
    ]
    # Строки про единственного писателя — первыми: ради них справку чаще всего и открывают.
    hits.sort(key=lambda h: not ("ЕДИНСТВЕНН" in h.upper() and "ПИСАТЕЛ" in h.upper()))
    return len(hits), [h[:230] for h in hits[:limit]]


def _by_app(files: list[str]) -> str:
    groups: dict[str, int] = collections.Counter(_app(f) for f in files)
    return ", ".join(f"{app} ({n})" for app, n in sorted(groups.items(), key=lambda kv: -kv[1]))


def report(root: pathlib.Path, target: str, index: dict[str, set[str]] | None = None) -> str:
    found = resolve(root, target)
    if not found:
        return (
            f"«{target}» не найден: нужен путь (apps/core/fsm.py), модуль (apps.core.fsm), "
            "имя модуля ядра (fsm) или путь::имя"
        )
    path, name = found
    index = index or build_index(root)
    stem = path.rsplit("/", 1)[-1][:-3]
    dotted = path[:-3].replace("/", ".")
    who = importers(index, path)
    test_importers = importers(index, path, tests=True)
    lines = [f"# {path}" + (f" :: {name}" if name else "")]
    if name:
        users = _grep(root, name, *who, path) if who else []
        lines.append(
            f"\nИмя `{name}` встречается в {len(users)} из {len(who)} импортёров: "
            + ", ".join(users[:12])
        )
    lines.append(f"\n## Кто импортирует — {len(who)} файлов, приложения: {_by_app(who) or 'никто'}")
    lines += [f"- {f}" for f in who[:25]] + ([f"- … ещё {len(who) - 25}"] if len(who) > 25 else [])
    deps = imports_of(index, path)
    lines.append(f"\n## Что импортирует сам — {len(deps)}")
    lines.append(", ".join(deps) or "ничего из apps/")

    mentions = set(_grep(root, stem, "apps/*/tests/*.py")) | set(test_importers)
    goldens = sorted(
        t for t in mentions if "golden" in pathlib.Path(root / t).read_text(encoding="utf-8")
    )
    lines.append(
        f"\n## Тесты — {len(mentions)} файлов упоминают `{stem}`, из них с эталонами {len(goldens)}"
    )
    lines += [f"- {t}" for t in sorted(mentions)[:15]]
    if len(mentions) > 15:
        lines.append(f"- … ещё {len(mentions) - 15}")
    if goldens:
        lines.append("Эталоны: " + ", ".join(goldens[:8]))

    skills = sorted(
        p.split("/")[2] for p in _grep(root, f"{stem}.py", ".claude/skills/sa-*/SKILL.md")
    )
    lines.append(
        "\n## Скилл — " + (", ".join(skills) or "ни один проектный скилл файл не называет")
    )

    needles = (f"{stem}.py", f"`{stem}.", f"{dotted}")
    n, sample = _lines(root, "docs/project-memory.md", needles, 6)
    writers = [s for s in sample if "ЕДИНСТВЕНН" in s.upper() and "ПИСАТЕЛ" in s.upper()]
    lines.append(f"\n## Память проекта — {n} строк (docs/project-memory.md)")
    if writers:
        lines.append("Единственный писатель (по памяти проекта, не из кода):")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/pitfalls.md", needles, 3)
    lines.append(f"\n## Грабли — {n} строк (docs/pitfalls.md)")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/skill-feedback.md", needles, 4)
    lines.append(f"\n## Находки журнала — {n}")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/fb33-handoff-2026-11-24.md", (f"{stem}.py",), 4)
    lines.append(f"\n## Передача FB-33 (известные ошибки, будущие стопки) — {n} строк")
    lines += [f"- {s}" for s in sample]

    log = subprocess.run(
        ["git", "log", "-6", "--date=short", "--pretty=%ad %s", "--", path],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    lines.append("\n## Последние правки")
    lines += [f"- {entry[:120]}" for entry in log] or [
        "- истории нет (новый файл или обрезанный клон)"
    ]
    if index.get("__broken__"):
        lines.append("\n⚠️ не разобраны (синтаксис): " + ", ".join(sorted(index["__broken__"])))
    lines.append(
        "\nНе видно справке: вызовы по строке (reverse, import_string, задачи Celery, сигналы), "
        "{% include %} шаблонов, getattr."
    )
    return "\n".join(lines) + "\n"


def core_index(root: pathlib.Path, index: dict[str, set[str]]) -> str:
    """Оглавление ядра: модуль — назначение (первая строка описания) — кто зовёт."""
    rows = []
    for file in sorted((root / "apps" / "core").glob("*.py")):
        if file.name == "__init__.py":
            continue
        path = file.relative_to(root).as_posix()
        try:
            doc = ast.get_docstring(ast.parse(file.read_text(encoding="utf-8"))) or ""
        except SyntaxError:
            doc = ""
        purpose = (doc.strip().splitlines() or ["— описания нет"])[0].replace("|", "/")[:150]
        who = importers(index, path)
        apps = sorted({_app(f) for f in who} - {"core"})
        rows.append(
            f"| `{file.name}` | {purpose} | {len(who)} | {len(apps)} | {', '.join(apps[:6])} |"
        )
    head = [
        "# Оглавление ядра `apps/core` — что уже есть (T-15.3)",
        "",
        "Собирается командой `uv run python scripts/codemap.py --core-index`; руками не править.",
        "Нужен, чтобы найти готовый модуль, а не завести второй. Назначение — первая строка описания",
        "модуля; подробности и «единственные писатели» — `docs/project-memory.md` §3. Связи одного файла —",
        "`uv run python scripts/codemap.py <файл>`. Числа обновляются при пересборке; замок сверяет только",
        "то, что каждый модуль ядра здесь есть (`apps/core/tests/test_codemap.py`).",
        "",
        "| Модуль | Назначение | Файлов-импортёров | Приложений | Кто зовёт (до шести) |",
        "|---|---|---|---|---|",
    ]
    return "\n".join(head + rows) + "\n"


def plan_report(root: pathlib.Path, plan: str, index: dict[str, set[str]]) -> str:
    spec = importlib.util.spec_from_file_location("plan_check", root / "scripts" / "plan_check.py")
    plan_check = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("plan_check", plan_check)
    spec.loader.exec_module(plan_check)
    slices = plan_check.parse(pathlib.Path(plan).read_text(encoding="utf-8"))
    if not slices:
        return "в плане нет таблицы срезов (docs/stack-plan-template.md)"
    out = [
        "| Срез | Файл | Импортёров | Приложения | Тестов | С эталонами |",
        "|---|---|---|---|---|---|",
    ]
    for s in slices:
        for f in s.own:
            if not (root / f.path).is_file():
                out.append(
                    f"| {s.name} | {f.path} | — | {'новый' if f.new else 'нет файла или шаблон'} | — | — |"
                )
                continue
            who = importers(index, f.path)
            stem = f.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            tests = _grep(root, stem, "apps/*/tests/*.py")
            goldens = [t for t in tests if _has_goldens(root, t)]
            out.append(
                f"| {s.name} | {f.path} | {len(who)} | {_by_app(who) or '—'} | {len(tests)} | {len(goldens)} |"
            )
    out.append(
        "\nЧисло наборов эталонов — верхняя оценка для колонки «Эталоны» плана: сверить прогоном."
    )
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Справка по коду (T-15)")
    ap.add_argument("target", nargs="?")
    ap.add_argument("--plan", help="план стопки с таблицей срезов")
    ap.add_argument("--core-index", action="store_true", help=f"пересобрать {CORE_INDEX}")
    ap.add_argument("--mutual", action="store_true", help="взаимные зависимости приложений")
    args = ap.parse_args()
    index = build_index(ROOT)
    if args.core_index:
        (ROOT / CORE_INDEX).write_text(core_index(ROOT, index), encoding="utf-8")
        print(f"{CORE_INDEX}: пересобран")
        return 0
    if args.mutual:
        for a, b in mutual_pairs(index):
            print(a, b)
        return 0
    if args.plan:
        print(plan_report(ROOT, args.plan, index))
        return 0
    if not args.target:
        ap.print_help()
        return 1
    text = report(ROOT, args.target, index)
    print(text)
    return 1 if "не найден" in text.splitlines()[0] else 0


if __name__ == "__main__":
    sys.exit(main())
