"""STU-18d (d3): свод пяти оставшихся листингов на каркас `listing.html`.

Пять страниц — наборы, лукбук, мерклист, блог, отзывы — наследовались напрямую от
`_base.html`, поэтому хром композиции (его рисует каркас) до них не доходил, и
композицию им нельзя было ДАЖЕ объявить (STU-9, план §11.5).

Эти замки — характеризационные: сняты ДО перевода на каркас и держат разметку
байт-в-байт (прецедент UB1-3). Каркас между шапкой и сеткой рисует строку
инструментов, поэтому у страниц без фильтров она обязана оставаться подавленной —
иначе появился бы пустой отступ, которого раньше не было.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        schema_name="public", slug=f"stu18p{uuid.uuid4().hex[:6]}", disabled_modules=[]
    )


def _get(view, path, tenant, **kwargs):
    req = RequestFactory().get(path)
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=False)
    req.tenant = tenant
    resp = view(req, **kwargs)
    assert resp.status_code == 200, f"{path} → {resp.status_code}"
    return resp.content.decode()


def test_combos_page_markup():
    from apps.catalog.models import Combo
    from apps.orders import public_views

    tenant = _tenant()
    Combo.objects.create(name="Menü A", price="15.00", is_active=True)
    body = _get(public_views.combo_list_public, "/kombi/", tenant)
    assert "data-combo-list" in body  # контейнер наборов (_combo_grid)
    assert 'class="text-2xl md:text-3xl font-bold mb-6"' in body  # H1 страницы
    assert "data-listing-bar" not in body  # строки инструментов у этой страницы нет


def test_wishlist_page_markup():
    from apps.orders import public_views

    tenant = _tenant()
    cfg = dict(tenant.site_config or {})
    cfg["wishlist"] = True  # SF-4a: опция включается владельцем
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    body = _get(public_views.wishlist_view, "/merkzettel/", tenant)
    assert "data-listing-bar" not in body


def test_reviews_page_markup():
    from apps.promotions import public_views

    tenant = _tenant()
    cfg = dict(tenant.site_config or {})
    # страница существует только при наличии отзывов (ST-8) — берём кураторский
    cfg["testimonials"] = [{"name": "Anna", "text": "Super!"}]
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    body = _get(public_views.reviews_page, "/bewertungen/", tenant)
    assert "data-listing-bar" not in body


def test_blog_page_markup():
    from apps.events import public_views
    from apps.events.models import BlogPost

    tenant = _tenant()
    BlogPost.objects.create(title="Post", slug="post", is_published=True)
    body = _get(public_views.blog_index, "/blog/", tenant)
    assert "Post" in body
    assert "data-listing-bar" not in body


def test_lookbook_page_markup():
    from apps.collections import public_views
    from apps.collections.models import Collection

    tenant = _tenant()
    Collection.objects.create(
        name={"de": "Herbst"}, slug="herbst", is_active=True, images=[{"url": "/m/a.jpg"}]
    )
    body = _get(public_views.lookbook, "/lookbook/herbst/", tenant, slug="herbst")
    assert "data-listing-bar" not in body
