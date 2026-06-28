"""Регресс-гард: многострочные `{# … #}` Django НЕ сворачивает как комментарий
(они однострочные) → текст течёт на страницу видимым мусором. Этот тест ловит такие
комментарии по всему `templates/`. Многострочные комментарии — только `{% comment %}`.
"""

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).resolve().parents[3] / "templates"


def _multiline_hash_comments(text: str) -> list[int]:
    bad = []
    for i, line in enumerate(text.split("\n"), start=1):
        idx = line.find("{#")
        if idx != -1 and "#}" not in line[idx:]:
            bad.append(i)
    return bad


def test_no_multiline_hash_comments_in_templates():
    offenders = {}
    for path in TEMPLATES_DIR.rglob("*.html"):
        lines = _multiline_hash_comments(path.read_text(encoding="utf-8"))
        if lines:
            offenders[str(path.relative_to(TEMPLATES_DIR))] = lines
    assert not offenders, (
        "Многострочные {# #} (Django не сворачивает → текст течёт на страницу). "
        f"Используйте {{% comment %}}: {offenders}"
    )
