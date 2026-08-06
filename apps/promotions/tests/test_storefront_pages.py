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
