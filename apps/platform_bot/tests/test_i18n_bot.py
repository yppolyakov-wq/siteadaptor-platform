"""T-8.10h H-6: каждая строка общего бота переведена на en/tr/ru/uk (бот говорит на языке
пользователя Telegram — пустой перевод = немецкий текст русскоязычному владельцу)."""

import ast
from pathlib import Path

import polib
import pytest

ROOT = Path(__file__).resolve().parents[3]
FILES = [
    *sorted((ROOT / "apps/platform_bot").glob("*.py")),
    ROOT / "apps/promotions/telegram_promo.py",
]


def _msgids():
    out = set()
    for path in FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                out.add(node.args[0].value)
    return out


@pytest.mark.parametrize("locale", ["en", "tr", "ru", "uk"])
def test_every_bot_string_is_translated(locale):
    po = polib.pofile(str(ROOT / f"locale/{locale}/LC_MESSAGES/django.po"))
    have = {e.msgid: e for e in po}
    missing = [
        m for m in _msgids() if m not in have or not (have[m].msgstr or have[m].msgstr_plural)
    ]
    assert not missing, missing[:5]
