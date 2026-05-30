"""Тесты CRUD-вьюх каталога через RequestFactory (вызов view напрямую).

Урлы каталога живут в urls_tenant, но в тестах django-tenants работает в
public-схеме и TenantMainMiddleware форсит PUBLIC_SCHEMA_URLCONF → реальная
HTTP-маршрутизация на каталог даёт 404. Поэтому тестируем view-функции
напрямую, минуя роутинг и middleware.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory


def _attach_session_user(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="owner", email="owner@test.de", password="pw12345678"
    )


@pytest.mark.django_db
def test_list_requires_login():
    req = RequestFactory().get("/catalog/products/")
    _attach_session_user(req, AnonymousUser())
    resp = views.product_list(req)
    assert resp.status_code in (301, 302)  # redirect to login


@pytest.mark.django_db
def test_list_shows_products(user):
    ProductFactory(name={"de": "Brot", "en": "Bread"})
    req = RequestFactory().get("/catalog/products/")
    _attach_session_user(req, user)
    resp = views.product_list(req)
    assert resp.status_code == 200
    assert b"Brot" in resp.content


@pytest.mark.django_db
def test_create_product(user):
    cat = CategoryFactory()
    req = RequestFactory().post(
        "/catalog/products/new/",
        {
            "name_de": "Apfelstrudel",
            "name_en": "Apple strudel",
            "description_de": "",
            "description_en": "",
            "category": str(cat.pk),
            "base_price": "4.50",
            "currency": "EUR",
            "sku": "APF-1",
            "is_active": "on",
        },
    )
    _attach_session_user(req, user)
    resp = views.product_create(req)
    assert resp.status_code == 302
    p = Product.objects.get(sku="APF-1")
    assert p.name["de"] == "Apfelstrudel"
    assert p.category_id == cat.pk


@pytest.mark.django_db
def test_edit_product(user):
    p = ProductFactory(name={"de": "Alt", "en": ""}, base_price="1.00")
    req = RequestFactory().post(
        f"/catalog/products/{p.pk}/edit/",
        {
            "name_de": "Neu",
            "name_en": "",
            "description_de": "",
            "description_en": "",
            "base_price": "2.00",
            "currency": "EUR",
            "sku": "",
            "is_active": "on",
        },
    )
    _attach_session_user(req, user)
    resp = views.product_edit(req, pk=p.pk)
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.name["de"] == "Neu"
    assert str(p.base_price) == "2.00"


@pytest.mark.django_db
def test_delete_product_is_soft(user):
    p = ProductFactory()
    pk = p.pk
    req = RequestFactory().post(f"/catalog/products/{pk}/delete/")
    _attach_session_user(req, user)
    resp = views.product_delete(req, pk=pk)
    assert resp.status_code == 302
    assert not Product.objects.filter(pk=pk).exists()
    assert Product.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_search_filters_by_sku(user):
    ProductFactory(name={"de": "Brot"}, sku="AAA")
    ProductFactory(name={"de": "Kuchen"}, sku="BBB")
    req = RequestFactory().get("/catalog/products/", {"q": "AAA"})
    req.META["HTTP_HX_REQUEST"] = "true"
    _attach_session_user(req, user)
    resp = views.product_list(req)
    assert resp.status_code == 200
    assert b"AAA" in resp.content
    assert b"BBB" not in resp.content
