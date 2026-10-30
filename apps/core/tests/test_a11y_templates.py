"""KA-12 E9.4b: доступность общих паттернов во ВСЕХ шаблонах (WCAG 2.2 AA).

План — `docs/ka-12-w5-e9-4-a11y-plan-2026-10-30.md`. Замки смотрят весь каталог шаблонов,
поэтому новый экран не может вернуть дефект: сообщение без объявления (4.1.3), кнопка-
иконка без имени (4.1.2), заголовок таблицы без `scope` (1.3.1).
"""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
TEMPLATES = sorted({*ROOT.glob("templates/**/*.html"), *ROOT.glob("apps/*/templates/**/*.html")})

MESSAGES_LOOP = re.compile(r"\{%\s*for\s+\w+\s+in\s+messages\s*%\}(.*?)\{%\s*endfor\s*%\}", re.S)
BUTTON = re.compile(r"<button\b([^>]*)>(.*?)</button>", re.S)
THEAD = re.compile(r"<thead\b.*?</thead>", re.S)
TEMPLATE_CODE = re.compile(r"<[^>]+>|\{%.*?%\}|\{\{.*?\}\}", re.S)


def _sources():
    for path in TEMPLATES:
        yield path.relative_to(ROOT), path.read_text(encoding="utf-8")


def test_flash_messages_are_announced():
    bad = []
    for rel, src in _sources():
        for loop in MESSAGES_LOOP.finditer(src):
            first = re.search(r"<[a-z]+\b[^>]*>", loop.group(1))
            if first and "role=" not in first.group(0):
                bad.append(str(rel))
    assert not bad, bad


def _icon_only(inner):
    if "{% trans" in inner or "{{" in inner or "{% firstof" in inner or "{% blocktrans" in inner:
        return False
    return not re.search(r"[A-Za-zÄÖÜäöüß0-9]", TEMPLATE_CODE.sub("", inner))


def test_icon_only_buttons_have_accessible_name():
    bad = []
    for rel, src in _sources():
        for m in BUTTON.finditer(src):
            attrs, inner = m.groups()
            if _icon_only(inner) and "aria-label" not in attrs and "aria-labelledby" not in attrs:
                bad.append(f"{rel}:{src[: m.start()].count(chr(10)) + 1} {inner.strip()[:20]!r}")
    assert not bad, bad


def test_table_headers_have_scope():
    bad = []
    for rel, src in _sources():
        for head in THEAD.finditer(src):
            if any("scope=" not in th for th in re.findall(r"<th(?=[\s>])[^>]*>", head.group(0))):
                bad.append(str(rel))
    assert not bad, sorted(set(bad))
