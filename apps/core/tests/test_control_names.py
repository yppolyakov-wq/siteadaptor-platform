"""KA-12 E9.4d: у каждого поля формы кабинета есть доступное имя.

Имя даёт: обёртка <label>, label for=id, aria-label/aria-labelledby или title.
Placeholder именем НЕ считается (исчезает при вводе, скринридеры читают его не всегда).

Замок-храповик: число безымянных полей в шаблоне может только УМЕНЬШАТЬСЯ;
новый шаблон обязан быть чистым. Исправили файл — уменьшите число в BASELINE.
"""

import re
from pathlib import Path

from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"
SKIP = ("storefront/", "aggregator/", "email", "pdf/", "public/", "platform/", "account/")
_CONTROL = re.compile(r"<(input|select|textarea)\b[^>]*>")
_NAMED = re.compile(r'aria-label(ledby)?=|\bid="|\btitle="')
_NO_NAME_NEEDED = re.compile(r'type="(hidden|submit|checkbox|radio|button|image|reset)"')
# Невидимое: honeypot (class hidden / aria-hidden), инпуты, собираемые строкой в JS.
_INVISIBLE = re.compile(r'class="(?:[^"]*\s)?hidden(?:\s[^"]*)?"|aria-hidden="true"|\' \+')

# После E9.4d (2026-10-31) безымянных полей в кабинете нет. Исключение — только
# осознанно и с причиной (храповик: число может лишь уменьшаться).
BASELINE: dict[str, int] = {}


_COMMENTS = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}|//[^\n]*", re.S)


def _blank(m):
    return re.sub(r"[^\n]", " ", m.group(0))


def unnamed_controls(text):
    text = _COMMENTS.sub(_blank, text)  # теги в комментариях — не разметка
    out = []
    for m in _CONTROL.finditer(text):
        tag = m.group(0)
        if _NO_NAME_NEEDED.search(tag) or _NAMED.search(tag) or _INVISIBLE.search(tag):
            continue
        before = text[max(0, m.start() - 1500) : m.start()]
        if before.rfind("<label") > before.rfind("</label>"):
            continue  # внутри <label>
        out.append((text.count("\n", 0, m.start()) + 1, tag[:100]))
    return out


def test_cabinet_controls_have_accessible_names():
    grown = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel.startswith(SKIP):
            continue
        found = unnamed_controls(path.read_text())
        if len(found) > BASELINE.get(rel, 0):
            grown.append((rel, len(found), BASELINE.get(rel, 0), found[:3]))
    assert not grown, grown


def test_baseline_is_tight():
    """Храповик не гниёт: исправленный файл обязан уменьшить своё число."""
    loose = []
    for rel, allowed in BASELINE.items():
        path = TEMPLATES / rel
        n = len(unnamed_controls(path.read_text())) if path.exists() else 0
        if n < allowed:
            loose.append((rel, n, allowed))
    assert not loose, loose


def test_scanner_sees_unnamed_and_named():
    assert unnamed_controls('<input name="a" placeholder="x">')
    assert not unnamed_controls('<label>A <input name="a"></label>')
    assert not unnamed_controls('<input name="a" aria-label="A">')
    assert not unnamed_controls('<input type="hidden" name="a">')
    assert not unnamed_controls('<input name="website" class="hidden" tabindex="-1">')
    assert unnamed_controls('<input name="a" class="hidden-ish w-1">')
    assert not unnamed_controls("{% comment %}<select>{% endcomment %}// <select> x")
