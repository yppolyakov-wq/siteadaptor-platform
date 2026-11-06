"""Каждый модуль, регистрирующий задачу ИИ, импортируется при старте (ready()).

Иначе задачи нет в реестре до первого импорта вьюхи: проверка `ai.W005` ругается на
деплое, а админка «KI-Einstellungen» и Celery-воркер её не знают (так было с
`search_query_expand`, T-8.34d).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_every_ai_task_module_is_imported_at_startup():
    missing = []
    for path in (ROOT / "apps").rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^registry\.register\(", text, re.M):
            continue
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        if module not in sys.modules:
            missing.append(module)
    assert not missing, f"не импортируются в ready(): {missing}"


def test_query_expand_task_is_known():
    from apps.ai.registry import TASKS

    assert "search_query_expand" in TASKS
