"""Статистика разработки (T-13.8): видно ли, что скиллы и гейт помогают.

    uv run python scripts/dev_stats.py                 # отчёт в терминал, с 2026-11-01
    uv run python scripts/dev_stats.py --since 2026-10-01
    uv run python scripts/dev_stats.py --write         # ещё и docs/dev-stats.md
    uv run python scripts/dev_stats.py --json <папка>  # наборы строк для страницы-панели
    uv run python scripts/dev_stats.py --snapshot "FB-33 стопка 7" --range origin/main..HEAD --red-ci 1
                                                       # строка в docs/dev-stats-history.md

Считает только то, что есть в репозитории (токены и время сессий сюда не попадают):
- коммиты по неделям и по шагам (префикс темы коммита) и долю «правок ревью» в них —
  главный индикатор: сколько работы уходит на исправление найденного после кода;
- находки журнала `docs/skill-feedback.md` по классам и по ответу «скилл покрывал?»;
- размер того, что грузится в каждую сессию и каждому субагенту (CLAUDE.md, правила),
  и размер проектных скиллов.

Разбор — чистые функции (`weekly`, `by_step`, `journal`), замок
`apps/core/tests/test_dev_stats.py`.
"""

import argparse
import collections
import datetime
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
# «ревью» — только отдельным словом: «превью» (срезы «Vorschau», страница 404) — не ревью.
REVIEW = re.compile(r"(?<![а-яё])ревью|находк", re.I)
# Записи о работе, а не работа: журнал, снимки, передача, документы, правка скиллов, ретро.
# Сверяется НАЧАЛО темы после «ID:» — в хвосте правки ревью часто стоит «…, строка журнала».
DOCS = re.compile(
    r"журнал находок|снимок статистик|передача стопки|доки\b|документы\b|скиллы sa-|ретро\b", re.I
)
# План и его ревью — до кода; этого мы и добивались, в переделку не входит.
PLAN = re.compile(r"(?:P0 — )?план\b|черновик плана|ревью плана", re.I)
# «FB-33 M3-7: …» → шаг «FB-33 M3-7»; «T-13.1: …» → «T-13.1»; «FB-33 стопка 5: …» → стыки стопки.
STEP = re.compile(r"^([A-Z][\w-]*(?:\.\w+)*(?: (?:стопка \d+|[A-Z0-9][\w-]*))?)(?=[:(\s—]|$)")
ANSWERS = ("нет правила", "правило неверное", "было, не сработало")
WHEN = ("план", "дифф", "после мержа")
HISTORY = ROOT / "docs" / "dev-stats-history.md"
HISTORY_HEAD = """# История снимков статистики разработки (T-13.8)

Строка на стопку или крупный мерж: `uv run python scripts/dev_stats.py --snapshot "<имя>"
--range origin/main..HEAD --red-ci N`. Судить по трём числам вместе (правила —
`docs/skill-feedback.md`): доля правок ревью ПОСЛЕ кода (цель < 20 %), находок `план` больше,
чем `дифф`, `после мержа` не растёт. «Ревью» — замки и правки по находкам после кода; план и
его ревью — отдельной колонкой, журнал и документы не считаются.

| Дата | Стопка | Коммитов | Ревью | Доля | Коммитов плана | Находки: план | дифф | после мержа | Красных CI |
|---|---|---|---|---|---|---|---|---|---|
"""


def kind(subject: str) -> str:
    """`docs` — записи о работе; `plan` — план и его ревью (до кода); `rework` — замок или
    правка по находке ПОСЛЕ кода; `work` — всё остальное. Порядок проверок важен: журнал
    «находок ревью плана» — это `docs`, а не `plan` и не `rework`."""
    prefix, _, head = subject.partition(":")
    head = head.strip() or subject
    if REVIEW.search(prefix):  # «FB-33 M5b-2 ревью: …» — правка по ревью, что бы ни шло дальше
        return "rework"
    if DOCS.match(head):
        return "docs"
    if PLAN.match(head):
        return "plan"
    return "rework" if REVIEW.search(subject) else "work"


def is_review(subject: str) -> bool:
    """Переделка после кода — то, долю чего мы хотим снизить."""
    return kind(subject) == "rework"


def step_of(subject: str) -> str:
    m = STEP.match(subject)
    # У ID задачи всегда есть цифра («FB-33», «T-13.1») — «Merge …» шагом не считаем.
    return m.group(1) if m and any(c.isdigit() for c in m.group(1)) else "прочее"


def weekly(commits: list[tuple[str, str]]) -> list[tuple[str, int, int]]:
    """[(дата ISO, тема)] → [(неделя «2026-W47», всего, из них ревью)] по возрастанию."""
    total: collections.Counter = collections.Counter()
    review: collections.Counter = collections.Counter()
    for day, subject in commits:
        year, week, _ = datetime.date.fromisoformat(day).isocalendar()
        key = f"{year}-W{week:02d}"
        total[key] += 1
        review[key] += is_review(subject)
    return [(k, total[k], review[k]) for k in sorted(total)]


def by_step(commits: list[tuple[str, str]], min_commits: int = 3) -> list[tuple[str, int, int]]:
    """Шаги от свежих к старым: (шаг, всего, из них ревью); мелкие шаги не показываем."""
    total: collections.Counter = collections.Counter()
    review: collections.Counter = collections.Counter()
    order: list[str] = []
    for _, subject in commits:
        key = step_of(subject)
        if key not in total:
            order.append(key)
        total[key] += 1
        review[key] += is_review(subject)
    return [(k, total[k], review[k]) for k in order if total[k] >= min_commits and k != "прочее"]


def journal(text: str) -> dict:
    """Строки раздела «Находки» → счётчики по классу, по скиллу и по ответу."""
    rows = text.split("## Находки")[1].strip().splitlines()[2:] if "## Находки" in text else []
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows if r.strip()]
    cells = [c for c in cells if len(c) == 9]
    return {
        "total": len(cells),
        "by_when": collections.Counter(c[2] for c in cells),
        "by_step": collections.Counter(c[1] for c in cells),
        "by_class": collections.Counter(c[4] for c in cells),
        "by_skill": collections.Counter(c[6] for c in cells),
        "by_answer": collections.Counter(c[7] for c in cells),
        "rows": cells,
    }


def snapshot_row(label: str, commits, found: dict, red_ci: str, today: str) -> str:
    """Строка истории: коммиты диапазона + находки журнала, у которых «Шаг» входит в `label`
    или наоборот (стопка «FB-33 стопка 7» собирает находки шагов, названных в журнале так же)."""
    total = len(commits)
    review = sum(is_review(s) for _, s in commits)
    steps = {step_of(s) for _, s in commits}
    mine = [r for r in found.get("rows", []) if r[1] in steps or r[1] in label or label in r[1]]
    when = collections.Counter(r[2] for r in mine)
    share = f"{round(100 * review / total)} %" if total else "—"
    plan = sum(kind(s) == "plan" for _, s in commits)
    cells = [today, label.replace("|", "/"), total, review, share, plan]
    cells += [when[w] for w in WHEN] + [red_ci]
    return "| " + " | ".join(str(c) for c in cells) + " |"


def history_rows(text: str) -> list[dict]:
    """Таблица `docs/dev-stats-history.md` строками — набор «по стопкам» страницы-панели."""

    def num(value: str):
        value = value.replace("%", "").strip()
        return int(value) if value.isdigit() else None

    rows = []
    for line in text.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) != 10 or not re.match(r"\d{4}-\d\d-\d\d$", c[0]):
            continue
        keys = ("commits", "review", "share", "plan_commits", "plan", "diff", "after", "red_ci")
        rows.append({"stack": c[1], "date": c[0], **dict(zip(keys, map(num, c[2:]), strict=True))})
    return rows


def map_rows() -> list[dict]:
    """Карта работ (`docs/fb33-map.md`) строками — что в main, что в работе, что можно брать."""
    path = ROOT / "docs" / "fb33-map.md"
    if not path.exists():
        return []
    rows, order = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|") or len(c) != 6 or c[0] in ("Стопка", ""):
            continue
        if set(c[0]) <= {"-", ":"}:
            continue
        order += 1
        keys = ("stack", "status", "depends", "slices", "what", "needs")
        rows.append(
            {"order": order, **dict(zip(keys, (x.replace("`", "") for x in c), strict=True))}
        )
    return rows


def sizes() -> list[tuple[str, int]]:
    rules = sum(p.stat().st_size for p in (ROOT / ".claude" / "rules").rglob("*") if p.is_file())
    skills = sorted((ROOT / ".claude" / "skills").glob("sa-*/SKILL.md"))
    return [
        ("CLAUDE.md (каждая сессия и агент)", (ROOT / "CLAUDE.md").stat().st_size),
        (".claude/rules/ (каждая сессия и агент)", rules),
        (
            f"проектные скиллы sa-* ({len(skills)} шт., по запросу)",
            sum(p.stat().st_size for p in skills),
        ),
    ]


def _commits(since: str, rev_range: str = "") -> list[tuple[str, str]]:
    scope = [rev_range] if rev_range else [f"--since={since}"]
    out = subprocess.run(
        ["git", "log", *scope, "--no-merges", "--date=short", "--pretty=%ad\t%s"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]


def shallow_note() -> str:
    """Облачная сессия клонирует только хвост истории — отчёт без оговорки врал бы о тренде."""
    out = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    if out != "true":
        return ""
    oldest = subprocess.run(
        ["git", "log", "--date=short", "--pretty=%ad", "--reverse"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split("\n", 1)[0]
    return (
        f"⚠️ История обрезана (самый старый коммит — {oldest}). Для полного тренда: "
        "`git fetch --shallow-since=2026-09-01 origin main`."
    )


def _bar(part: int, whole: int, width: int = 20) -> str:
    filled = round(width * part / whole) if whole else 0
    return "█" * filled + "░" * (width - filled)


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)} %" if whole else "—"


def report(since: str) -> str:
    commits = _commits(since)
    lines = [f"# Статистика разработки (с {since}, на {datetime.date.today().isoformat()})", ""]
    total = len(commits)
    review = sum(is_review(s) for _, s in commits)
    if shallow_note():
        lines += [shallow_note(), ""]
    plan = sum(kind(s) == "plan" for _, s in commits)
    lines += [
        f"**Индикатор: доля «правок ревью» — {_pct(review, total)}** ({review} из {total} коммитов).",
        "Ниже — лучше: меньше работы уходит на исправление найденного после кода.",
        f"Коммитов плана и его ревью (до кода, в долю не входят): {plan}.",
        "",
        "## По неделям",
        "",
        "| Неделя | Коммитов | Ревью | Доля | |",
        "|---|---|---|---|---|",
    ]
    for week, n, r in weekly(commits):
        lines.append(f"| {week} | {n} | {r} | {_pct(r, n)} | `{_bar(r, n)}` |")
    lines += [
        "",
        "## По шагам (свежие сверху)",
        "",
        "| Шаг | Коммитов | Ревью | Доля |",
        "|---|---|---|---|",
    ]
    for step, n, r in by_step(commits)[:25]:
        lines.append(f"| {step} | {n} | {r} | {_pct(r, n)} |")

    j = journal((ROOT / "docs" / "skill-feedback.md").read_text(encoding="utf-8"))
    lines += ["", f"## Журнал находок — {j['total']} строк", ""]
    if j["total"]:
        lines += ["| Когда найдено | Находок |", "|---|---|"]
        lines += [f"| {w} | {j['by_when'][w]} |" for w in WHEN]
        lines += ["", "| Скилл покрывал? | Находок |", "|---|---|"]
        lines += [f"| {a} | {j['by_answer'][a]} |" for a in ANSWERS]
        lines += ["", "| Класс | Находок |", "|---|---|"]
        lines += [f"| {k} | {n} |" for k, n in j["by_class"].most_common()]
        lines += ["", "| Скилл («—» — не был загружен) | Находок |", "|---|---|"]
        lines += [f"| {k} | {n} |" for k, n in j["by_skill"].most_common()]
    else:
        lines.append("Пока пусто: строки появляются с первой находкой ревью, CI или стенда.")

    lines += ["", "## Постоянно загружаемый контекст", "", "| Что | КБ |", "|---|---|"]
    lines += [f"| {name} | {size / 1000:.1f} |" for name, size in sizes()]
    lines += [
        "",
        "Чего здесь нет: токены и время сессий в репозиторий не пишутся — их показывает",
        "страница использования в приложении; красные прогоны CI — вкладка Actions.",
    ]
    return "\n".join(lines) + "\n"


def datasets(since: str) -> dict[str, list[dict]]:
    """Те же числа строками — для страницы-панели (каждый набор уходит в свой JSON-файл)."""
    commits = _commits(since)

    def rows(key: str, items) -> list[dict]:
        return [
            {key: name, "commits": n, "review": r, "share": round(100 * r / n) if n else 0}
            for name, n, r in items
        ]

    j = journal((ROOT / "docs" / "skill-feedback.md").read_text(encoding="utf-8"))
    found = [
        {"group": "Скилл покрывал?", "name": a, "findings": j["by_answer"][a]} for a in ANSWERS
    ]
    found += [{"group": "Класс", "name": k, "findings": n} for k, n in j["by_class"].most_common()]
    found += [{"group": "Скилл", "name": k, "findings": n} for k, n in j["by_skill"].most_common()]
    return {
        "steps": rows("step", by_step(commits)[:25]),
        "weeks": rows("week", weekly(commits)),
        "context": [{"what": name, "kb": round(size / 1000, 1)} for name, size in sizes()],
        "journal": found if j["total"] else [],
        "history": history_rows(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else [],
        "map": map_rows(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Статистика разработки (T-13.8)")
    ap.add_argument("--since", default="2026-11-01")
    ap.add_argument("--write", action="store_true", help="записать docs/dev-stats.md")
    ap.add_argument("--json", metavar="DIR", help="наборы строк для страницы-панели")
    ap.add_argument("--snapshot", metavar="ИМЯ", help="дописать строку в docs/dev-stats-history.md")
    ap.add_argument("--range", default="", help="диапазон git для снимка, напр. origin/main..HEAD")
    ap.add_argument("--red-ci", default="—", help="число красных прогонов CI за стопку")
    args = ap.parse_args()
    if args.json:
        out = pathlib.Path(args.json)
        out.mkdir(parents=True, exist_ok=True)
        for name, rows in datasets(args.since).items():
            (out / f"{name}.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
            )
    if args.snapshot:
        found = journal((ROOT / "docs" / "skill-feedback.md").read_text(encoding="utf-8"))
        row = snapshot_row(
            args.snapshot,
            _commits(args.since, args.range),
            found,
            args.red_ci,
            datetime.date.today().isoformat(),
        )
        text = HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else HISTORY_HEAD
        HISTORY.write_text(text.rstrip("\n") + "\n" + row + "\n", encoding="utf-8")
        print(row)
        return
    text = report(args.since)
    print(text)
    if args.write:
        (ROOT / "docs" / "dev-stats.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
