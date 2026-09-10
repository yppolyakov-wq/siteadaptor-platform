"""STU-17: обратная сторона инварианта LAY-4 — «исполнение без обещания».

LAY-4 проверял ОДНУ сторону: «тип страницы объявляет ось `*_card_form` ⇒ его
разметка рисует карточку». Обратная — «разметка рисует карточку (или сетку) ⇒ тип
ОБЯЗАН объявить эту ось» — не проверялась, и восемь страниц оказались в слепой
зоне: настройка на них действует, а панель её не предлагает. Для владельца это
выглядит как «структура/каша»: значение он меняет на одной странице, а видит на
другой.

Карта «тип → шаблон» здесь НЕ пишется руками (она бы протухла на первой же новой
странице): тип → `url_name` → вьюха → её `render(request, "…")` → рекурсивный обход
`{% include %}/{% extends %}`.

Граница честности: деривация — НИЖНЯЯ оценка. Через динамический include
(`{% include s.template %}` на деталях — реестр `detail_sections`) она пройти не
может, поэтому красный тут = настоящая находка, а зелёный = «не нашли», а не
«карточки нет». Верхнюю границу (обещание ⇒ исполнение) держит парный замок
`test_lay4_card_forms.py` со СВОЕЙ, ручной и фейл-клоузед картой: тип, которого в
ней нет, объявлен нарушителем, а не пропущен молча. Два замка сходятся с разных
сторон — намеренно, ни один не заменяет другой.

План — `docs/stu17-axis-coverage-plan-2026-09-10.md`.
"""

import inspect
import re

import pytest
from django.template.loader import get_template
from django.urls import get_resolver

from apps.core import studio_pages as sp

#: Маркеры карточки в разметке — все партиалы/теги, которые читают форму карточки.
CARD_MARKERS = re.compile(
    r"_product_card\.html|_promo_card\.html|_combo_card\.html|_tour_card\.html|sellable_card"
)
#: Маркеры сетки — теги движка раскладок (оба, узкий и общий).
GRID_MARKERS = re.compile(r"sf_grid_attrs|grid_attrs")

#: Шаблон вьюхи: `render(request, "…")` И обёртки вокруг него — витрина рендерит
#: листинги через `_render_embed` (виджет/iframe), и узкий шаблон их не видел.
_RENDER = re.compile(r'(?:^|[^\w])\w*render\w*\(\s*request,\s*"([^"]+\.html)"')
_INCLUDE = re.compile(r'{%\s*(?:include|extends)\s*"([^"]+\.html)"')

#: Страницы, чью сетку задаёт раскладка ОДНОИМЁННОЙ секции главной (они
#: переиспользуют её партиал). Второй ключ ради «настройки здесь» был бы дублем —
#: план §3.2: вместо контрола панель даёт подсказку со ссылкой на секцию.
GRID_FROM_HOME_SECTION = {"team", "gallery"}


def _views_by_url_name():
    out = {}

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
            elif getattr(p, "name", None):
                out[p.name] = p.callback

    walk(get_resolver("config.urls_tenant").url_patterns)
    return out


def _scan(template_name, seen=None):
    """(есть карточка, есть сетка) в шаблоне и во всём, что он включает."""
    seen = seen if seen is not None else set()
    if template_name in seen:
        return (False, False)
    seen.add(template_name)
    try:
        source = open(get_template(template_name).origin.name, encoding="utf-8").read()
    except Exception:  # noqa: BLE001 — шаблона нет/не читается: не наша забота
        return (False, False)
    # STU-18d: пояснительные блоки — не разметка. Пока их не вырезали, ЛЮБАЯ
    # страница на каркасе `listing.html` считалась рисующей карточку: имя
    # `_product_card.html` встречается в описании контракта полок. Сканер обязан
    # смотреть на то, что рендерится, иначе краснеет на прозе.
    source = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", source, flags=re.S)
    card = bool(CARD_MARKERS.search(source))
    grid = bool(GRID_MARKERS.search(source))
    for name in _INCLUDE.findall(source):
        sub_card, sub_grid = _scan(name, seen)
        card, grid = card or sub_card, grid or sub_grid
    return (card, grid)


def _axes_rendered(page_type, views):
    """Какие оси РЕАЛЬНО действуют на странице этого типа."""
    templates = set()
    for url_name in page_type.url_names:
        view = views.get(url_name)
        if view is None:
            continue
        try:
            templates |= set(_RENDER.findall(inspect.getsource(view)))
        except (OSError, TypeError):  # вьюха не из исходника — пропускаем
            continue
    card = grid = False
    for name in templates:
        has_card, has_grid = _scan(name)
        card, grid = card or has_card, grid or has_grid
    return card, grid


def _axes_offered(page_type):
    codes = page_type.settings
    return (
        any("card_form" in code for code in codes),
        any(code.endswith("_layout") for code in codes),
    )


@pytest.mark.parametrize("page_type", list(sp.PAGE_TYPES), ids=lambda pt: pt.code)
def test_rendered_axis_is_offered_in_the_panel(page_type):
    """Ось действует на странице ⇒ панель этого типа обязана её предлагать."""
    views = _views_by_url_name()
    card_acts, grid_acts = _axes_rendered(page_type, views)
    card_offered, grid_offered = _axes_offered(page_type)
    if card_acts:
        assert card_offered, (
            f"{page_type.code}: разметка рисует карточку, но ось «форма карточки» "
            "в реестре не объявлена — владелец меняет её на другой странице"
        )
    if grid_acts and page_type.code not in GRID_FROM_HOME_SECTION:
        assert grid_offered, (
            f"{page_type.code}: разметка строит сетку движком раскладок, но ось "
            "«сетка» в реестре не объявлена"
        )


def test_home_section_pages_are_declared_not_forgotten():
    """Исключение §3.2 — осознанное и узкое: только team/gallery, и они существуют.

    Замок держит границу: расширять список молча (чтобы «замок позеленел») нельзя —
    каждая новая страница здесь означает ещё одну поверхность без своей настройки.
    """
    codes = {pt.code for pt in sp.PAGE_TYPES}
    assert GRID_FROM_HOME_SECTION <= codes
    assert len(GRID_FROM_HOME_SECTION) == 2
