"""KA-12 E9.6 (2026-10-30): общая таблица кабинета `ui-table` + клавиатура в списках."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_table_component_in_css():
    css = (ROOT / "static/src/app.css").read_text()
    for sel in (".ui-table ", ".ui-table-stack", ".ui-num", "td[data-label]::before"):
        assert sel in css, sel


def test_chrome_includes_list_script():
    base = (ROOT / "templates/tenant/_base_dashboard.html").read_text()
    assert '{% include "core/_list_kb.html" %}' in base
    js = (ROOT / "templates/core/_list_kb.html").read_text()
    # подписи из <th>, клавиши только при фокусе в списке, без модификаторов
    assert "data-label" in js and 'closest("[data-kb-list]")' in js
    assert "e.altKey || e.ctrlKey || e.metaKey" in js and "isField(t)" in js
    # ревью a11y: строки фокус не получают — стрелки ведут на ссылку строки
    assert "tabIndex" not in js and "data-kb-active" not in js and "anchorOf" in js
    css = (ROOT / "static/src/app.css").read_text()
    assert 'attr(data-label) / ""' in css  # подпись не дублируется скринридером


def test_offene_posten_uses_ui_table():
    src = (ROOT / "templates/finance/offene_posten.html").read_text()
    assert 'class="ui-table ui-table-stack"' in src and "data-kb-list" in src
    assert 'data-cell="primary"' in src and 'data-cell="actions"' in src
    assert 'colspan="6" data-cell="empty"' in src  # пустая строка на все 6 колонок (было 5)
