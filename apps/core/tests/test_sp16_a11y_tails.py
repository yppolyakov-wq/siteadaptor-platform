"""SP-16 (решение владельца 2026-11-03): хвосты ревью доступности серии SP.

3. Низкий экран (≤ 480 px высоты: телефон боком, 400 % масштаб) — нижние слои витрины
   встают в поток страницы, а не закрывают контент (WCAG 1.4.10).
4. Text-Check: live-region всегда в дереве доступности; «Ausblenden» с уникальным
   именем; фокус после скрытия не теряется.
5. Кнопки Text-Check ≥ 32 px (Mini App).
6. Лента типов акций на телефоне прокручивается к открытому типу.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.template.loader import render_to_string

ROOT = Path(__file__).resolve().parents[3]


def _css(built=False):
    return (ROOT / "static" / ("css" if built else "src") / "app.css").read_text()


def test_low_height_unfixes_bottom_layers():
    css = _css()
    block = css.split("@media (max-height: 480px)", 1)[1].split("\n}\n", 1)[0]
    for sel in ("[data-sf-bottom-nav]", "[data-buybar]", "[data-chat-fab]", "[data-sf-presence]"):
        assert sel in block
    assert "position: static !important" in block
    # переменные отступов обнуляются, иначе подвал держал бы пустое место
    assert "--sf-nav-h: 0px !important" in block
    assert "--sf-buybar-h: 0px !important" in block
    assert "max-height:480px" in _css(built=True).replace(" ", "")


class _Finding:
    def __init__(self, **kw):
        self.__dict__.update(
            {
                "severity": "medium",
                "quote": "",
                "suggestion": None,
                "source": "rules",
                "norm": "UWG",
                "field": "title",
                "locale": "de",
                "code": "x",
            }
        )
        self.__dict__.update(kw)


def _results(findings):
    return render_to_string("promotions/_text_check_results.html", {"text_findings": findings})


def test_hide_buttons_have_unique_names_and_target_size():
    html = _results(
        [_Finding(message="Preis fehlt", code="a"), _Finding(message="Datum prüfen", code="b")]
    )
    labels = re.findall(r'data-tc-hide aria-label="([^"]+)"', html)
    assert len(labels) == 2 and len(set(labels)) == 2, labels
    assert all(lbl.startswith("Ausblenden") for lbl in labels)  # WCAG 2.5.3: видимое — в начале
    assert html.count("min-h-[32px]") >= 2


def test_status_live_region_is_never_display_none():
    html = render_to_string("promotions/_text_check.html", {"text_findings": []})
    m = re.search(r'<p class="([^"]*)" data-tc-status role="status">', html)
    assert m, "live-region пропал или без role=status"
    assert "hidden" not in m.group(1).split()
    assert 'classList.toggle("sr-only", !text)' in html
    assert 'classList.toggle("hidden", !text)' not in html
    # одинаковый результат не перерисовывается (регион не «болтает»)
    assert "html !== container._tcHtml" in html
    # кнопки проверки ≥ 32 px
    assert re.search(r'min-h-\[32px\][^"]*" data-tc-run', html)


def test_hide_moves_focus_to_next_item():
    html = render_to_string("promotions/_text_check.html", {"text_findings": []})
    hide_js = html.split("if (hide) {", 1)[1].split("return;\n    }", 1)[0]
    assert "nextElementSibling" in hide_js and ".focus()" in hide_js


def test_type_chips_scroll_active_into_view():
    html = render_to_string(
        "storefront/promo_page/_type_chips.html",
        {"groups": [("a", "A"), ("b", "B")], "selected_group": "b"},
    )
    assert 'aria-current="page"' in html
    assert "row.scrollLeft" in html and "__sfTypeChipsBound" in html
    # без вертикального прыжка страницы (scrollIntoView двигал бы и окно)
    assert "scrollIntoView" not in html
    assert 'addEventListener("toggle"' in html


def test_chat_fab_name_is_its_visible_label():
    """WCAG 2.5.3: aria-label «Ask us a question» в de/ru/uk/tr не начинался с
    видимого «Ask us» — имя теперь сама подпись (sr-only там, где не видна)."""
    base = (ROOT / "templates" / "storefront" / "_base.html").read_text()
    fab = base.split("data-chat-fab title=", 1)[1].split("</a>", 1)[0]
    assert "aria-label" not in fab
    assert 'class="sr-only sm:not-sr-only lg:sr-only' in fab
