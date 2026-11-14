"""Замок: тесты правят само соединение, а не прокси `django.db.connection`.

Правка прокси через `monkeypatch` запоминает прежнее значение по словарю прокси, где
его нет, и при откате (pytest ≥ 9.2) удаляет атрибут у настоящего соединения: следующие
тесты падают с «no attribute 'schema_name'» или теряют `connection.tenant`.
Править надо `connections["default"]`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_PROXY_PATCH = re.compile(
    r"(?:monkeypatch\.(?:setattr|delattr)|patch\.object)\(\s*(?:db\.)?connection\s*,"
)


def test_tests_do_not_monkeypatch_the_connection_proxy():
    files = [*(ROOT / "apps").rglob("test*.py"), *(ROOT / "apps").rglob("conftest.py")]
    offenders = []
    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        # по всему тексту: вызов может быть разбит на строки
        for found in _PROXY_PATCH.finditer(text):
            line = text.count("\n", 0, found.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, offenders
