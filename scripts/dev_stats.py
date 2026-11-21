"""Статистика разработки (T-13.8): видно ли, что скиллы и гейт помогают.

    uv run python scripts/dev_stats.py                 # отчёт в терминал, с 2026-11-01
    uv run python scripts/dev_stats.py --since 2026-10-01
    uv run python scripts/dev_stats.py --write         # ещё и docs/dev-stats.md

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
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVIEW = re.compile(r"ревью|находк", re.I)
# «FB-33 M3-7: …» → шаг «FB-33 M3-7»; «T-13.1: …» → «T-13.1»; «FB-33 стопка 5: …» → стыки стопки.
STEP = re.compile(r"^([A-Z][\w-]*(?:\.\w+)*(?: (?:стопка \d+|[A-Z0-9][\w-]*))?)(?=[:(\s—]|$)")
ANSWERS = ("нет правила", "правило неверное", "было, не сработало")


def is_review(subject: str) -> bool:
    return bool(REVIEW.search(subject))


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
    cells = [c for c in cells if len(c) == 8]
    return {
        "total": len(cells),
        "by_class": collections.Counter(c[3] for c in cells),
        "by_skill": collections.Counter(c[5] for c in cells),
        "by_answer": collections.Counter(c[6] for c in cells),
    }


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


def _commits(since: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", f"--since={since}", "--no-merges", "--date=short", "--pretty=%ad\t%s"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]


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
    lines += [
        f"**Индикатор: доля «правок ревью» — {_pct(review, total)}** ({review} из {total} коммитов).",
        "Ниже — лучше: меньше работы уходит на исправление найденного после кода.",
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
        lines += ["| Скилл покрывал? | Находок |", "|---|---|"]
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Статистика разработки (T-13.8)")
    ap.add_argument("--since", default="2026-11-01")
    ap.add_argument("--write", action="store_true", help="записать docs/dev-stats.md")
    args = ap.parse_args()
    text = report(args.since)
    print(text)
    if args.write:
        (ROOT / "docs" / "dev-stats.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
