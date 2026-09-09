"""STU-13: Студия по утверждённому макету + язык кабинета из полноэкранной Студии.

Эталон — канвас `docs/design/studio-2026-09-07/`: артборд **P3** (плашка действий у блока
и панель с группами-карточками), **P4** (быстрый поповер плитками), **F1/F2** (топбар).
План — `docs/stu13-canvas-parity-plan-2026-09-09.md`.

Замки написаны ДО правок и краснеют на текущем коде: волна STU-12 сделала ПОВЕДЕНИЕ, а вид
остался черновым — плашка светлая и без имени блока, группы панели набраны капсом без сводки
значений, поповер узкий и с голыми `<select>`, а язык кабинета из Студии не переключить
(она полноэкранная, селектор живёт в шапке кабинета — владелец видел немецкую панель на
русской витрине и счёл это отсутствием перевода).
"""

import pathlib
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")


def _builder(tenant):
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req).content.decode()


def _css_rule(src: str, selector: str) -> str:
    """Тело CSS-правила по селектору (первое вхождение) — вид проверяем по стилям."""
    i = src.index(selector)
    return src[i : src.index("}", i)]


# ── A. Плашка действий у блока (макет P3) ────────────────────────────────────


def test_action_bar_carries_block_name():
    """A1: слева на плашке — ИМЯ выбранного блока (в макете «Produkte │ ▲ ▼ …»).

    Без имени плашка не говорит, чем управляет: у владельца она уехала в верхний левый
    угол канвы и читалась как случайная панель инструментов.
    """
    src = TPL.read_text()
    i = src.index('id="bld-action-bar"')
    markup = src[i : src.index("</div>", i)]
    assert 'data-ab="name"' in markup, "на плашке нет элемента с именем блока"


def test_action_bar_is_dark_pill():
    """A1: плашка — тёмная пилюля (макет), а не белая карточка."""
    src = TPL.read_text()
    rule = _css_rule(src, "#bld-action-bar.bld-ab-on")
    assert "background: #fff" not in rule, "плашка всё ещё белая"
    assert "#111827" in rule or "#1f2937" in rule, "нет тёмного фона плашки"


def test_action_bar_centered_over_block():
    """A3: плашка центрируется по блоку, а не липнет к его левому краю.

    `placeAnchored` ставил `left = rect.left`; у секции, начинающейся от края канвы,
    плашка оказывалась в верхнем левом углу экрана.
    """
    src = TPL.read_text()
    i = src.index("function placeAnchored")
    body = src[i : src.index("\n  }", i)]
    assert "rect.right - rect.left - w" in body, "placeAnchored не центрирует по якорю"


# ── B. Выделение выбранного блока на канве ───────────────────────────────────


def test_selected_section_is_outlined():
    """B: выбранная секция обведена (макет P3 — синяя рамка), иначе «что я правлю?».

    Проверяем сам механизм: редактор ставит класс выделения на элемент в кадре.
    """
    src = TPL.read_text()
    assert "sf-ed-selected" in src, "нет класса выделения выбранного блока"


# ── C. Панель блока (макет P3) ───────────────────────────────────────────────


def test_group_headings_are_not_uppercase():
    """C2/C3: заголовки групп — обычным регистром (в макете «Inhalt», не «INHALT»)."""
    src = TPL.read_text()
    rule = _css_rule(src, ".bld-grp-sum {")
    assert "uppercase" not in rule, "заголовки групп всё ещё капсом"


def test_group_is_a_card_with_value_summary():
    """C2: группа — карточка с рамкой, справа сводка значений («Titel · Quelle · 8»).

    Сводка — то, ради чего свёрнутая группа полезна: состояние читается без раскрытия.
    """
    src = TPL.read_text()
    rule = _css_rule(src, ".bld-grp {")
    assert "border:" in rule and "border-top" not in rule.split("border:")[0][-12:], (
        "группа не оформлена карточкой (рамка со всех сторон)"
    )
    assert "bld-grp-val" in src, "нет элемента сводки значений группы"


def test_panel_head_has_no_duplicate_order_buttons():
    """C1: ▲▼/⚙ живут на плашке у блока — голова строки в панели не показывается.

    Строка секции переносится в панель целиком (W0: поля не покидают форму), поэтому
    её голова с ▲▼/⚙ дублировала плашку. Прячем CSS, а не выбрасываем из DOM.
    """
    src = TPL.read_text()
    rule = _css_rule(src, "#bld-block-popup .home-block-head {")
    assert "display: none" in rule, (
        "голова строки видна в панели — порядок и ⚙ дублируют плашку у блока"
    )


def test_panel_explains_where_order_lives():
    """C1: вместо снятых кнопок — подсказка «порядок и скрытие — на плашке у секции»."""
    src = TPL.read_text()
    assert "bld-grp-hint" in src, "нет подсказки о том, где живут порядок и видимость"


# ── D. Быстрый поповер (макет P4) ────────────────────────────────────────────


def test_quick_popover_is_wide_enough_for_tiles():
    """D1: поповер шире (в макете — три плитки в ряд), 320px под это не хватало."""
    src = TPL.read_text()
    rule = _css_rule(src, "#bld-quick-pop.bld-quick-on")
    assert "min(320px" not in rule, "поповер всё ещё узкий (320px)"
    assert "min(380px" in rule or "min(400px" in rule or "min(420px" in rule


def test_quick_popover_has_head_with_close():
    """D1: у поповера шапка — название настройки, бейдж блока и ✕ (макет P4)."""
    src = TPL.read_text()
    assert 'id="bld-quick-pop-head"' in src, "у поповера нет шапки с названием и ✕"


def test_quick_popover_renders_tiles_in_grid():
    """D1: варианты — плитки сеткой, а не столбик `<select>`."""
    src = TPL.read_text()
    rule = _css_rule(src, "#bld-quick-pop .bld-thumbs")
    assert "grid-template-columns" in rule, "плитки поповера не разложены сеткой"


# ── E. Топбар (макет F1) ─────────────────────────────────────────────────────


def test_device_buttons_are_icons_only():
    """E: устройства — иконками (в макете три квадратика), подписи съедали строку."""
    src = TPL.read_text()
    i = src.index('data-dev="desktop"')
    btn = src[i : src.index("</button>", i)]
    assert "bld-device-label" in btn, "у кнопки устройства нет скрываемой подписи"


# ── F. Язык кабинета доступен из полноэкранной Студии ────────────────────────


@override_settings(CABINET_LANGUAGES=["de", "ru"])
def test_studio_topbar_has_cabinet_language():
    """F: из Студии видно и переключается язык КАБИНЕТА.

    Студия — полноэкранный оверлей: шапки кабинета с селектором 🗣 в ней нет, и владелец
    на русской витрине видел немецкую панель, считая, что перевода нет вовсе.
    """
    # Грабля-повтор (урок ST-3): контекст-процессор `modules_nav` возвращает {} для
    # схемы «public» — тенанту тестов нужна обычная схема, иначе cabinet_langs пуст.
    tenant = TenantFactory(schema_name="stu13")
    html = _builder(tenant)
    # В разметке — реверс `set-cabinet-lang`, поэтому ищем ПУТЬ, а не имя маршрута.
    assert reverse("set-cabinet-lang") in html, "в Студии нет переключателя языка кабинета"
    assert 'name="lang"' in html, "селектор языка кабинета не отрисован"
