"""Замок проектных скиллов `.claude/skills/sa-*` (T-13.2 / T-13.7, 2026-11-21).

Скилл — выжимка «что звать и чего не делать» по теме; он грузится вместо чтения сотен строк
`docs/project-memory.md` и `docs/pitfalls.md`. Устаревший скилл хуже отсутствующего: он уверенно
ведёт в снятый модуль. Поэтому каждый путь и каждое `файл.py::имя`, названные в скилле,
обязаны существовать, а сам скилл — оставаться коротким (новое правило вытесняет старое).
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SKILLS = sorted((ROOT / ".claude" / "skills").glob("sa-*/SKILL.md"))
MAX_LINES = 200
SECTIONS = ("## Когда грузить", "## Единые точки", "## Нельзя", "## Грабли", "## Что гейтить")

_PATH = re.compile(
    r"`((?:apps|scripts|docs|templates|static|config|\.claude|\.githooks)/[\w./-]+\.\w+)"
    r"(?:::([\w,\s]+))?`"
)
# Короткая запись `модуль.py::имя` — модуль ядра (`apps/core/`).
_CORE = re.compile(r"`(\w+\.py)::([\w,\s]+)`")


def _id(path: pathlib.Path) -> str:
    return path.parent.name


def test_first_project_skills_exist():
    names = {_id(p) for p in SKILLS}
    assert {"sa-increment", "sa-block-editor"} <= names, names


@pytest.mark.parametrize("skill", SKILLS, ids=_id)
def test_skill_has_frontmatter_sections_and_stays_short(skill):
    text = skill.read_text(encoding="utf-8")
    head = text.split("---")[1] if text.startswith("---") else ""
    assert f"name: {_id(skill)}" in head, "frontmatter: name должен совпадать с каталогом"
    assert re.search(r"^description: .{60,}", head, re.M), (
        "description — по нему скилл выбирается: что внутри и когда грузить"
    )
    for section in SECTIONS:
        assert section in text, f"нет раздела «{section}»"
    lines = text.count("\n") + 1
    assert lines <= MAX_LINES, (
        f"{lines} строк при потолке {MAX_LINES}: новое правило вытесняет наименее полезное, "
        "история и обоснования остаются в docs/"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=_id)
def test_every_path_and_name_in_skill_exists(skill):
    text = skill.read_text(encoding="utf-8")
    found = _PATH.findall(text) + [(f"apps/core/{m}", n) for m, n in _CORE.findall(text)]
    assert found, "скилл не называет ни одного файла — он не про код проекта"
    missing = []
    for path, names in found:
        target = ROOT / path
        if not target.exists():
            missing.append(path)
            continue
        if names:
            source = target.read_text(encoding="utf-8")
            for name in (n.strip() for n in names.split(",")):
                if not re.search(rf"^\s*(?:def |class )?{re.escape(name)}\b\s*[(=:]", source, re.M):
                    missing.append(f"{path}::{name}")
    assert not missing, f"скилл ссылается на несуществующее: {missing}"


def test_the_lock_itself_sees_a_missing_name(tmp_path):
    # Замок, который ничего не ловит, хуже отсутствующего: проверяем оба вида записи.
    text = "`apps/core/fsm.py::apply,\n  no_such_name_zz` и `fsm.py::no_such_short_zz`"
    found = _PATH.findall(text) + [(f"apps/core/{m}", n) for m, n in _CORE.findall(text)]
    names = {n.strip() for _, group in found for n in group.split(",")}
    assert {"apply", "no_such_name_zz", "no_such_short_zz"} <= names


def test_feedback_journal_rows_are_classified():
    journal = (ROOT / "docs" / "skill-feedback.md").read_text(encoding="utf-8")
    rows = journal.split("## Находки")[1].strip().splitlines()[2:]
    allowed = ("нет правила", "правило неверное", "было, не сработало")
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 8, f"строка журнала не из 8 колонок: {row[:80]}"
        assert cells[6] in allowed, f"«Скилл покрывал?» — одно из {allowed}: {row[:80]}"
        assert cells[7], f"не записано, что сделано: {row[:80]}"
