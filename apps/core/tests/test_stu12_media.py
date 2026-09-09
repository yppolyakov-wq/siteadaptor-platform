"""STU-12f: колонка «Medien» + вход в медиа кликом по канве + «＋ Kategorie» с плашки.

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12f): четыре out-of-form
области медиа (галерея · баннер · обложки · логотип) собираются в ОДНУ колонку
аккордеоном; вход — клик по самому медиа на канве (витрина помечает слоты); каждая
форма несёт `page_path`, поэтому после загрузки канва возвращается на ТУ ЖЕ страницу
(сегодня любой аплоад выкидывал на главную). «＋ Kategorie» доступна с плашки действий
секции «Kategorien».

⚠️ Имя атрибута: `data-sf-media` УЖЕ занято — это форма фото витрины (round|wide) на
`<body>`, и она под замком `test_looks`. Слоты медиа помечаем `data-sf-media-slot`.
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

# действие формы → достаточный набор полей POST (без файлов — проверяем ВОЗВРАТ, не загрузку)
MEDIA_ACTIONS = (
    ("delete_gallery_image", {"image_id": "nope"}),
    ("save_gallery_video", {"gallery_video": ""}),
    ("delete_logo", {}),
    ("save_hero_slide", {"slide_index": ""}),
    ("delete_hero_slide", {"slide_index": "0"}),
    ("move_hero_slide", {"slide_index": "0", "dir": "up"}),
)


def _req(method, path, tenant, data=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _builder(tenant):
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _segment(body, start_marker, end_marker):
    i = body.index(start_marker)
    return body[i : body.index(end_marker, i)]


def test_media_areas_live_in_one_column():
    """Четыре области медиа — части ОДНОЙ колонки, а не четыре разных экрана."""
    body = _builder(TenantFactory(slug="stmd1", name="StMd1"))
    col = _segment(body, 'data-bld-area="media"', 'data-bld-area="catalog-add"')
    for part in ("gallery", "logo", "banner", "covers"):
        assert f'data-media-part="{part}"' in col, part
    # прежние имена областей сохранены — по ним ходят существующие входы и замки
    for area in ("gallery-media", "logo-media", "banner-media", "covers-media"):
        assert f'data-bld-area="{area}"' in col, area


def test_show_area_resolves_media_parts_to_the_column():
    tpl = TPL.read_text(encoding="utf-8")
    fn = _segment(tpl, "function showArea(", "window.__sfOpenArea")
    assert "MEDIA_PARTS" in fn, "части медиа резолвятся в колонку «media»"
    # части медиа вложены в колонку и НЕ переключаются как самостоятельные области
    # (иначе показ «media» тут же погасил бы её содержимое); прочие области — на разной
    # глубине (theme/sections/page/menu лежат внутри #home-form), поэтому фильтр по
    # вложенности, а не по уровню — найдено скриншотом стенда.
    areas = _segment(tpl, "var areas = edPane", "var isNarrow")
    assert "closest('[data-bld-area=\"media\"]')" in areas
    assert ":scope >" not in areas, "фильтр по уровню гасил бы theme/sections/page/menu"


def test_every_media_form_carries_the_page_path():
    """Аплоад с подстраницы обязан вернуть канву на ту же страницу."""
    body = _builder(TenantFactory(slug="stmd2", name="StMd2"))
    col = _segment(body, 'data-bld-area="media"', 'data-bld-area="catalog-add"')
    forms = re.findall(r"<form\b.*?</form>", col, re.S)
    assert len(forms) >= 5, len(forms)
    for f in forms:
        action = re.search(r'name="action" value="([a-z_]+)"', f)
        assert 'name="page_path"' in f, action.group(1) if action else f[:120]


def test_media_actions_return_to_the_same_canvas_page():
    tenant = TenantFactory(slug="stmd3", name="StMd3")
    for action, extra in MEDIA_ACTIONS:
        data = {"action": action, "page_path": "/sortiment/", **extra}
        resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, data))
        assert resp.status_code == 302, action
        assert "page=/sortiment/" in resp["Location"], f"{action}: {resp['Location']}"


def test_add_category_returns_to_the_same_page_too():
    tenant = TenantFactory(slug="stmd4", name="StMd4")
    resp = views.home_builder_view(
        _req(
            "post",
            "/dashboard/site/home/",
            tenant,
            {"action": "add_category", "name_de": "Neu", "page_path": "/sortiment/"},
        )
    )
    assert resp.status_code == 302
    assert "page=/sortiment/" in resp["Location"], resp["Location"]


def test_storefront_marks_media_slots():
    """Витрина помечает медиа-слоты, чтобы клик по ним открывал их настройки."""
    gallery = pathlib.Path("templates/storefront/sections/_gallery.html").read_text(
        encoding="utf-8"
    )
    hero = pathlib.Path("templates/storefront/sections/_hero.html").read_text(encoding="utf-8")
    logo = pathlib.Path("templates/storefront/_header_logo.html").read_text(encoding="utf-8")
    cover = pathlib.Path("templates/storefront/_archetype_cover.html").read_text(encoding="utf-8")
    assert 'data-sf-media-slot="gallery"' in gallery
    assert 'data-sf-media-slot="hero"' in hero
    assert 'data-sf-media-slot="logo"' in logo
    assert 'data-sf-media-slot="cover:' in cover
    # имя формы фото витрины (round|wide) НЕ трогаем — оно под замком test_looks
    for tpl in (gallery, hero, logo, cover):
        assert 'data-sf-media="' not in tpl


def test_canvas_click_routes_media_slots_before_header():
    """Логотип лежит ВНУТРИ шапки — ветка медиа обязана идти раньше ветки header."""
    tpl = TPL.read_text(encoding="utf-8")
    handler = _segment(tpl, 'sec.addEventListener("click"', "if (opened) return;")
    i_media = handler.index("openMediaSlot(e)")
    i_links = handler.index('closest("a,button,input,textarea,select,[contenteditable]")')
    i_header = handler.index('key === "header"')
    assert i_media < i_links < i_header, "медиа-слот — до отсечки ссылок и до шапки"
    # сам резолвер знает атрибут слота и уводит в колонку «Медиа»
    resolver = _segment(tpl, "function openMediaSlot(", "bindCanvasContent(doc);")
    assert "data-sf-media-slot" in resolver and "__sfShowArea" in resolver
    for area in ("gallery-media", "logo-media", "banner-media", "covers-media"):
        assert area in resolver, area


def test_action_bar_offers_add_category_for_the_categories_block():
    body = _builder(TenantFactory(slug="stmd5", name="StMd5"))
    bar = _segment(body, 'id="bld-action-bar"', 'id="bld-quick-pop"')
    assert 'data-ab="addcat"' in bar
    tpl = TPL.read_text(encoding="utf-8")
    sync = _segment(tpl, "function syncBar(", "function ensureFrameHooks(")
    assert '"addcat"' in sync, "кнопка видна только у секции с категориями"
