"""KA-0 (2026-10-23): наследование шаблонов не ломается молча.

Экран «Aktionstypen» падал 500 у всех бизнесов: шаблон наследовал
`core/_base_dashboard.html`, которого нет (база кабинета — `tenant/…`), а его
содержимое лежало в блоке `content`, которого у базы нет, — даже с верной базой
страница была бы пустой. Тесты вызывали только помощник данных. Ловим класс
целиком, статически по всем шаблонам:

1. каждый `{% extends "…" %}` указывает на существующий шаблон;
2. каждый блок верхнего уровня дочернего шаблона есть в цепочке родителей —
   иначе его содержимое Django молча выбрасывает.
"""

import re
from pathlib import Path

from django.template.loader import get_template

ROOT = Path(__file__).resolve().parents[3] / "templates"
EXTENDS = re.compile(r"{%\s*extends\s+[\"']([^\"']+)[\"']\s*%}")
BLOCK = re.compile(r"{%\s*block\s+(\w+)\s*%}")
COMMENTS = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.S)


def _code(src):
    """Шаблон без комментариев — упоминание блока в комментарии не блок."""
    return COMMENTS.sub("", src)


def _templates():
    return sorted(ROOT.rglob("*.html")) + sorted(ROOT.rglob("*.txt"))


def _source(name):
    return _code(Path(get_template(name).origin.name).read_text(encoding="utf-8"))


def _chain_blocks(name, seen=None):
    """Имена блоков шаблона и его предков; None — в цепочке нелитеральный extends
    (`{% extends base_template|default:… %}`): родителя статически не узнать."""
    seen = seen or set()
    if name in seen:
        return set()
    seen.add(name)
    src = _source(name)
    names = set(BLOCK.findall(src))
    if re.search(r"{%\s*extends\s+[^\"'\s]", src):
        return None
    for parent in EXTENDS.findall(src)[:1]:
        upper = _chain_blocks(parent, seen)
        if upper is None:
            return None
        names |= upper
    return names


def _top_level_blocks(src):
    """Блоки верхнего уровня (не вложенные в другие блоки)."""
    depth, out = 0, []
    for m in re.finditer(r"{%\s*(?:block\s+(\w+)|endblock\b)[^%]*%}", src):
        if m.group(1):
            if depth == 0:
                out.append(m.group(1))
            depth += 1
        else:
            depth -= 1
    return out


def test_every_literal_extends_target_exists():
    missing = []
    for path in _templates():
        for target in EXTENDS.findall(path.read_text(encoding="utf-8")):
            try:
                get_template(target)
            except Exception:  # noqa: BLE001 — любой провал загрузки = дефект
                missing.append(f"{path.relative_to(ROOT)} → {target}")
    assert not missing, "extends на несуществующий шаблон:\n" + "\n".join(missing)


def test_child_blocks_exist_in_parent_chain():
    lost = []
    for path in _templates():
        src = _code(path.read_text(encoding="utf-8"))
        parents = EXTENDS.findall(src)
        if not parents:
            continue
        try:
            available = _chain_blocks(parents[0])
        except Exception:  # noqa: BLE001 — несуществующую базу ловит тест выше
            continue
        if available is None:
            continue
        for name in _top_level_blocks(src):
            if name not in available:
                lost.append(f"{path.relative_to(ROOT)}: block {name} (нет в {parents[0]})")
    assert not lost, "блок не выводится родителем — содержимое пропадёт:\n" + "\n".join(lost)
