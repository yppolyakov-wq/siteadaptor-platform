"""W11-5: страница «Site» → 302 на Studio (единственный вход «Website»).

Паритет достигнут ДО схлопывания (урок W10-6): quick-start (шаблоны + демо) —
область «Schnellstart» рейки, фон баннера/быстрый заказ — форма билдера, видео
галереи — область «Медиа»; галерея фото и контент-секции были общими и раньше.
Соседние экраны (SEO/обложки/раскладки/превью/меню) достижимы из Studio.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_site_redirects_to_studio():
    resp = views.site_view(_req("get", "/dashboard/site/"))
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/site/home/"


def test_site_redirect_carries_get():
    """Deep-link ?page= (T-6.1 «Edit design» с витрины) переживает редирект."""
    resp = views.site_view(_req("get", "/dashboard/site/", {"page": "/sortiment/"}))
    assert resp.status_code == 302
    loc = resp["Location"]
    assert loc.startswith("/dashboard/site/home/?")
    assert "page=%2Fsortiment%2F" in loc


def test_redirect_target_renders_end_to_end():
    """Цель редиректа — живой экран (не петля): Studio отдаёт 200 с канвой."""
    tenant = TenantFactory(schema_name="public", slug="w115", name="W115")
    resp = views.site_view(_req("get", "/dashboard/site/", tenant=tenant))
    target = resp["Location"].split("?")[0]
    assert target == "/dashboard/site/home/"

    req = _req("get", target, tenant=tenant)
    req.user = SimpleNamespace(is_authenticated=True)
    page = views.home_builder_view(req)
    assert page.status_code == 200
    html = page.content.decode()
    assert 'id="bld-root"' in html  # канва редактора
    assert 'id="st-rail"' not in html  # STU-12a: рейки нет
    assert 'id="st-page-switch"' in html  # верхняя строка «Seite ▾»


def test_studio_carries_all_site_page_functions():
    """Функции умершей страницы «Site» никуда не делись.

    STU-12g: глобальные из них (шаблоны витрины, демо-контент, быстрый заказ)
    переехали ещё раз — на экран кабинета «Design des Shops»; остальное живёт
    в Студии. Проверяем оба адреса, чтобы ни одна функция не потерялась.
    """
    tenant = TenantFactory(schema_name="public", slug="w115b", name="W115B", business_type="bakery")
    req = _req("get", "/dashboard/site/home/", tenant=tenant)
    req.user = SimpleNamespace(is_authenticated=True)
    html = views.home_builder_view(req).content.decode()

    assert 'name="hero_image"' in html  # фон баннера
    assert 'name="gallery_video"' in html  # видео галереи
    assert 'value="upload_gallery"' in html  # фото галереи (было и раньше)
    # LAY-1b: FAQ — пары полей вместо одной textarea (запрос владельца).
    assert 'name="faq_q_0"' in html  # контент-секции (общий партиал)

    from apps.core import design_page

    dreq = _req("get", "/dashboard/design/", tenant=tenant)
    dreq.user = SimpleNamespace(is_authenticated=True)
    design = design_page.design_view(dreq).content.decode()
    assert 'value="apply_template"' in design  # шаблоны витрины
    assert 'value="load_demo"' in design or 'value="clear_demo"' in design  # демо-контент
    assert 'name="quick_add"' in design  # быстрый заказ на карточках


def test_website_anchor_points_at_studio():
    """Якорь сайдбара/палитры «Website» ведёт прямо в Studio."""
    from apps.core import nav_registry

    anchor = next(a for a in nav_registry.ANCHORS if a.nav_key == "site")
    assert anchor.url_name == "site-home"
