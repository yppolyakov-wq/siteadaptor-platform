"""Замок размера `.claude/rules/` (T-13.0, 2026-11-21).

Всё, что лежит в `.claude/rules/` без `paths:` во frontmatter, грузится в КАЖДУЮ сессию и
каждому субагенту — поверх `CLAUDE.md`. Копия общих правил ECC занимала 29 КБ, и большая её
часть была отменена в `project-overrides.md` (порог покрытия, conventional commits,
Repository-паттерн, FastAPI…). Тест не даёт каталогу снова обрасти.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
RULES = ROOT / ".claude" / "rules"
BUDGET_BYTES = 9_000


def test_rules_dir_stays_within_budget():
    files = sorted(p for p in RULES.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in files)
    listing = ", ".join(f"{p.relative_to(RULES)}={p.stat().st_size}" for p in files)
    assert size <= BUDGET_BYTES, (
        f".claude/rules/ = {size} байт при бюджете {BUDGET_BYTES} ({listing}). Правило грузится "
        "каждой сессии и каждому агенту: общее знание — в скилл (.claude/skills/), историю и "
        "обоснования — в docs/."
    )


def test_rules_dir_holds_only_rules():
    # README и LICENSE копии ECC тоже грузились как правила — их место в docs/ecc/.
    stray = [p.name for p in RULES.rglob("*") if p.is_file() and p.suffix != ".md"]
    assert not stray, f"в .claude/rules/ лежит не правило: {stray}"
    assert not (RULES / "ecc").exists(), "копия общих правил ECC снята (T-13.0) — см. docs/ecc/"
    assert (ROOT / "docs" / "ecc" / "LICENSE").exists(), "лицензия MIT копии ECC обязана остаться"
