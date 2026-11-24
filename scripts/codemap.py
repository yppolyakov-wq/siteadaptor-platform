"""Справка по коду (T-15): связи файла по запросу — вместо десятка поисков в начале среза.

    uv run python scripts/codemap.py apps/core/form_spec.py     # файл
    uv run python scripts/codemap.py apps.core.fsm              # модуль
    uv run python scripts/codemap.py form_spec                  # голое имя, если оно одно в apps/
    uv run python scripts/codemap.py apps/core/fsm.py::StateMachine   # имя в файле
    uv run python scripts/codemap.py --plan docs/<план>.md      # по таблице срезов плана стопки
    uv run python scripts/codemap.py --core-index               # пересобрать docs/codemap-core.md
    uv run python scripts/codemap.py --mutual                   # взаимные зависимости приложений

Отчёт: кто импортирует (по приложениям; `apps/`, `config/`, `scripts/`), кто называет модуль строкой
(таблицы «модуль → класс», settings, `include(...)`), какие шаблоны грузят его как `{% load %}`, что
импортирует сам, тесты и наборы эталонов, скиллы, строки памяти проекта (в т.ч. «единственный
писатель»), находки журнала, последние шаги в git, упоминания в передаче FB-33. Связи считаются из
кода в момент запроса (AST: импорты, включая ленивые внутри функций и относительные, и строковые
литералы с путём модуля) — справка не хранится и не устаревает.

Чего справка НЕ видит: миграции; `reverse()` по имени маршрута; сигналы и задачи Celery по имени;
`{% include %}` шаблонов; `getattr`. Пустой список импортёров — не «никто не зовёт».
Замок — `apps/core/tests/test_codemap.py`.
"""

import argparse
import ast
import collections
import functools
import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_INDEX = "docs/codemap-core.md"
MUTUAL_BASELINE = "docs/codemap-mutual-baseline.txt"
_ROOTS = ("apps", "config", "scripts")
_SKIP = ("/migrations/", "/node_modules/")
# Тесты самих инструментов упоминают слово «golden», но эталонов приложения не держат.
_TOOL_TESTS = (
    "test_preflight_plan.py",
    "test_codemap.py",
    "test_plan_check.py",
    "test_dev_stats.py",
)
# Имена, одинаковые во всех приложениях: по одному слову тесты и память не ищем — только с приложением.
_GENERIC = frozenset(
    "models views urls forms services tasks admin signals apps public_views state_machine "
    "__init__ factories serializers utils helpers constants".split()
)
_DOTTED = re.compile(r"^apps(?:\.\w+){1,6}$")
_STRINGS = "__strings__"
_BROKEN = "__broken__"
_META = (_STRINGS, _BROKEN)


def _is_test(path: str) -> bool:
    return "/tests/" in path or path.rsplit("/", 1)[-1].startswith("test_")


def _has_goldens(root: pathlib.Path, test: str) -> bool:
    if test.rsplit("/", 1)[-1] in _TOOL_TESTS:
        return False
    return "golden" in (root / test).read_text(encoding="utf-8")


@functools.cache
def _module_file(root: pathlib.Path, dotted: str) -> str | None:
    """`apps.core.fsm` → `apps/core/fsm.py` (или `…/__init__.py` пакета); нет такого — None."""
    base = dotted.replace(".", "/")
    for cand in (f"{base}.py", f"{base}/__init__.py"):
        if (root / cand).is_file():
            return cand
    return None


def _string_target(root: pathlib.Path, value: str) -> str | None:
    """`"apps.orders.state_machine.OrderSM"` → файл модуля: хвост отбрасывается, пока путь не найдётся."""
    if not _DOTTED.match(value):
        return None
    parts = value.split(".")
    while (
        len(parts) >= 3
    ):  # apps.<приложение>.<модуль>: само приложение строкой — не связь с файлом
        found = _module_file(root, ".".join(parts))
        if found and not found.endswith("/__init__.py"):
            return found
        parts.pop()
    return None


def _scan(root: pathlib.Path, path: str, tree: ast.AST) -> tuple[set[str], set[str]]:
    """(импортирует, называет строкой)."""
    imports: set[str] = set()
    strings: set[str] = set()
    package = path.rsplit("/", 1)[0].replace("/", ".")

    def add(dotted: str, names=()):
        hit = False
        for name in names:  # `from apps.core import fsm` — имя может быть модулем
            sub = _module_file(root, f"{dotted}.{name}")
            if sub:
                imports.add(sub)
                hit = True
        if not hit or not names:
            target = _module_file(root, dotted)
            if target:
                imports.add(target)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apps"):
                    add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # относительный: `from . import models`, `from ..core import fsm`
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                dotted = f"{base}.{node.module}" if node.module else base
            else:
                dotted = node.module or ""
            if dotted.startswith("apps"):
                add(dotted, [a.name for a in node.names])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            target = _string_target(root, node.value)
            if target:
                strings.add(target)
    imports.discard(path)
    strings -= imports | {path}
    return imports, strings


def build_index(root: pathlib.Path = ROOT) -> dict:
    """Файл → файлы, которые он импортирует. Служебные ключи: `__strings__` (файл → названные строкой),
    `__broken__` (не разобранные — о них справка обязана сказать)."""
    index: dict = {_STRINGS: {}, _BROKEN: set()}
    for top in _ROOTS:
        for file in sorted((root / top).rglob("*.py")) if (root / top).is_dir() else []:
            path = file.relative_to(root).as_posix()
            if any(skip in f"/{path}" for skip in _SKIP):
                continue
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                index[_BROKEN].add(path)
                continue
            index[path], strings = _scan(root, path, tree)
            if strings:
                index[_STRINGS][path] = strings
    return index


def importers(index: dict, path: str, tests: bool = False) -> list[str]:
    return sorted(
        f for f, deps in index.items() if f not in _META and path in deps and _is_test(f) == tests
    )


def string_refs(index: dict, path: str) -> list[str]:
    """Кто называет модуль строкой (таблицы «модуль → класс», settings, include) — без import."""
    return sorted(f for f, deps in index[_STRINGS].items() if path in deps and not _is_test(f))


def imports_of(index: dict, path: str) -> list[str]:
    return sorted(index.get(path, ()))


def broken_note(index: dict) -> str:
    bad = sorted(index[_BROKEN])
    return (
        ("⚠️ не разобраны (синтаксис), их связи в ответ не вошли: " + ", ".join(bad)) if bad else ""
    )


def _app(path: str) -> str:
    parts = path.split("/")
    return parts[1] if parts[0] == "apps" and len(parts) > 2 else parts[0]


def mutual_pairs(index: dict) -> list[tuple[str, str]]:
    """Пары приложений, импортирующих друг друга (тесты, `config/` и `scripts/` не считаются;
    ленивые импорты внутри функций считаются — связь та же)."""
    edges = {
        (_app(f), _app(d))
        for f, deps in index.items()
        if f not in _META and f.startswith("apps/") and not _is_test(f)
        for d in deps
        if d.startswith("apps/") and _app(f) != _app(d)
    }
    return sorted({tuple(sorted(e)) for e in edges if (e[1], e[0]) in edges})


def candidates(root: pathlib.Path, name: str) -> list[str]:
    """Файлы `apps/**/<name>.py` — когда голое имя встречается не в одном месте."""
    if not re.fullmatch(r"\w+", name):
        return []
    out = []
    for p in (root / "apps").rglob(f"{name}.py"):
        path = p.relative_to(root).as_posix()
        if not any(skip in f"/{path}" for skip in _SKIP) and "/tests/" not in path:
            out.append(path)
    return sorted(out)


def resolve(root: pathlib.Path, target: str) -> tuple[str, str] | None:
    """Запрос → (файл, имя). Понимает путь, `a.b.c`, `путь::имя`, голое имя модуля, если оно одно."""
    target, _, name = target.partition("::")
    target = target.strip().rstrip("/")
    for cand in (target, _module_file(root, target) or ""):
        if cand and (root / cand).is_file():
            return cand, name.strip()
    found = candidates(root, target)
    return (found[0], name.strip()) if len(found) == 1 else None


def _grep(root: pathlib.Path, needle: str, *paths: str, word: bool = False) -> list[str]:
    cmd = ["git", "grep", "-l", "-F"] + (["-w"] if word else []) + [needle, "--", *paths]
    out = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
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


def _names(path: str) -> tuple[str, str, tuple[str, ...]]:
    """(слово для тестов, игла для скиллов, иглы для документов). У общих имён — с приложением."""
    stem = path.rsplit("/", 1)[-1][:-3]
    dotted = path[:-3].replace("/", ".")
    if stem == "__init__":
        stem = path.split("/")[-2]
        dotted = dotted[: -len(".__init__")]
    if stem in _GENERIC:
        qualified = ".".join(dotted.split(".")[-2:])  # orders.models
        return "", path, (path, qualified, dotted)
    return stem, f"{stem}.py", (f"{stem}.py", f"`{stem}.", dotted)


def _template_loads(root: pathlib.Path, path: str) -> list[str]:
    if "/templatetags/" not in path or path.endswith("__init__.py"):
        return []
    lib = path.rsplit("/", 1)[-1][:-3]
    out = subprocess.run(
        ["git", "grep", "-l", "-E", rf"\{{% load [^%]*\b{lib}\b", "--", "*.html"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _list(files: list[str], limit: int = 25) -> list[str]:
    extra = [f"- … ещё {len(files) - limit}"] if len(files) > limit else []
    return [f"- {f}" for f in files[:limit]] + extra


def _tests_of(root: pathlib.Path, index: dict, path: str) -> tuple[set[str], str]:
    word = _names(path)[0]
    tests = set(importers(index, path, tests=True))
    if word:
        tests |= set(_grep(root, word, "apps/*/tests/*.py", word=True))
        return tests, f"импортируют файл или называют `{word}`"
    return tests, "импортируют файл (имя общее — по слову не ищем)"


def report(root: pathlib.Path, target: str, index: dict | None = None) -> str:
    found = resolve(root, target)
    if not found:
        many = candidates(root, target.partition("::")[0].strip())
        if len(many) > 1:
            return (
                f"«{target}» не найден однозначно — уточни путь:\n"
                + "\n".join(_list(many, 40))
                + "\n"
            )
        return (
            f"«{target}» не найден: нужен путь (apps/core/fsm.py), модуль (apps.core.fsm), "
            "имя модуля (fsm) или путь::имя\n"
        )
    path, name = found
    index = index or build_index(root)
    _, skill_needle, needles = _names(path)
    who = importers(index, path)
    lines = [f"# {path}" + (f" :: {name}" if name else "")]
    if broken_note(index):
        lines.append(broken_note(index))
    if name:
        source = (root / path).read_text(encoding="utf-8")
        if not re.search(
            rf"^\s*(?:async def |def |class )?{re.escape(name)}\b\s*[(=:]", source, re.M
        ):
            lines.append(
                f"\n⚠️ имени `{name}` нет в файле {path} (ни def, ни class, ни присваивания)"
            )
        else:
            users = _grep(root, name, *who, word=True) if who else []
            lines.append(
                f"\nИмя `{name}` встречается в {len(users)} из {len(who)} импортёров: "
                + ", ".join(users[:12])
            )

    lines.append(f"\n## Кто импортирует — {len(who)} файлов, приложения: {_by_app(who) or 'никто'}")
    lines += _list(who)
    by_string = string_refs(index, path)
    lines.append(f"\n## Кто называет строкой (таблицы, settings, include) — {len(by_string)}")
    lines += _list(by_string, 12)
    loads = _template_loads(root, path)
    if loads:
        lines.append(f"\n## Шаблоны с {{% load {path.rsplit('/', 1)[-1][:-3]} %}} — {len(loads)}")
        lines += _list(loads, 8)
    if not who and not by_string and not loads:
        lines.append(
            "Пусто — это не «никто не зовёт»: проверь reverse(), сигналы, задачи Celery, {% include %}."
        )
    deps = imports_of(index, path)
    lines.append(f"\n## Что импортирует сам — {len(deps)}")
    lines.append(", ".join(deps) or "ничего из apps/")

    mentions, basis = _tests_of(root, index, path)
    goldens = sorted(t for t in mentions if _has_goldens(root, t))
    lines.append(f"\n## Тесты — {len(mentions)} файлов {basis}, из них с эталонами {len(goldens)}")
    lines += _list(sorted(mentions), 15)
    if goldens:
        lines.append("Эталоны: " + ", ".join(goldens[:8]))
    lines.append("Тесты, которые проверяют модуль через вьюху, не называя его, сюда не попадают.")

    skills = sorted(
        p.split("/")[2] for p in _grep(root, skill_needle, ".claude/skills/sa-*/SKILL.md")
    )
    lines.append(
        "\n## Скилл — " + (", ".join(skills) or "ни один проектный скилл файл не называет")
    )

    n, sample = _lines(root, "docs/project-memory.md", needles, 6)
    lines.append(f"\n## Память проекта — {n} строк (docs/project-memory.md)")
    if any("ЕДИНСТВЕНН" in s.upper() and "ПИСАТЕЛ" in s.upper() for s in sample):
        lines.append("Единственный писатель (по памяти проекта, не из кода) — первыми строками:")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/pitfalls.md", needles, 3)
    lines.append(f"\n## Грабли — {n} строк (docs/pitfalls.md)")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/skill-feedback.md", needles, 4)
    lines.append(f"\n## Находки журнала — {n}")
    lines += [f"- {s}" for s in sample]
    n, sample = _lines(root, "docs/fb33-handoff-2026-11-24.md", needles[:1], 4)
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
    lines.append(
        "\nНе видно справке: миграции; reverse() по имени маршрута; сигналы и задачи Celery по имени; "
        "{% include %} шаблонов; getattr."
    )
    return "\n".join(lines) + "\n"


def core_index(root: pathlib.Path, index: dict) -> str:
    """Оглавление ядра: модуль — назначение (первая строка описания) — кто зовёт."""
    rows = []
    core = root / "apps" / "core"
    for file in sorted(core.rglob("*.py")):
        path = file.relative_to(root).as_posix()
        if file.name == "__init__.py" or _is_test(path) or any(s in f"/{path}" for s in _SKIP):
            continue
        try:
            doc = ast.get_docstring(ast.parse(file.read_text(encoding="utf-8"))) or ""
            purpose = (doc.strip().splitlines() or ["— описания нет"])[0]
        except (SyntaxError, UnicodeDecodeError):
            purpose = "⚠️ файл не разобран (синтаксис)"
        who = importers(index, path)
        apps = sorted({_app(f) for f in who} - {"core"})
        rel = file.relative_to(core).as_posix()
        purpose = purpose.replace("|", "/")[:150]
        rows.append(f"| `{rel}` | {purpose} | {len(who)} | {len(apps)} | {', '.join(apps[:6])} |")
    head = [
        "# Оглавление ядра `apps/core` — что уже есть (T-15.3)",
        "",
        "Собирается командой `uv run python scripts/codemap.py --core-index`; руками не править.",
        "Нужен, чтобы найти готовый модуль, а не завести второй. Назначение — первая строка описания",
        "модуля; подробности и «единственные писатели» — `docs/project-memory.md` §3. Связи одного файла —",
        "`uv run python scripts/codemap.py <файл>`. Числа обновляются при пересборке; замок сверяет только",
        "то, что каждый модуль ядра здесь есть (`apps/core/tests/test_codemap.py`). Команды управления и",
        "шаблонные теги зовутся по имени, а не импортом — нули в их строках не значат «не используется».",
        "",
        "| Модуль | Назначение | Файлов-импортёров | Приложений | Кто зовёт (до шести) |",
        "|---|---|---|---|---|",
    ]
    return "\n".join(head + rows) + "\n"


def plan_report(root: pathlib.Path, plan: str, index: dict) -> str:
    plan_path = pathlib.Path(plan)
    if not plan_path.is_file():
        return f"плана «{plan}» нет (путь — от текущего каталога)"
    spec = importlib.util.spec_from_file_location("plan_check", root / "scripts" / "plan_check.py")
    plan_check = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("plan_check", plan_check)
    spec.loader.exec_module(plan_check)
    slices = plan_check.parse(plan_path.read_text(encoding="utf-8"))
    if not slices:
        return "в плане нет таблицы срезов (docs/stack-plan-template.md)"
    out = [
        "| Срез | Файл | Импортёров | Приложения | Строкой | Тестов | С эталонами |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in slices:
        for f in s.own:
            if not (root / f.path).is_file():
                kind = "новый" if f.new else "нет файла или шаблон имени"
                out.append(f"| {s.name} | {f.path} | — | {kind} | — | — | — |")
                continue
            who = importers(index, f.path)
            tests, _ = _tests_of(root, index, f.path)
            goldens = [t for t in tests if _has_goldens(root, t)]
            out.append(
                f"| {s.name} | {f.path} | {len(who)} | {_by_app(who) or '—'} | "
                f"{len(string_refs(index, f.path))} | {len(tests)} | {len(goldens)} |"
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
    note = broken_note(index)
    if args.core_index:
        (ROOT / CORE_INDEX).write_text(core_index(ROOT, index), encoding="utf-8")
        print(f"{CORE_INDEX}: пересобран")
    elif args.mutual:
        for a, b in mutual_pairs(index):
            print(a, b)
    elif args.plan:
        print(plan_report(ROOT, args.plan, index))
    elif args.target:
        text = report(ROOT, args.target, index)
        print(text)
        return 1 if "не найден" in text.splitlines()[0] else 0
    else:
        ap.print_help()
        return 1
    if note:  # в любом режиме: связи битого файла в ответ не вошли
        print(note, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
