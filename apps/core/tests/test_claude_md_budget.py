"""Замок размера `CLAUDE.md` (T-12, 2026-11-13).

Файл грузится целиком в каждую сессию и каждому субагенту. За полгода он вырос до 618 КБ:
в §3 дописывали хронологию, которой место в `docs/build-log.md`. Тест не даёт этому
повториться — история идёт в журнал, решения и единые модули в `docs/project-memory.md`,
грабли в `docs/pitfalls.md`.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
BUDGET_BYTES = 45_000


def test_claude_md_stays_within_budget():
    size = (ROOT / "CLAUDE.md").stat().st_size
    assert size <= BUDGET_BYTES, (
        f"CLAUDE.md = {size} байт при бюджете {BUDGET_BYTES}. Хронологию перенесите в "
        "docs/build-log.md, решения владельца и единые модули — в docs/project-memory.md, "
        "грабли — в docs/pitfalls.md; в §3 остаются две-три строки «сейчас»."
    )


def test_claude_md_points_to_memory_docs():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for doc in ("build-log.md", "project-memory.md", "pitfalls.md", "task-catalog.md"):
        assert doc in text, f"CLAUDE.md потерял ссылку на docs/{doc}"
        assert (ROOT / "docs" / doc).exists(), f"docs/{doc} не существует"
