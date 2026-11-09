"""PH-13d (остаток): переключатель Liste/Karte и закреплённая строка фильтров на телефоне."""

from __future__ import annotations

import re
from pathlib import Path

TPL = Path(__file__).resolve().parents[3] / "templates" / "aggregator"


def test_map_toggle_links_are_nofollow_and_mark_current():
    src = (TPL / "_map.html").read_text()
    toggle = src[src.index("data-map-toggle") : src.index("agg-near-me")]
    assert toggle.count('rel="nofollow"') == 2  # query-вариации (noindex) — не для робота
    assert 'aria-current="page"' in toggle
    # «текущий» вид помечен ровно одной ссылкой в зависимости от map_view.open
    assert re.search(r"data-map-list[^>]*\{% if not map_view\.open %\} aria-current", toggle)
    assert re.search(r"data-map-show[^>]*\{% if map_view\.open %\} aria-current", toggle)


def test_filter_bar_is_sticky_only_on_phones():
    src = (TPL / "_portal_filter_bar.html").read_text()
    # sticky держится в пределах родителя: ставим на обёртку data-flt (её родитель — вся выдача)
    bar = src[src.index("<div data-flt ") : src.index(">", src.index("<div data-flt "))]
    assert "max-md:sticky" in bar and "max-md:top-0" in bar
    assert "max-md:bg-" in bar  # непрозрачный фон: карточки не просвечивают под строкой
    assert " sticky" not in bar.replace("max-md:sticky", "")


def test_sort_lives_in_the_toolbar_row_with_an_accessible_name():
    """PH-14: сортировка — в той же строке, что фильтры; подпись — только для читалок."""
    src = (TPL / "_portal_filter_bar.html").read_text()
    bar = src[src.index("<div data-flt-bar") : src.index("data-flt-applied")]
    assert "data-flt-sort" in bar and "data-view-switch" in bar
    assert '<span class="sr-only">{% trans "Sortieren" %}</span>' in bar


def test_ok_button_is_not_translated_as_a_word_of_approval():
    import polib

    root = Path(__file__).resolve().parents[3] / "locale"
    for loc in ("ru", "uk"):
        e = polib.pofile(str(root / loc / "LC_MESSAGES" / "django.po")).find("OK")
        assert e.msgstr == "OK", loc  # «Хорошо»/«Гаразд» — омоним на кнопке «применить»


def test_sticky_panel_does_not_hide_focus_and_yields_on_short_screens():
    base = (TPL / "portal_base.html").read_text()
    html_tag = base[base.index("<html") : base.index(">", base.index("<html"))]
    # 2.4.11: фокус не прячется под закреплённой панелью и нижним меню
    assert "max-md:scroll-pt-" in html_tag and "max-md:scroll-pb-" in html_tag
    src = (TPL / "_portal_filter_bar.html").read_text()
    assert "[@media(max-height:480px)]:static" in src  # ландшафт/зум — без закрепления
    assert "aria-label=" in (TPL / "_map.html").read_text().split("data-map-toggle")[0][-200:]
