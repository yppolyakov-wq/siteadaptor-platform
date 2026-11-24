"""Карта работ (T-14.1): порядок, статус и зависимости стопок — в одной таблице, которую читает программа.

    uv run python scripts/work_map.py            # проверить карту и показать, что можно брать
    uv run python scripts/work_map.py --graph    # пересобрать граф зависимостей в файле карты
    uv run python scripts/work_map.py --set 13 "в работе"   # сменить статус стопки (и граф)

Карта — `docs/fb33-map.md` (другая — через `--file`). Строка таблицы:

    | Стопка | Статус | Зависит от | Срезы | Что | До кода нужно |

Статусы: `в main` · `в работе` · `дальше` · `ждёт решения` · `отменено`. Порядок строк — предлагаемый
порядок работ. Разбор и проверки — чистые функции (`parse`, `problems`, `ready`, `mermaid`), замок
`apps/core/tests/test_work_map.py`. Порядок и статус стопок записываются ТОЛЬКО здесь: передачи и
планы ссылаются на карту, а не повторяют её.
"""

import argparse
import dataclasses
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAP = ROOT / "docs" / "fb33-map.md"
STATUSES = ("в main", "в работе", "дальше", "ждёт решения", "отменено")
DONE, ACTIVE, NEXT = "в main", "в работе", "дальше"
GRAPH_BEGIN, GRAPH_END = "<!-- граф: начало -->", "<!-- граф: конец -->"
_EMPTY = ("", "—", "-")


@dataclasses.dataclass
class Row:
    stack: str
    status: str
    deps: list[str]
    slices: list[str]
    what: str
    needs: str


def _list(cell: str) -> list[str]:
    return [x.strip().strip("`") for x in cell.split(",") if x.strip() not in _EMPTY]


def parse(text: str) -> list[Row]:
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|") or len(cells) != 6:
            continue
        if cells[0] in ("Стопка", "") or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(Row(cells[0], cells[1], _list(cells[2]), _list(cells[3]), cells[4], cells[5]))
    return rows


def table_errors(text: str) -> list[str]:
    """Строки таблицы карты, которые `parse` не прочитал: стопку нельзя потерять молча."""
    out, inside = [], False
    for n, line in enumerate(text.splitlines(), 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|"):
            inside = False
            continue
        if cells[:2] == ["Стопка", "Статус"]:
            inside = True
            continue
        if inside and len(cells) != 6 and not set(cells[0]) <= {"-", ":"}:
            out.append(
                f"строка {n} (стопка «{cells[0]}»): {len(cells)} колонок вместо 6 — лишняя «|» в ячейке или пропущена колонка"
            )
    return out


def _cycle(rows: list[Row]) -> list[str]:
    deps = {r.stack: r.deps for r in rows}
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

    for r in rows:
        found = visit(r.stack, [])
        if found:
            return found
    return []


def problems(rows: list[Row], catalog: str) -> list[str]:
    """Что в карте не так. Пустой список — карте можно верить."""
    out = []
    if not rows:
        return ["карта пуста: таблица «| Стопка | Статус | … |» не найдена или в ней нет строк"]
    by = {r.stack: r for r in rows}
    if len(by) != len(rows):
        out.append("стопка записана дважды")
    for r in rows:
        if r.status not in STATUSES:
            out.append(
                f"стопка {r.stack}: статус «{r.status}» — нужен один из {', '.join(STATUSES)}"
            )
        for d in r.deps:
            if d not in by:
                out.append(f"стопка {r.stack}: зависит от «{d}», такой стопки в карте нет")
    loop = _cycle(rows)
    if loop:
        out.append("цикл зависимостей: " + " → ".join(loop))
    active = [r.stack for r in rows if r.status == ACTIVE]
    if len(active) > 1:
        out.append(f"в работе сразу {', '.join(active)} — закрой одну (scripts/stack_close.py)")
    for r in rows:
        if r.status not in (ACTIVE, DONE):
            continue
        late = [d for d in r.deps if d in by and by[d].status != DONE]
        if late:
            out.append(
                f"стопка {r.stack} «{r.status}», а её зависимости {', '.join(late)} ещё не в main"
            )
        if r.status == ACTIVE:
            for s in r.slices:
                # ID целиком: «D1» не засчитывается по «D1.1», «D10» или «MD1».
                if not re.search(rf"(?<![\w.-]){re.escape(s)}(?![\w-]|\.\d)", catalog):
                    out.append(
                        f"стопка {r.stack}: срез {s} не заведён в docs/task-catalog.md (ID берётся до плана)"
                    )
    return out


def ready(rows: list[Row]) -> list[Row]:
    """Что можно брать: статус «дальше» и все зависимости в main. Порядок — как в карте."""
    by = {r.stack: r for r in rows}
    return [
        r
        for r in rows
        if r.status == NEXT and all(d in by and by[d].status == DONE for d in r.deps)
    ]


def _node(stack: str) -> str:
    # Имя узла Mermaid — только ASCII: «стенды» → s_u441_u442…
    return "s" + "".join(c if c.isascii() and c.isalnum() else f"_u{ord(c):x}" for c in stack)


def mermaid(rows: list[Row]) -> str:
    """Граф зависимостей: GitHub рисует блок Mermaid прямо в файле карты."""
    marks = {DONE: "✅", ACTIVE: "🚧", NEXT: "⏳", "ждёт решения": "❓", "отменено": "✖"}
    lines = ["```mermaid", "flowchart LR"]
    for r in rows:
        label = f"{marks.get(r.status, '')} {r.stack} · {r.what}".replace('"', "'").replace("`", "")
        lines.append(f'  {_node(r.stack)}["{label}"]')
    for r in rows:
        lines += [f"  {_node(d)} --> {_node(r.stack)}" for d in r.deps]
    return "\n".join(lines + ["```"])


def with_graph(text: str, rows: list[Row]) -> str:
    """Текст карты со свежим графом между метками."""
    block = f"{GRAPH_BEGIN}\n{mermaid(rows)}\n{GRAPH_END}"
    if GRAPH_BEGIN in text and GRAPH_END in text:
        head, rest = text.split(GRAPH_BEGIN, 1)
        return head + block + rest.split(GRAPH_END, 1)[1]
    return text.rstrip("\n") + "\n\n" + block + "\n"


def set_status(text: str, stack: str, status: str) -> str:
    out, hit, inside = [], False, False
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        is_row = line.lstrip().startswith("|")
        if not is_row:
            inside = False  # другие таблицы файла не трогаем
        elif cells[:2] == ["Стопка", "Статус"]:
            inside = True
        if inside and is_row and not hit and len(cells) == 6 and cells[0] == stack:
            cells[1], hit = status, True
            line = "| " + " | ".join(cells) + " |"
        out.append(line)
    if not hit:
        raise SystemExit(f"стопки «{stack}» в карте нет")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Карта работ (T-14.1)")
    ap.add_argument("--file", default=str(MAP))
    ap.add_argument("--graph", action="store_true", help="пересобрать граф в файле карты")
    ap.add_argument("--set", nargs=2, metavar=("СТОПКА", "СТАТУС"), help="сменить статус стопки")
    args = ap.parse_args()
    path = pathlib.Path(args.file)
    text = path.read_text(encoding="utf-8")
    if args.set:
        if args.set[1] not in STATUSES:
            raise SystemExit(f"статус — один из: {', '.join(STATUSES)}")
        text = set_status(text, *args.set)
    rows = parse(text)
    catalog = (ROOT / "docs" / "task-catalog.md").read_text(encoding="utf-8")
    found = table_errors(text) + problems(rows, catalog)
    if args.set and found:
        # Смена статуса, после которой карта неверна (вторая стопка в работе, срез без ID), не пишется.
        print(f"статус стопки {args.set[0]} НЕ изменён:")
    elif args.set or args.graph:
        path.write_text(with_graph(text, rows), encoding="utf-8")
    for r in rows:
        if r.status == ACTIVE:
            print(f"в работе: стопка {r.stack} — {r.what}")
    for r in ready(rows):
        print(
            f"можно брать: стопка {r.stack} — {r.what}"
            + (f" (до кода: {r.needs})" if r.needs not in _EMPTY else "")
        )
    for p in found:
        print("✗ " + p)
    if not found:
        print(f"карта в порядке: {len(rows)} строк")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
