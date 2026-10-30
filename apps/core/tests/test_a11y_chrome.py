"""KA-12 E9.4a: доступность хрома кабинета (WCAG 2.2 AA).

План — `docs/ka-12-w5-e9-4-a11y-plan-2026-10-30.md`. Поведение (фокус, Esc, стрелки,
ловушка Tab) проверяет Playwright-стенд; здесь — разметка, от которой оно зависит.
"""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR) / "templates" / "tenant"
BASE = (ROOT / "_base_dashboard.html").read_text(encoding="utf-8")
PALETTE = (ROOT / "_nav_palette.html").read_text(encoding="utf-8")


def _tag(src, element_id):
    m = re.search(r"<[a-z]+\b[^>]*\bid=\"" + element_id + r"\"[^>]*>", src, re.S)
    assert m, element_id
    return m.group(0)


def test_skip_link_is_first_and_targets_main():
    body = BASE.split("{% block body %}", 1)[1]
    skip = body.find('href="#main"')
    assert skip != -1 and skip < body.find('<aside id="sidebar"')
    assert 'id="main"' in _tag(BASE, "main") and 'tabindex="-1"' in _tag(BASE, "main")


def test_menu_buttons_expose_state():
    for bid in ("sidebar-open", "tabbar-menu"):
        tag = _tag(BASE, bid)
        assert 'aria-controls="sidebar"' in tag and 'aria-expanded="false"' in tag, bid


def test_mobile_menu_is_inert_when_closed_and_closes_on_escape():
    assert "sb.inert" in BASE and '"Escape"' in BASE


def test_palette_field_has_label_and_visible_focus():
    assert re.search(r'<label for="navpal-q"', PALETTE)
    field = _tag(PALETTE, "navpal-q")
    assert "focus:ring" in field
    assert not re.search(r"(?<![:\w-])outline-none", field)


def test_palette_announces_results():
    status = _tag(PALETTE, "navpal-status")
    assert 'role="status"' in status and "{n}" in status
