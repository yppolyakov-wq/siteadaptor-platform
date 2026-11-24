"""Проверяемый план стопки (T-14.2 / T-14.3): таблицу срезов читает программа, а не только люди.

    uv run python scripts/plan_check.py docs/<план>.md              # ДО кода
    uv run python scripts/plan_check.py docs/<план>.md --verify --base <коммит P0>   # ПОСЛЕ кода

В плане — одна таблица (образец `docs/stack-plan-template.md`):

    | Срез | Зависит от | Свои файлы | Общие файлы | Эталоны | Ветка |

- «Свои файлы» — в бэктиках через запятую: `путь`, `путь:10-20,40-55` (строки — когда параллельные
  срезы делят файл по кускам), `шаблон/_bw_*.html`, `+новый/файл.py` (файла ещё нет).
- «Общие файлы» — правит только координатор на верхушке (`static/css/app.css`, общие эталоны, `.po`).
- «Эталоны» — прогноз: сколько файлов эталонов изменит срез (число; «?» — прогноза нет, это находка).
- «Ветка» — ветка или коммит среза, нужна для `--verify`.

До кода (`check`): зависимости существуют и без циклов; срезы, которые могут идти параллельно, не
делят файл или его строки; файл координатора не записан срезу; каждый названный файл существует —
иначе это «предпосылка без проверки по коду». После кода (`verify`): что срез тронул сверх заявленного
и сколько эталонов изменилось против прогноза. Свои тесты (`*/tests/test_*.py`) срез пишет без записи.
Замок — `apps/core/tests/test_plan_check.py`.
"""

import argparse
import dataclasses
import fnmatch
import glob
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_EMPTY = ("", "—", "-")


@dataclasses.dataclass
class File:
    path: str
    ranges: list[tuple[int, int]]
    new: bool = False

    def matches(self, path: str) -> bool:
        return fnmatch.fnmatch(path, self.path)


@dataclasses.dataclass
class Slice:
    name: str
    deps: list[str]
    own: list[File]
    shared: list[File]
    goldens: int | None
    branch: str
    own_text: str = ""  # ячейка как написана: текст без бэктиков — не «нет файлов», а ошибка записи


def _files(cell: str) -> list[File]:
    out = []
    for token in re.findall(r"`([^`]+)`", cell):
        new = token.startswith("+")
        path, _, tail = token.lstrip("+").partition(":")
        ranges = [(int(a), int(b or a)) for a, b in re.findall(r"(\d+)(?:-(\d+))?", tail)]
        out.append(File(path.strip(), ranges, new))
    return out


def parse(text: str) -> list[Slice]:
    """Первая таблица с шапкой «| Срез | Зависит от | Свои файлы | …» → срезы."""
    slices, inside = [], False
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|"):
            if inside:
                break
            continue
        if cells[:3] == ["Срез", "Зависит от", "Свои файлы"]:
            inside = True
            continue
        if not inside or len(cells) != 6 or set(cells[0]) <= {"-", ":"}:
            continue
        deps = [d.strip() for d in cells[1].split(",") if d.strip() not in _EMPTY]
        goldens = int(cells[4]) if cells[4].isdigit() else None
        slices.append(
            Slice(cells[0], deps, _files(cells[2]), _files(cells[3]), goldens, cells[5], cells[2])
        )
    return slices


def table_errors(text: str) -> list[str]:
    """Строки таблицы срезов, которые `parse` не смог прочитать: молча терять срез нельзя."""
    out, state = [], "before"  # before → inside → after
    for n, line in enumerate(text.splitlines(), 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        is_row = line.lstrip().startswith("|")
        if state == "before":
            if is_row and cells[:3] == ["Срез", "Зависит от", "Свои файлы"]:
                state = "inside"
            continue
        if state == "inside":
            if not is_row:
                state = "after"
            elif len(cells) != 6 and not set(cells[0]) <= {"-", ":"}:
                out.append(
                    f"строка {n} (срез «{cells[0]}»): {len(cells)} колонок вместо 6 — лишняя «|» в ячейке или пропущена колонка"
                )
            continue
        # после таблицы: строка, похожая на срез (6 колонок, в 3-й бэктики или прочерк), — разрыв
        if (
            is_row
            and len(cells) == 6
            and cells[0] not in ("Срез",)
            and not set(cells[0]) <= {"-", ":"}
        ):
            if "`" in cells[2] or cells[1] in _EMPTY:
                out.append(
                    f"строка {n}: срез «{cells[0]}» после разрыва таблицы — пустая строка внутри таблицы теряет срезы"
                )
    return out


def _ancestors(slices: list[Slice]) -> dict[str, set[str]]:
    deps = {s.name: s.deps for s in slices}
    out: dict[str, set[str]] = {}

    def walk(name: str, seen: frozenset) -> set[str]:
        if name in out:
            return out[name]
        acc: set[str] = set()
        for d in deps.get(name, []):
            if d in seen:  # цикл — сообщит check()
                continue
            acc |= {d} | walk(d, seen | {name})
        out[name] = acc
        return acc

    for s in slices:
        walk(s.name, frozenset())
    return out


def _cycle(slices: list[Slice]) -> list[str]:
    deps = {s.name: s.deps for s in slices}
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> list[str]:
        if state.get(node) == 1:
            return path[path.index(node) :] + [node]
        if state.get(node) == 2 or node not in deps:
            return []
        state[node] = 1
        for nxt in deps[node]:
            found = visit(nxt, path + [node])
            if found:
                return found
        state[node] = 2
        return []

    for s in slices:
        found = visit(s.name, [])
        if found:
            return found
    return []


def _inside(directory: str, path: str) -> bool:
    return directory.endswith("/") and path.startswith(directory)


def _overlap(a: File, b: File) -> bool:
    if _inside(a.path, b.path) or _inside(b.path, a.path):
        return True  # каталог целиком и файл внутри него
    if not (a.matches(b.path) or b.matches(a.path)):
        return False
    if not a.ranges or not b.ranges:
        return True
    return any(x1 <= y2 and y1 <= x2 for x1, x2 in a.ranges for y1, y2 in b.ranges)


def on_disk(path: str) -> bool:
    return bool(glob.glob(str(ROOT / path)))


def check(slices: list[Slice], exists=on_disk) -> list[str]:
    """Что в плане не сходится ДО кода. Пустой список — срезы можно раздавать."""
    out = []
    names = [s.name for s in slices]
    if len(set(names)) != len(names):
        out.append("срез записан дважды")
    for s in slices:
        out += [
            f"{s.name}: зависит от «{d}», такого среза в плане нет"
            for d in s.deps
            if d not in names
        ]
    loop = _cycle(slices)
    if loop:
        out.append("цикл зависимостей: " + " → ".join(loop))
    up = _ancestors(slices)
    for i, a in enumerate(slices):
        for b in slices[i + 1 :]:
            if a.name in up.get(b.name, ()) or b.name in up.get(a.name, ()):
                continue  # идут по очереди — тот же файл не конфликт
            hits = sorted({fa.path for fa in a.own for fb in b.own if _overlap(fa, fb)})
            if hits:
                out.append(
                    f"{a.name} и {b.name} могут идти параллельно и делят {', '.join(hits)} — "
                    "развести по строкам, поставить зависимость или отдать координатору"
                )
    reserved = [(f, s.name) for s in slices for f in s.shared]
    for s in slices:
        if not s.own:
            if s.own_text.strip() in _EMPTY:
                out.append(
                    f"{s.name}: не названо ни одного файла — пересечения и сверку проверить нечем"
                )
            else:
                out.append(
                    f"{s.name}: файлы записаны без бэктиков («{s.own_text[:40]}») — программа их не видит"
                )
        for f in s.own:
            if any(r.matches(f.path) or f.matches(r.path) for r, _ in reserved):
                out.append(
                    f"{s.name}: {f.path} — общий файл, его правит только координатор на верхушке"
                )
            if not f.new and not exists(f.path):
                out.append(
                    f"{s.name}: {f.path} — такого файла нет (предпосылка без проверки по коду; новый файл — с «+»)"
                )
        if s.goldens is None:
            out.append(
                f"{s.name}: нет прогноза эталонов — число изменяемых файлов эталонов (0, если не задевает)"
            )
    return out


def waves(slices: list[Slice]) -> list[list[str]]:
    """Волны: срезы одной волны можно вести параллельно, следующая ждёт предыдущую."""
    done: set[str] = set()
    left = list(slices)
    out = []
    while left:
        wave = [s for s in left if all(d in done for d in s.deps)]
        if (
            not wave
        ):  # цикл или неизвестная зависимость — остаток одной волной, причину даёт check()
            wave = left
        out.append([s.name for s in wave])
        done |= {s.name for s in wave}
        left = [s for s in left if s.name not in done]
    return out


def _own_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/tests/" in path and name.startswith("test_") and name.endswith(".py")


def verify(slices: list[Slice], touched: dict[str, list[str]]) -> list[str]:
    """Что срез тронул сверх заявленного и где прогноз эталонов не сошёлся (ПОСЛЕ кода)."""
    out = []
    reserved = [f for s in slices for f in s.shared]
    for s in slices:
        files = touched.get(s.name)
        if files is None:
            continue
        if not files:
            # Пустая разница — не «всё по плану»: ветка равна базе или уже влита, сверять нечего.
            out.append(f"{s.name}: ветка не отличается от базы — сверка не выполнена")
            continue
        if s.goldens is None:
            out.append(f"{s.name}: нет прогноза эталонов — сверить число изменённых не с чем")
        goldens = [f for f in files if "golden" in f.split("/")[-2:][0] or "/golden" in f]
        for f in files:
            if f in goldens or _own_test(f):
                continue
            if any(r.matches(f) for r in reserved) and not any(o.matches(f) for o in s.shared):
                out.append(f"{s.name}: тронул общий файл {f} — его правит только координатор")
            elif not any(o.matches(f) for o in s.own + s.shared):
                out.append(f"{s.name}: тронул {f} вне плана — дописать в план или вернуть")
        if s.goldens is not None and len(goldens) != s.goldens:
            out.append(
                f"{s.name}: изменено файлов эталонов {len(goldens)}, прогноз {s.goldens} — "
                "сверить список изменившихся случаев с ожидаемым"
            )
    return out


def _touched(base: str, ref: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{ref}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверяемый план стопки (T-14.2 / T-14.3)")
    ap.add_argument("plan")
    ap.add_argument("--verify", action="store_true", help="сверить факт с планом (после кода)")
    ap.add_argument("--base", default="origin/main", help="коммит P0 или база стопки для --verify")
    args = ap.parse_args()
    text = pathlib.Path(args.plan).read_text(encoding="utf-8")
    slices = parse(text)
    broken = table_errors(text)
    if not slices:
        print(
            "✗ в плане нет таблицы «| Срез | Зависит от | Свои файлы | Общие файлы | Эталоны | Ветка |»"
        )
        return 1
    found = broken + check(slices)
    for n, wave in enumerate(waves(slices), 1):
        print(f"волна {n}: " + ", ".join(wave))
    if args.verify:
        touched, skipped = {}, []
        for s in slices:
            if not s.branch:
                skipped.append(s.name)
                continue
            touched[s.name] = _touched(args.base, s.branch)
        found += verify(slices, touched)
        if skipped:
            # Срез без ветки сверить нечем — это не «чисто», а «не проверено».
            found.append("нет ветки для сверки (не проверено): " + ", ".join(skipped))
    for p in found:
        print("✗ " + p)
    if not found:
        print(f"план в порядке: {len(slices)} срезов")
    else:
        print(
            "каждое расхождение после кода — строка в docs/skill-feedback.md (класс «предпосылка-без-grep»)"
        )
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
