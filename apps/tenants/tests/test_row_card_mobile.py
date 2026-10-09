"""LB-4d-3 (стенд): секция услуг на главной — одна колонка на телефоне.

Секция всегда рисует СТРОЧНЫЕ карточки (фото · имя · цена с кнопкой). В сетке
«3 колонки» пресет даёт телефону две, и строка шириной 171 px не помещает колонку цены:
на ru («ФИКСИРОВАННАЯ ЦЕНА» + «Забронировать») главная ретрита уезжала вбок. Потолок
мобильных колонок — свойство секции, а не выбор владельца: две строки рядом на телефоне
не читаются никогда.
"""

from apps.tenants import siteconfig


def _layout(raw):
    cfg = siteconfig.normalize({"sections": [{"key": "services", "enabled": True, "layout": raw}]})
    return next(s for s in cfg["sections"] if s["key"] == "services")["layout"]


def test_services_section_is_one_column_on_phones_whatever_the_preset():
    assert _layout({"preset": "cols3"})["mobile"] == 1
    assert _layout({"preset": "cols4", "mobile": 2})["mobile"] == 1
    assert _layout({"preset": "cols3"})["cols"] == 3  # десктоп владельца не трогаем


def test_other_grids_keep_two_columns_on_phones():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "layout": {"preset": "cols3"}}]}
    )
    row = next(s for s in cfg["sections"] if s["key"] == "products")
    assert row["layout"]["mobile"] == 2


def test_list_block_of_services_keeps_two_columns_on_phones():
    """Блок «Liste» рисует услуги плитками — потолок секции к нему не относится."""
    from apps.core import list_blocks

    default = list_blocks._DEFAULTS["services"]
    assert "mobile_max" not in default
    assert siteconfig.normalize_layout({"preset": "cols3"}, default)["mobile"] == 2
