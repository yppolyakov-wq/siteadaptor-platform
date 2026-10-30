"""KA-12 E9.2: пустой список кабинета — одна деталь `ui/_empty.html` с первым действием (VI-7).

План — `docs/ka-12-w5-e9-2-empty-states-plan-2026-10-30.md`.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string

ROOT = Path(settings.BASE_DIR) / "templates"

# экран → маршрут «создать», на который ведёт кнопка пустого состояния
SCREENS = {
    "catalog/category_list.html": "catalog:category-create",
    "catalog/combo_list.html": "catalog:combo-create",
    "crm/company_list.html": "crm:company-create",
    "events/event_list.html": "events:create",
    "events/teacher_list.html": "events:teacher-create",
}


@pytest.mark.parametrize("path,url_name", SCREENS.items())
def test_list_screen_uses_shared_empty_state_with_action(path, url_name):
    src = (ROOT / path).read_text(encoding="utf-8")
    assert '"ui/_empty.html"' in src
    assert f"{{% url '{url_name}' as u %}}" in src and "action_url=u" in src


def test_empty_partial_renders_action_only_with_both_parts():
    full = render_to_string(
        "ui/_empty.html", {"title": "Leer", "action_url": "/x/", "action_label": "Neu"}
    )
    assert "data-ui-empty" in full and 'href="/x/"' in full and "ui-btn-primary" in full
    bare = render_to_string("ui/_empty.html", {"title": "Leer", "action_url": "/x/"})
    assert "<a " not in bare


def test_empty_partial_escapes_title():
    html = render_to_string("ui/_empty.html", {"title": "<b>x</b>"})
    assert "&lt;b&gt;" in html
