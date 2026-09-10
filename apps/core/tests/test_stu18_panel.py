"""STU-18a: компоненты панели Студии — один шаблон строки и никакой обрезки.

Замер на живом стенде (демо aktionsmarkt, панель 380 px, кабинет по-русски) показал
две вещи, которых не видно на немецком: панель переливается по горизонтали на 30 px,
и пять подписей обрезаются. Причина — вёрстка под длину ОДНОГО языка: у подписи плитки
жёсткая ширина `w-16` (64 px) и `line-clamp-2`.

В CI браузера нет, поэтому здесь — инвариант РАЗМЕТКИ, который и породил дефект;
сама обрезка меряется стендом (docs/stu18-panel-ia-plan-2026-09-10.md §1.2).
"""

import re
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


# ── STU-18b: три оси как структура ───────────────────────────────────────────


def test_every_setting_declares_a_known_axis():
    """У каждой настройки ровно одна ось из реестра.

    Ось — свойство записи, а не второй словарь рядом (прецедент compositions.py):
    иначе он разъезжается с реестром ровно так же, как разъехались четыре реестра
    шаблонов страницы до волны LAY.
    """
    from apps.core import studio_pages as sp

    known = {code for code, _label in sp.AXES}
    assert len(known) == 4, "осей должно быть четыре: композиция · сетка · карточка · содержание"
    for code, setting in sp.SETTINGS.items():
        assert setting.axis in known, f"{code}: ось {setting.axis!r} не из реестра"


def test_axis_order_is_fixed():
    """Порядок групп в панели неизменен: от «что вокруг» к «как одна плитка»."""
    from apps.core import studio_pages as sp

    assert [code for code, _l in sp.AXES] == [
        sp.AXIS_COMPOSITION,
        sp.AXIS_GRID,
        sp.AXIS_CARD,
        sp.AXIS_CONTENT,
    ]


@pytest.mark.django_db
def test_panel_marks_every_row_with_its_axis(settings):
    """Панель подписывает строку осью из реестра — по этому атрибуту она группируется.

    Замок держит обе стороны: строка без оси не попадёт ни в одну группу и молча
    исчезнет из панели, а чужая ось означала бы, что настройка показана не там.
    Тенант тот же, что у `test_registry_and_panel_agree`: «ресторан без orders»
    открывает две строки, спрятанные бизнес-гейтами, а не типом страницы.
    """
    from apps.core import studio_pages as sp
    from apps.core.tests.test_studio_pages import _builder_html
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    markup = _builder_html(TenantFactory(business_type="restaurant", disabled_modules=["orders"]))

    found: dict[str, str] = {}
    for tag in re.findall(r"<[a-zA-Z][^>]*data-stu-setting=\"[^\"]+\"[^>]*>", markup):
        code = re.search(r'data-stu-setting="([^"]+)"', tag).group(1)
        axis = re.search(r'data-stu-axis="([^"]*)"', tag)
        found[code] = axis.group(1) if axis else ""

    missing = sorted(c for c in sp.SETTINGS if not found.get(c))
    assert not missing, f"строки без data-stu-axis: {missing}"
    wrong = {c: (found[c], sp.SETTINGS[c].axis) for c in found if found[c] != sp.SETTINGS[c].axis}
    assert not wrong, f"ось строки разошлась с реестром: {wrong}"


# ── STU-18c: панель не обещает того, чего нет (решение владельца Р-5) ─────────


def test_composition_gate_is_wired():
    """Гейт доступности композиций ВЫЗЫВАЕТСЯ в проде, а не лежит в реестре.

    `available_for` описан волной LAY («полки и вкладки без под-сущностей не
    предлагаются»), но до STU-18c у него было НОЛЬ вызовов: панель кормилась
    ungated-списком, и владелец выбирал «Полки» там, где подкатегорий нет.
    Это ровно тот класс, который он называет кашей: настройка есть, эффекта нет.
    """
    import subprocess

    hits = subprocess.run(
        ["grep", "-rn", "available_for(", "apps/", "templates/"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    prod = [h for h in hits if "/tests/" not in h and "def available_for" not in h]
    assert prod, "available_for() не вызывается в проде — гейт не подключён"


@pytest.mark.django_db
def test_shelves_are_not_offered_without_sub_entities(settings):
    """У тенанта без подкатегорий и наборов «Полки», «Вкладки» и «Сеты» — недоступны.

    Плитки остаются ВИДНЫ, но помечены недоступными с причиной: молча убрать их
    значило бы оставить владельца гадать, почему выбор исчез.
    """
    from apps.core.tests.test_studio_pages import _builder_html
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    markup = _builder_html(TenantFactory(business_type="restaurant"))

    for key in ("regale", "tabs", "sets"):
        tiles = re.findall(r'<button[^>]*data-cf-key="' + key + r'"[^>]*>', markup)
        assert tiles, f"плитка {key} вообще не отрендерена"
        assert all("data-cf-off" in t for t in tiles), (
            f"плитка {key} предлагается как доступная, хотя под-сущностей нет"
        )


@pytest.mark.parametrize("tpl", ["_combo_card.html", "_tour_card.html"])
def test_offered_card_forms_are_implemented(tpl):
    """Форма, предложенная на странице, обязана что-то менять в её карточке (Д-2).

    LAY-4 научил формам `_sellable_card`, но наборы и туры остались с четырьмя из
    шести: «Текст на фото» и «Ценник» на /kombi/ и /touren/ выбирались и молча
    ничего не делали. Обратная сторона правила STU-9 — обещание без исполнения.
    """
    from apps.core import card_forms

    src = (Path(__file__).resolve().parents[3] / "templates" / "storefront" / tpl).read_text(
        encoding="utf-8"
    )
    missing = [k for k in card_forms.keys_for(card_forms.PRODUCT) if k and f'"{k}"' not in src]
    assert not missing, f"{tpl}: формы предлагаются, но не реализованы: {missing}"
