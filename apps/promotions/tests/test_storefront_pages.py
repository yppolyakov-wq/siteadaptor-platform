"""ST-8: отдельные страницы витрины — галерея / отзывы / команда.

Запрос владельца: «не разделы на главной, а отдельные страницы». Гейт — по
НАЛИЧИЮ контента: пусто → 404, пункт меню гаснет (иначе меню вело бы в никуда).
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants import menu, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, tenant):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _tenant(**config):
    return TenantFactory.build(name="Hofladen", address="Feldweg 1", site_config=config)


# --- страницы доступны при наполнении ----------------------------------------


def test_gallery_page_renders_photos():
    tenant = _tenant(gallery=[{"id": "g1", "url": "https://img.test/a.jpg"}])
    html = public_views.gallery_page(_req("/galerie/", tenant)).content.decode()
    assert "https://img.test/a.jpg" in html


def test_gallery_page_renders_visitor_toggle_men23():
    """MEN-23: на /galerie/ — переключатель «сетка ↔ крупно» (class-swap,
    обработчик в _grid_view_script.html); контейнер несёт data-galv +
    целевые классы в data-cls-* (purge-safe)."""
    tenant = _tenant(gallery=[{"id": "g1", "url": "https://img.test/a.jpg"}])
    html = public_views.gallery_page(_req("/galerie/", tenant)).content.decode()
    assert 'data-galv="raster"' in html and 'data-galv-btn="gross"' in html
    assert 'data-cls-gross="grid gap-4 sm:grid-cols-2"' in html


def test_home_gallery_toggle_only_for_default_grid():
    """MEN-23: на главной переключатель — только у дефолт-сетки; авторские
    стили (strip/large/polaroid/soft) не переключаем."""
    from apps.promotions.public_views import storefront_home

    base = {"gallery": [{"id": "g1", "url": "https://img.test/a.jpg"}]}
    plain = _tenant(sections=[{"key": "gallery", "enabled": True}], **base)
    html = storefront_home(_req("/", plain)).content.decode()
    assert 'data-galv="raster"' in html and 'data-galv-btn="gross"' in html

    strip = _tenant(sections=[{"key": "gallery", "enabled": True, "style": "strip"}], **base)
    html2 = storefront_home(_req("/", strip)).content.decode()
    assert 'data-galv-btn="' not in html2 and 'data-galv="' not in html2


def test_team_page_renders_members():
    tenant = _tenant(team=[{"name": "Anna Berg", "role": "Meisterin", "photo": ""}])
    html = public_views.team_page(_req("/team/", tenant)).content.decode()
    assert "Anna Berg" in html and "Meisterin" in html


# --- пустой раздел не создаёт пустую страницу --------------------------------


def test_gallery_page_404_without_content():
    with pytest.raises(Http404):
        public_views.gallery_page(_req("/galerie/", _tenant()))


def test_team_page_404_without_content():
    with pytest.raises(Http404):
        public_views.team_page(_req("/team/", _tenant()))


def test_reviews_page_404_without_reviews():
    """Отзывы о бизнесе живут в SHARED-модели; без них страницы нет."""
    with pytest.raises(Http404):
        public_views.reviews_page(_req("/bewertungen/", _tenant()))


# --- меню: пункт появляется только при наполнении -----------------------------


def _resolve(tenant, target):
    node = {"label": "X", "type": "page", "target": target, "enabled": True, "children": []}
    return menu._node_url(tenant, node)


def test_menu_entry_appears_only_with_content():
    empty = _tenant()
    filled = _tenant(
        gallery=[{"id": "g1", "url": "https://img.test/a.jpg"}],
        team=[{"name": "Anna", "role": "", "photo": ""}],
    )
    assert _resolve(empty, "gallery") is None
    assert _resolve(empty, "team") is None
    assert _resolve(filled, "gallery") == "/galerie/"
    assert _resolve(filled, "team") == "/team/"


def test_about_menu_entry_is_not_gated():
    """Паритет: «О нас» ссылкой был всегда — гейт контента его не касается."""
    assert _resolve(_tenant(), "about") == "/ueber-uns/"


def test_new_nav_items_are_registered():
    """Пункты доступны владельцу в билдере меню (реестр NAV_ITEMS)."""
    keys = {key for key, _l, _u, _m in siteconfig.NAV_ITEMS}
    assert {"gallery", "team", "reviews"} <= keys


def test_demo_kits_use_pages_not_anchors():
    """Регрессия запроса владельца: у отеля/ресторана «Galerie»/«Bewertungen»
    были ЯКОРЯМИ на секции главной — теперь это страницы."""
    from apps.tenants import demo_kits

    for name in ("HOTEL_MENUS", "PRANASY_MENUS", "FRISEUR_MENUS"):
        items = getattr(demo_kits, name)["top"]["items"]
        anchors = [
            i for i in items if i.get("type") == "anchor" and "galerie" in str(i.get("target", ""))
        ]
        assert not anchors, f"{name}: галерея всё ещё якорь"
        targets = {i.get("target") for i in items if i.get("type") == "page"}
        assert "gallery" in targets or "reviews" in targets


# --- аудит 2026-08-06: страницы-сироты получили путь из меню -------------------


def test_orphan_pages_reachable_from_menu_when_module_active():
    """До аудита /treue/, /gutschein/, /kombi/, /konto/ существовали, но НИ ОДИН
    пункт меню на них не вёл — посетитель попадал только по прямой ссылке."""
    tenant = _tenant()
    tenant.disabled_modules = []
    assert _resolve(tenant, "loyalty") == "/treue/"
    assert _resolve(tenant, "account") == "/konto/"
    # gift дополнительно требует настроенной оплаты — см. отдельный замок ниже.


def test_orphan_menu_entries_gated_by_module():
    """Выключен модуль — пункт гаснет (иначе меню вело бы на 404)."""
    tenant = _tenant()
    tenant.disabled_modules = ["loyalty", "gift", "orders", "customer_account"]
    for target in ("loyalty", "gift", "combos", "account"):
        assert _resolve(tenant, target) is None, target


def test_combos_entry_needs_actual_combos():
    """Модуль orders активен почти у всех, а наборы есть у единиц: без гейта по
    контенту пункт «Kombi-Angebote» встал бы в шапку каждого тенанта и вёл на
    пустую страницу."""
    tenant = _tenant()
    tenant.disabled_modules = []
    assert _resolve(tenant, "combos") is None  # наборов нет → пункта нет


def test_gift_entry_requires_configured_payments():
    """`/gutschein/` отдаёт 404 не только без модуля, но и без настроенной
    онлайн-оплаты (`gift_purchase_active`). Гейт «только модуль» ставил в меню и
    на первый экран вход в 404 — у демо и у любого тенанта без Stripe."""
    tenant = _tenant()
    tenant.disabled_modules = []
    tenant.payments_enabled = False
    assert _resolve(tenant, "gift") is None


def test_gift_hero_tile_uses_the_same_gate_as_the_page():
    from apps.core import hero_tiles

    tenant = _tenant()
    tenant.disabled_modules = []
    tenant.payments_enabled = False
    for widget in ("friseur", "touren"):
        hrefs = [t["href"] for t in hero_tiles.tiles_for(widget, tenant)]
        assert "/gutschein/" not in hrefs, widget


def test_content_gates_query_once_per_request():
    """`resolve_menu` зовётся на КАЖДЫЙ рендер (шапка витрины, нижнее меню,
    контекст-процессор кабинета), а гейты reviews/combos ходят в БД. Без мемо это
    лишние запросы на каждой странице — считаем обращения к пробнику."""
    from apps.tenants import menu as menu_mod

    tenant = _tenant()
    calls = []
    original = menu_mod._content_probe
    menu_mod._content_probe = lambda t, target: (calls.append(target), False)[1]
    try:
        for _ in range(3):  # три резолва одного и того же тенанта
            menu_mod._page_has_content(tenant, "reviews")
            menu_mod._page_has_content(tenant, "combos")
    finally:
        menu_mod._content_probe = original
    assert calls == ["reviews", "combos"], calls


def test_content_gate_failure_hides_entry_instead_of_breaking_page():
    """Сбой чтения обязан гасить ПУНКТ, а не страницу (правило storefront_reviews)."""
    from unittest.mock import patch

    from apps.tenants import menu as menu_mod

    with patch("apps.catalog.models.Combo.objects") as objects:
        objects.filter.side_effect = RuntimeError("db down")
        assert menu_mod._content_probe(_tenant(), "combos") is False


def test_header_icon_pages_are_not_duplicated_in_nav():
    """У «Мой аккаунт» и «Merkzettel» уже есть иконки в шапке
    (_header_icons.html 👤/♥) — пункт меню был бы вторым входом в то же место."""
    keys = {key for key, _l, _u, _m in siteconfig.NAV_ITEMS}
    assert "account" not in keys and "wishlist" not in keys


def test_finder_menu_entry_requires_enabled_finder():
    """Finder — опция: пункт появляется только когда он включён владельцем
    (finder.enabled требует и флага, и primary_kind — см. apps/core/finder.py)."""
    from apps.core import finder

    tenant = _tenant()
    tenant.disabled_modules = []
    assert _resolve(tenant, "finder") is None  # по умолчанию выключен

    tenant.site_config = {"finder": {"enabled": True}}
    if finder.enabled(tenant):  # у типа есть primary-сущность
        assert _resolve(tenant, "finder") == "/finder/"
    else:  # без primary-сущности Finder не показывается — и пункта тоже нет
        assert _resolve(tenant, "finder") is None


# --- фидбэк 2026-08-07: дропдауны шапки открываются на тач-экране --------------


def test_more_dropdown_is_clickable_not_hover_only():
    """«Mehr ▾» раскрывалась ТОЛЬКО по hover/focus-within. На тач-экране hover
    нет, а Safari/iOS не отдаёт кнопке фокус по тапу — панель не открывалась
    («не работает и пустая при нажатии»). Группам меню клик добавили ещё
    2026-07-30; кнопке overflow — этим фиксом."""
    from django.template.loader import render_to_string

    html = render_to_string("storefront/_header_nav.html", {"storefront_menu": []})
    more = html[html.index('id="sf-nav-more"') :]
    assert "data-nav-group" in more, "кнопка Mehr без клик-обработчика"
    assert "data-nav-panel" in more, "панель Mehr не подключена к обработчику"


def test_nav_click_handler_restores_hidden_on_close():
    """Клик вне панели снимал только `block`, не возвращая `hidden` — у div
    остаётся display:block по умолчанию, поэтому панель не закрывалась."""
    from pathlib import Path

    base = Path("templates/storefront/_base.html").read_text(encoding="utf-8")
    # Срез от обработчика групп; «NAV-v2» как конец не годится — эта строка есть
    # и в комментарии выше по файлу (первая версия замка ловила пустой срез).
    start = base.index('e.target.closest("[data-nav-group]")')
    handler = base[start : start + 1200]
    assert 'classList.add("hidden")' in handler, "при закрытии не возвращается hidden"
    assert ".blur()" in handler, "фокус не снимается — group-focus-within держит панель"


def test_menu_editor_offers_every_page_target():
    """Аудит 2026-08-07: список страниц в редакторе меню был захардкожен как
    {home, about}. Узел с любой другой целью не находил себя в селекте, браузер
    выбирал первый пункт — и после Save «Galerie» начинала вести на главную.
    Реестр целей теперь один: новая страница появляется в редакторе сама."""
    from apps.tenants import menu as menu_mod

    choices = {c["value"] for c in menu_mod.page_target_choices()}
    targets = set(menu_mod._PAGE_URL_NAMES) - {"offers"}  # offers = легаси-алиас home
    assert targets <= choices, f"нет в редакторе меню: {sorted(targets - choices)}"
    assert all(c["label"] for c in menu_mod.page_target_choices()), "цель без подписи"


def test_gallery_toggle_absent_for_video_only_gallery():
    """Ревью MEN-23: у «только видео» контейнера data-galv нет — кнопки были бы
    мёртвыми. Гейт по site.gallery на главной И на /galerie/."""
    from apps.promotions.public_views import storefront_home

    tenant = _tenant(
        gallery_video="https://www.youtube.com/watch?v=x",
        sections=[{"key": "gallery", "enabled": True}],
    )
    html = public_views.gallery_page(_req("/galerie/", tenant)).content.decode()
    assert 'data-galv-btn="' not in html
    home = storefront_home(_req("/", tenant)).content.decode()
    assert 'data-galv-btn="' not in home
