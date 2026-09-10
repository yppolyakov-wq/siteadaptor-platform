"""STU-12b: одна колонка вместо «область + лента блока».

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12b): выбранный блок
показывается В ТОЙ ЖЕ колонке `#bld-editor-pane` — шапка колонки становится крошкой
«‹Seite› › ‹блок›» + `Einfach|Experte` + `⋯` + `✕`, контекст-группа верхней строки
(`.bld-ctx`, UC6-10) снята, fixed-геометрия «ленты» (UC6-6a) ушла — строка формы
по-прежнему ПЕРЕНОСИТСЯ (комментарий-якорь), а не клонируется (W0).
"""

import pathlib
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")


def _html(tenant):
    request = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = tenant
    return views.home_builder_view(request).content.decode()


def _segment(body, start_marker, end_marker):
    i = body.index(start_marker)
    return body[i : body.index(end_marker, i)]


def test_topbar_context_group_is_gone_and_block_head_lives_in_the_column():
    tenant = TenantFactory(slug="stcol1", name="StCol1")
    body = _html(tenant)
    assert "bld-ctx" not in body, "контекст-группа верхней строки (UC6-10) снята"
    assert 'id="bld-ribbon-collapse"' not in body and "bld-ribbon-min" not in body
    # шапка блока — ВНУТРИ контейнера блока в колонке, а не в верхней строке
    popup = _segment(body, 'id="bld-block-popup"', 'id="bld-block-popup-body"')
    for marker in (
        'id="bld-block-head"',
        'id="bld-block-back"',
        'id="bld-block-crumb"',
        'id="bld-block-popup-title"',
        # STU-16c (осознанно): пилюли Einfach|Experte из шапки блока УБРАНЫ —
        # владелец попросил «оставь только эксперт везде». Остальной состав шапки
        # (крошка, ⋯, ✕) — прежний, его строка и держит.
        'id="bld-block-more"',
        'id="bld-dense-toggle"',
        'id="bld-block-popup-close"',
    ):
        assert marker in popup, marker
    # W0: шапка блока живёт внутри #home-form, но НИЧЕГО не сабмитит — ни одного name=
    head = _segment(body, 'id="bld-block-head"', 'id="bld-block-popup-body"')
    assert 'name="' not in head
    assert "bld-mode-" not in head, "режим Простой/Эксперт снят (STU-16c)"
    # шапка самой панели прячется, пока открыт блок (одна шапка за раз)
    assert 'id="bld-panel-head"' in body
    assert "#bld-root.bld-has-block #bld-panel-head { display: none; }" in body


def test_ribbon_geometry_became_column_geometry():
    tpl = TPL.read_text()
    host = _segment(tpl, "#bld-editor-pane.bld-ribbon-open {", "}")
    assert "visibility: hidden" not in host, "панель-хозяин остаётся видимой"
    assert "pointer-events: none" not in host
    popup_rule = _segment(tpl, ".bld-ribbon-open #bld-block-popup {", "}")
    assert "position: fixed" not in popup_rule, "блок в потоке колонки, не fixed-лента"
    # мобильного bottom-sheet для ленты больше нет — лист даёт сама панель (<1024px)
    assert ".bld-ribbon-open #bld-block-popup { top: auto; left: 0; right: 0; bottom: 0;" not in tpl
    # верхняя строка не прячет статус/подсказку при выбранном блоке (место есть)
    assert "#bld-root.bld-has-block #bld-edit-hint" not in tpl


def test_open_block_looks_up_page_row_first_outside_home():
    """Грабля ТЗ: ключи секций страниц совпадают с секциями главной
    (services/events/stay_rooms/reviews) — на подстранице строку страницы искать РАНЬШЕ."""
    tpl = TPL.read_text()
    fn = _segment(tpl, "function openBlockPopup(key) {", "closeBlockPopup(false);")
    assert "var byPage = form.querySelector('.page-block[data-page-key=\"' + key + '\"]')" in fn
    assert "(byPage || byCb || byOrd)" in fn, "вне главной — строка страницы первой"
    assert "(byOrd || byCb || byPage)" in fn, "на главной — прежний порядок"
    assert "__stuIsHome" in fn


def test_open_block_focuses_the_sections_area_and_sets_the_crumb():
    tpl = TPL.read_text()
    fn = _segment(tpl, "function openBlockPopup(key) {", "return true;")
    assert 'secArea.classList.add("focus-on")' in fn
    assert "popupCrumb.textContent" in fn and "__stuPageLabel" in fn
    assert "window.__stuPageLabel = function" in tpl


def test_close_block_returns_to_the_page_level():
    tpl = TPL.read_text()
    fn = _segment(tpl, "function closeBlockPopup(restorePanel) {", "function syncRibbonPad")
    assert "showArea(curArea || (window.__stuPageArea ? window.__stuPageArea()" in fn
    # «‹» в крошке и «✕» — один и тот же путь назад к странице
    assert (
        'if (popupBack) popupBack.addEventListener("click", function () { closeBlockPopup(); });'
        in tpl
    )
    assert 'if (popupClose) popupClose.addEventListener("click", closeBlockPopup);' in tpl


def test_escape_chain_block_then_page_then_collapse():
    tpl = TPL.read_text()
    handler = _segment(tpl, 'if (e.key !== "Escape") return;', "});")
    assert "if (hadPopup) closeBlockPopup();" in handler
    assert re.search(r"if \(!hadPopup && [^\n]*\) closePanel\(\);", handler)


def test_dense_toggle_lives_in_the_more_menu():
    tpl = TPL.read_text()
    assert 'id="bld-dense-toggle"' in tpl
    js = _segment(tpl, 'getElementById("bld-dense-toggle")', "});")
    assert 'classList.toggle("bld-dense"' in js and "sf_editor_dense" in js


def test_cblock_rows_show_translated_labels():
    """ТЗ 12b: имена C-блоков — через CBLOCK_LABELS (переводимые), не сырой ключ."""
    from apps.core.templatetags.cabinet import cblock_label

    for key in siteconfig.REPEATABLE_BLOCKS + siteconfig.PAGE_REF_BLOCKS:
        assert key in siteconfig.CBLOCK_LABELS, key
        assert str(cblock_label(key)) == str(siteconfig.CBLOCK_LABELS[key]) != key
    assert cblock_label("weird_type") == "weird_type"  # мусор — как есть, не 500
    tenant = TenantFactory(
        slug="stcol2",
        name="StCol2",
        site_config={"sections": [{"key": "image_text", "id": "cbx1", "data": {"title": "T"}}]},
    )
    body = _html(tenant)
    assert 'data-cb-id="cbx1"' in body
    assert '<span class="font-medium">image_text</span>' not in body
    assert f'<span class="font-medium">{siteconfig.CBLOCK_LABELS["image_text"]}</span>' in body


def test_block_library_uses_the_same_label_registry():
    """Библиотека блоков (инсертер) и строки формы называют тип ОДНИМ словом."""
    body = _html(TenantFactory(slug="stcol3", name="StCol3"))
    buttons = re.findall(r'data-bt="([a-z_]+)"[^>]*>([^<]*)<', body)
    assert buttons, "инсертер обязан перечислять типы блоков"
    for value, text in buttons:
        assert str(siteconfig.CBLOCK_LABELS[value]) in text, (value, text)
