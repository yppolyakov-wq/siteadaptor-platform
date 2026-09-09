"""STU-12d: плашка действий у выбранного блока + быстрые поповеры (F5A).

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12d): у выбранного на
канве блока появляется плашка (▲ ▼ 👁 🗑 ⚙ + «Stil ▾ / Raster ▾ / Breite ▾»);
кнопки зовут СУЩЕСТВУЮЩИЕ обработчики (moveByOrder/movePageBlock, чекбоксы
enabled_*/delete_cb_*, openBlockPopup), а поповер ПЕРЕНОСИТ в себя реальный контрол
формы (`style_<key>` / `layout_preset_<key>` / `width_<key>|width_cb_<id>`) и
возвращает его на место при закрытии — контролы не клонируются (W0: число полей
в `#home-form` не меняется).
"""

import pathlib
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")


def _html(tenant):
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req).content.decode()


def _segment(body, start_marker, end_marker):
    i = body.index(start_marker)
    return body[i : body.index(end_marker, i)]


def test_action_bar_and_quick_popover_render_inside_the_form():
    body = _html(TenantFactory(slug="stab1", name="StAb1"))
    form = _segment(body, 'id="home-form"', "</form>")
    assert 'id="bld-action-bar"' in form, (
        "плашка живёт В ФОРМЕ (переносимые контролы остаются в сабмите)"
    )
    assert 'id="bld-quick-pop"' in form and 'id="bld-quick-pop-body"' in form
    bar = _segment(body, 'id="bld-action-bar"', 'id="bld-quick-pop"')
    for act in ("up", "down", "vis", "del", "settings"):
        assert f'data-ab="{act}"' in bar, act
    for kind in ("style", "layout", "width"):
        assert f'data-quick="{kind}"' in bar, kind
    # W0: сама плашка и пустой поповер НИЧЕГО не сабмитят — иначе Save менял бы конфиг
    shell = _segment(body, 'id="bld-action-bar"', "</form>")
    assert 'name="' not in shell


def test_quick_popover_moves_the_control_and_puts_it_back():
    """Контрол ПЕРЕНОСИТСЯ (комментарий-якорь, как openBlockPopup), а не клонируется:
    клон отправил бы в сабмит второе значение того же поля."""
    tpl = TPL.read_text()
    fn = _segment(tpl, "function openQuickPop(", "function closeQuickPop(")
    assert "createComment" in fn, "место контрола держит комментарий-якорь"
    assert "quickBody.appendChild" in fn
    assert "cloneNode" not in fn, "контрол переносится, а не клонируется"
    back = _segment(tpl, "function closeQuickPop(", "\n  function ")
    assert "quickAnchor" in back and "insertBefore" in back
    assert "quickAnchor.parentNode.removeChild" in back or "quickAnchor.remove()" in back


def test_quick_popover_targets_are_real_form_controls():
    """Кнопки плашки показываются ТОЛЬКО когда у блока есть такой контрол —
    иначе поповер открывался бы пустым."""
    tpl = TPL.read_text()
    fn = _segment(tpl, "function quickCtl(", "function quickUnit(")
    for name in ("style_", "layout_preset_", "width_", "width_cb_"):
        assert '"' + name + '"' in fn or "'" + name + "'" in fn, name


def test_place_anchored_uses_frame_scale_and_clamps():
    """Координаты берутся из rect элемента ВНУТРИ кадра × масштаб канвы (applyDevice
    масштабирует iframe трансформом) + смещение кадра; плашка не уезжает за экран."""
    tpl = TPL.read_text()
    fn = _segment(tpl, "function frameScale(", "function placeAnchored(")
    assert "getBoundingClientRect" in fn and "offsetWidth" in fn
    place = _segment(tpl, "function placeAnchored(", "\n  function ")
    assert "Math.max" in place and "Math.min" in place, "clamp по краям экрана"
    assert "innerWidth" in place and "innerHeight" in place
    anchor = _segment(tpl, "function anchorRect(", "function placeAnchored(")
    assert "frameScale()" in anchor, "rect элемента умножается на масштаб кадра"


def test_popover_flips_above_the_bar_when_there_is_no_room_below():
    tpl = TPL.read_text()
    place = _segment(tpl, "function placeAnchored(", "\n  function ")
    assert re.search(r"below|flip|выше|над", place), "есть ветка «не влезло снизу → выше»"


def test_bar_follows_the_canvas_and_survives_the_swap():
    """Живая правка перерисовывает канву двойной буферизацией — выбранный узел
    становится ДРУГИМ; плашка обязана переехать на новый узел, иначе после первой
    же смены настройки она указывает в никуда.

    Переписан осознанно: перенос делает САМА `positionBar` (она вызывается и по
    скроллу, и по тикеру, и после свопа), а `reselectAfterSwap` — быстрый путь из
    `instrumentFrame`. Проверяем контракт там, где он живёт.
    """
    tpl = TPL.read_text(encoding="utf-8")
    assert "function reselectAfterSwap(" in tpl
    fn = _segment(tpl, "function reselectAfterSwap(", "\n  function ")
    assert "abKey" in fn and "positionBar()" in fn, "быстрый путь зовёт перенос"
    pos = _segment(tpl, "function positionBar(", "function showBarFor(")
    assert 'data-sf-section="' in pos and "abKey" in pos, (
        "перенос ищет блок с тем же ключом в ТЕКУЩЕМ документе канвы"
    )
    assert "isConnected" in pos and "ownerDocument" in pos, (
        "признак «узел из прошлой канвы» — отсоединён или из другого документа"
    )
    inst = _segment(tpl, "function instrumentFrame(", "function schedule()")
    assert "reselectAfterSwap()" in inst, "после оснастки нового кадра плашка возвращается"


def test_bar_buttons_reuse_existing_handlers():
    tpl = TPL.read_text()
    fn = _segment(tpl, "function barAction(", "\n  function ")
    assert "moveByOrder(" in fn and "movePageBlock(" in fn, "порядок — существующие движки"
    assert "openBlockPopup(" in fn, "⚙ открывает колонку блока"
    assert "delete_cb_" in fn and "enabled" in fn, "🗑/👁 — те же чекбоксы формы"


def test_escape_and_outside_click_close_the_popover():
    tpl = TPL.read_text()
    esc = _segment(tpl, 'if (e.key !== "Escape") return;', "});")
    assert "closeQuickPop" in esc, "Esc сначала закрывает поповер"
    assert "quickOutsideClose" in tpl, "клик мимо — в т.ч. ВНУТРИ канвы (iframe)"
    inst = _segment(
        tpl, "function instrumentFrame(", 'frame.addEventListener("load", instrumentFrame)'
    )
    assert "quickOutsideClose" in inst, "слушатель вешается и на документ кадра"


def test_bar_stays_usable_when_the_block_is_hidden_by_its_own_toggle():
    """Найдено стендом: 👁 был односторонним.

    `positionBar` гасил плашку по одному условию «блок за краем канвы», но у скрытого
    (display:none) блока коробки НЕТ вовсе — вырожденный прямоугольник попадал в то же
    условие, плашка становилась opacity:0/pointer-events:none, и вернуть блок с неё было
    нельзя (только из колонки). Скрытие владельцем и «укручен за край» — разные случаи:
    первый обязан оставлять плашку живой, иначе кнопка видимости работает в одну сторону.
    """
    body = TPL.read_text(encoding="utf-8")
    seg = _segment(body, "function positionBar(", "function showBarFor(")
    assert re.search(r"var flat = ", seg), "нужен признак «у блока нет коробки» (скрыт)"
    assert re.search(r"var off = !flat &&", seg), (
        "гашение плашки — ТОЛЬКО для блока за краем канвы, не для скрытого"
    )


def test_double_buffering_instruments_the_new_canvas():
    """Пред-существующий дефект, найденный стендом 12d (класс «фича молча не работала»).

    Свежесозданный буфер-iframe отдаёт `load` СВОЕГО about:blank ещё до навигации по `src`.
    Этот load считался провалом рендера → на КАЖДУЮ живую правку шёл hard-reload: канва
    прыгала в начало и теряла ВСЮ оснастку редактора («+», инлайн-правка, ручки drag,
    клик-выбор), потому что гвард оснастки был флагом на <body> ТЕКУЩЕГО `frame`, а
    instrumentFrame успевал отработать, пока `frame` ещё указывал на СТАРЫЙ кадр.
    """
    tpl = TPL.read_text(encoding="utf-8")
    first = _segment(tpl, "function onFirstLoad()", "var bufOk = false;")
    assert 'proto0 === "about:"' in first, (
        "about:blank буфера — не провал рендера, а нормальный первый load"
    )
    inst = _segment(tpl, "function instrumentFrame(", "function schedule()")
    assert "lastInstrumentedDoc === gDoc" in inst, "гвард оснастки — по ДОКУМЕНТУ, не по <body> frame"
    swap = _segment(tpl, "frame = buf;", "old.removeAttribute(\"id\")")
    assert "instrumentFrame()" in swap, "новый кадр оснащается сразу после подмены"
