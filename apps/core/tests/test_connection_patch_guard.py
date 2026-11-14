"""Замок: тесты правят само соединение, а не прокси `django.db.connection`.

Правка прокси через `monkeypatch` запоминает прежнее значение по словарю прокси, где
его нет, и при откате (pytest ≥ 9.2) удаляет атрибут у настоящего соединения: следующие
тесты падают с «no attribute 'schema_name'» или теряют `connection.tenant`.
Править надо `connections["default"]`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_PROXY_PATCH = re.compile(r"monkeypatch\.(?:setattr|delattr)\(\s*(?:db\.)?connection\s*,")


def test_tests_do_not_monkeypatch_the_connection_proxy():
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in sorted((ROOT / "apps").rglob("test*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _PROXY_PATCH.search(line)
    ]
    assert not offenders, offenders
