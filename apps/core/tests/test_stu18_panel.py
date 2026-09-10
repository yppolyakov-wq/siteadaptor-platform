"""STU-18a: компоненты панели Студии — один шаблон строки и никакой обрезки.

Замер на живом стенде (демо aktionsmarkt, панель 380 px, кабинет по-русски) показал
две вещи, которых не видно на немецком: панель переливается по горизонтали на 30 px,
и пять подписей обрезаются. Причина — вёрстка под длину ОДНОГО языка: у подписи плитки
жёсткая ширина `w-16` (64 px) и `line-clamp-2`.

В CI браузера нет, поэтому здесь — инвариант РАЗМЕТКИ, который и породил дефект;
сама обрезка меряется стендом (docs/stu18-panel-ia-plan-2026-09-10.md §1.2).
"""

from pathlib import Path

import pytest

TPL = Path(__file__).resolve().parents[3] / "templates" / "tenant"


def _read(name: str) -> str:
    return (TPL / name).read_text(encoding="utf-8")


def test_tile_caption_wraps_instead_of_being_clipped():
    """Подпись плитки переносится, а не режется по фиксированной ширине.

    `w-16` + `line-clamp-2` — ровно та пара, что обрезала «Полки (подкатегории
    лентами)» и «Плитка предложения» и давала перелив в русской локали.
    """
    src = _read("_cardform_picker.html")
    caption = [ln for ln in src.splitlines() if "{{ label }}" in ln]
    assert caption, "подпись плитки не найдена — шаблон изменился, замок надо переписать"
    line = caption[0]
    assert "w-16" not in line, "у подписи плитки жёсткая ширина 64 px — длинные подписи режутся"
    assert "line-clamp" not in line, "line-clamp обрезает подпись вместо переноса"


def test_rows_is_a_choice_not_an_empty_number_field():
    """«Рядов» — селект с явным значением «alle».

    Пустое числовое поле с серым `placeholder` читается как «недоступно», а не как
    «сейчас показываются все» (П-5 разбора).
    """
    src = _read("_output_axis.html")
    assert 'name="{{ field }}_rows"' in src
    rows_block = src.split('name="{{ field }}_rows"')[0].rsplit("<label", 1)[-1]
    assert "<select" in rows_block, "«Рядов» всё ещё пустое числовое поле, а не выбор значения"


def test_speed_is_offered_only_for_the_slider():
    """«Скорость» показывается только когда выбран слайдер.

    Сегодня поле стоит всегда и пишет «выкл» — настройка, которая для сетки не значит
    ничего, занимает строку у каждой поверхности.
    """
    src = _read("_output_axis.html")
    speed = [
        ln
        for ln in src.splitlines()
        if "_speed" in ln and "<label" in ln or "data-axis-speed" in ln
    ]
    assert any("data-axis-speed" in ln for ln in src.splitlines()), (
        "у строки «Скорость» нет маркера data-axis-speed — её нечем скрыть при режиме «Сетка»"
    )
    assert speed


@pytest.mark.parametrize(
    "partial",
    ["_output_axis.html", "_cardform_picker.html", "_scope_pill.html"],
)
def test_panel_partials_have_no_multiline_django_comment(partial):
    """Грабля проекта: многострочный {# #} утекает ТЕКСТОМ на страницу."""
    src = _read(partial)
    for chunk in src.split("{#")[1:]:
        head = chunk.split("#}")[0]
        assert "\n" not in head, f"{partial}: многострочный {{# #}} — используйте {{% comment %}}"
