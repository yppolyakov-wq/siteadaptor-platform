"""STU-12h (F7A): Студия на телефоне.

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12h): «⚙ Seite» открывает
лист настроек страницы (сделано в 12a), поповеры становятся bottom-sheet, плашка действий
видна на тач-устройстве, `▲▼` доступны в листах, `●` статус несохранённого рядом с
«Speichern» на узком экране, `isNarrow` — через `matchMedia`-listener.

Отдельный инвариант, ради которого замок написан ДО кода: `isNarrow` сегодня вычисляется
ОДИН раз при загрузке. Владелец, сузивший окно (или повернувший планшет), получал десктопное
поведение панели — затемнения нет, лист ведёт себя как боковая колонка.
"""

import pathlib
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

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


def _segment(body, start, end):
    i = body.index(start)
    return body[i : body.index(end, i)]


def test_is_narrow_follows_the_viewport():
    """Смена ширины окна обязана менять поведение панели, а не только первый рендер."""
    tpl = TPL.read_text(encoding="utf-8")
    assert 'var isNarrow = !window.matchMedia("(min-width: 1024px)").matches;' not in tpl, (
        "константа: сузив окно, владелец остаётся с десктопным поведением"
    )
    assert "narrowMq" in tpl and 'addEventListener("change"' in tpl


def test_quick_popovers_become_a_bottom_sheet_on_a_phone():
    tpl = TPL.read_text(encoding="utf-8")
    assert "bld-quick-sheet" in tpl, "на телефоне поповер — лист снизу, а не плавающий блок"
    css = _segment(tpl, "#bld-quick-pop.bld-quick-sheet", "}")
    for prop in ("position: fixed", "left: 0", "right: 0", "bottom: 0"):
        assert prop in css, prop
    # позиционирование у листа не считается — placeQuick обязан это учитывать
    place = _segment(tpl, "function placeQuick(", "function closeQuickPop(")
    assert "bld-quick-sheet" in place


def test_action_bar_is_reachable_without_hover():
    """Плашка блока — единственный вход в Stil/Raster/Breite; на тач hover не бывает."""
    tpl = TPL.read_text(encoding="utf-8")
    bar = _segment(tpl, "#bld-action-bar button {", "#bld-action-bar button[hidden]")
    assert "min-height" in bar or "padding" in bar
    sheet = _segment(tpl, "@media (hover: none)", "}")
    assert "#bld-action-bar" in sheet, "у тач-устройств своя, крупная плашка"


def test_save_button_shows_unsaved_dot_on_narrow_screens():
    body = _builder(TenantFactory(slug="stmb1", name="StMb1"))
    assert 'id="bld-save-dot"' in body, "маркер несохранённого рядом с «Speichern»"
    # именно РЯДОМ с кнопкой: между ними только закрывающий тег кнопки
    near = _segment(body, 'form="home-form"', "</span>")
    assert 'id="bld-save-dot"' in near, "маркер должен стоять у кнопки, а не где-то ещё"
    tpl = TPL.read_text(encoding="utf-8")
    assert "bld-save-dot" in tpl and "saveDot" in tpl


def test_move_buttons_live_in_the_block_row():
    """`▲▼` доступны и в листе (строка блока переносится в колонку целиком)."""
    body = _builder(TenantFactory(slug="stmb2", name="StMb2"))
    i = body.index('name="order_faq"')
    row = body[body.rindex('class="home-block ', 0, i) : i + 4000]
    assert "blk-up" in row and "blk-down" in row
