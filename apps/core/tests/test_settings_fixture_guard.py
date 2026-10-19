"""Замок класса: тест не сочетает декоратор `@override_settings` с фикстурой `settings`.

Фикстура pytest-django снимает снимок настроек в момент запроса — когда декоратор уже
активен — и при выходе возвращает этот снимок. Если декоратор подменял ROOT_URLCONF,
urlconf портала «прилипает» ко всем следующим тестам воркера: CI #2870 уронил
двадцать с лишним чужих тестов на NoReverseMatch. Нужна правка настроек в таком
тесте — `with override_settings(...)` целиком."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _offenders() -> list[str]:
    bad = []
    for path in (ROOT / "apps").rglob("test*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not any(arg.arg == "settings" for arg in node.args.args):
                continue
            for deco in node.decorator_list:
                fn = deco.func if isinstance(deco, ast.Call) else deco
                if (getattr(fn, "id", None) or getattr(fn, "attr", None)) == "override_settings":
                    bad.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    return bad


def test_no_override_settings_decorator_with_settings_fixture():
    assert _offenders() == []
