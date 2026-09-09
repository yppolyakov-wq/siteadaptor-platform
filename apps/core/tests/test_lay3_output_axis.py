"""LAY-3b — «тип вывода»: сетка/слайдер, ряды, лимит, пагинация, скорость.

Уточнение владельца 2026-09-09: «тип слайдер (сколько карточек, скорость
переключения, сколько строк) или тип сетка: сколько колонок; сколько элементов
показывать — например их 50, показываем 10, как раз 2 ряда по 5; не задано —
показывать все; пагинация — сколько выводить на странице».

Разбор и решения — `docs/lay-unified-output-plan-2026-09-09.md §10.4`. Ключевое
проектное решение: показываем РЯДЫ, а не абсолютное число. Абсолютный лимит
перестаёт быть ровным при смене числа колонок — ровно та рваная картина, которую
лечили волны DL-11/DL-14/DL-15.

Замки написаны ДО правок и краснеют на текущем коде.
"""

import pytest

from apps.tenants import siteconfig

# ── Новые параметры оси: presence-minimal ────────────────────────────────────


def test_rows_is_stored_and_clamped():
    """«Сколько рядов показать» — 1..6; мусор и ноль ключа не создают."""
    assert siteconfig.normalize_layout({"preset": "cols5", "rows": 2})["rows"] == 2
    assert siteconfig.normalize_layout({"preset": "cols5", "rows": 99})["rows"] == 6
    assert "rows" not in siteconfig.normalize_layout({"preset": "cols5"})
    assert "rows" not in siteconfig.normalize_layout({"preset": "cols5", "rows": 0})
    assert "rows" not in siteconfig.normalize_layout({"preset": "cols5", "rows": "quatsch"})


def test_page_size_is_stored_and_clamped():
    """Размер страницы пагинации задаёт владелец; пусто = как считала вьюха."""
    assert siteconfig.normalize_layout({"preset": "cols3", "page_size": 24})["page_size"] == 24
    assert siteconfig.normalize_layout({"preset": "cols3", "page_size": 1})["page_size"] == 6
    assert siteconfig.normalize_layout({"preset": "cols3", "page_size": 999})["page_size"] == 96
    assert "page_size" not in siteconfig.normalize_layout({"preset": "cols3"})


def test_slider_speed_is_off_by_default():
    """Автопрокрутка выключена по умолчанию (доступность, решение DL-16.1).

    Ключ появляется только когда владелец её ОСОЗНАННО включил; секунды клампятся.
    """
    assert "speed" not in siteconfig.normalize_layout({"preset": "cols3", "scroll": True})
    assert siteconfig.normalize_layout({"preset": "cols3", "speed": 5})["speed"] == 5
    assert siteconfig.normalize_layout({"preset": "cols3", "speed": 1})["speed"] == 3
    assert siteconfig.normalize_layout({"preset": "cols3", "speed": 999})["speed"] == 15
    assert "speed" not in siteconfig.normalize_layout({"preset": "cols3", "speed": 0})


def test_new_keys_do_not_touch_golden_normalize():
    """Ни один новый ключ не материализуется в пустом конфиге."""
    cfg = siteconfig.normalize({})
    for key in ("rows", "page_size", "speed"):
        assert key not in cfg.get("catalog_layout", {}), key


# ── Эффективный лимит: «10 = 2 ряда по 5» получается САМО ────────────────────


def test_effective_limit_is_rows_times_columns():
    layout = siteconfig.normalize_layout({"preset": "cols5", "rows": 2})
    assert siteconfig.effective_limit(layout) == 10


def test_effective_limit_follows_the_columns():
    """Смена колонок сохраняет ровность рядов — ради этого и хранятся ряды."""
    assert (
        siteconfig.effective_limit(siteconfig.normalize_layout({"preset": "cols4", "rows": 2})) == 8
    )
    assert (
        siteconfig.effective_limit(siteconfig.normalize_layout({"preset": "cols3", "rows": 2})) == 6
    )


def test_effective_limit_is_none_when_rows_not_set():
    """«Не задано количество элементов — показывать все» (слова владельца)."""
    assert siteconfig.effective_limit(siteconfig.normalize_layout({"preset": "cols5"})) is None


def test_explicit_limit_wins_over_rows():
    """Секции главной уже имеют своё число элементов (`limit_<key>`) — оно сильнее."""
    layout = siteconfig.normalize_layout({"preset": "cols5", "rows": 2})
    assert siteconfig.effective_limit(layout, explicit=7) == 7
    assert siteconfig.effective_limit(layout, explicit=0) == 10, "0 = «не задано», не «ноль штук»"


# ── Тип вывода: сетка или слайдер ────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [({}, "grid"), ({"scroll": True}, "slider")])
def test_output_mode_reads_the_existing_key(raw, expected):
    """Тип вывода — производное от существующего `scroll`: конфиги не переписываем."""
    layout = siteconfig.normalize_layout({"preset": "cols3", **raw})
    assert siteconfig.output_mode(layout) == expected


def test_slider_carries_its_parameters_into_the_markup():
    """У слайдера в разметку уезжают строки и скорость — иначе контрол ничего не делает."""
    layout = siteconfig.normalize_layout({"preset": "cols4", "scroll": True, "rows": 2, "speed": 6})
    attrs = siteconfig.grid_attr_string(layout)
    assert 'data-sf-slider="1"' in attrs
    assert 'data-sf-rows="2"' in attrs
    assert 'data-sf-speed="6"' in attrs


def test_grid_keeps_its_markup_unchanged_without_new_keys():
    """Паритет: конфиг без новых ключей даёт ту же разметку, что до волны."""
    layout = siteconfig.normalize_layout({"preset": "cols3"})
    attrs = siteconfig.grid_attr_string(layout)
    assert "data-sf-rows" not in attrs
    assert "data-sf-speed" not in attrs
