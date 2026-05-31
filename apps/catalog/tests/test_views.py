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
from apps.catalog.forms import CategoryForm
from apps.catalog.models import Category, Product
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


# --- категории ------------------------------------------------------------


def _post(url, data, user):
    req = RequestFactory().post(url, data)
    _attach_session_user(req, user)
    return req


@pytest.mark.django_db
def test_create_category_autoslug(user):
    req = _post(
        "/catalog/categories/new/",
        {"name_de": "Brot & Brötchen", "name_en": "", "slug": "", "icon": "", "sort_order": "0"},
        user,
    )
    resp = views.category_create(req)
    assert resp.status_code == 302
    cat = Category.objects.get()
    assert cat.name["de"] == "Brot & Brötchen"
    assert cat.slug == "brot-brotchen"  # сгенерирован из name_de


@pytest.mark.django_db
def test_category_list_is_nested(user):
    parent = CategoryFactory(name={"de": "Backwaren"}, slug="backwaren")
    CategoryFactory(name={"de": "Kuchen"}, slug="kuchen", parent=parent)
    req = RequestFactory().get("/catalog/categories/")
    _attach_session_user(req, user)
    resp = views.category_list(req)
    assert resp.status_code == 200
    assert b"Backwaren" in resp.content
    assert b"Kuchen" in resp.content


@pytest.mark.django_db
def test_parent_cycle_rejected():
    parent = CategoryFactory()
    child = CategoryFactory(parent=parent)
    form = CategoryForm(
        data={
            "name_de": "X",
            "name_en": "",
            "slug": "",
            "icon": "",
            "sort_order": "0",
            "parent": str(child.pk),  # потомок как родитель → цикл
        },
        instance=parent,
    )
    assert not form.is_valid()
    assert "parent" in form.errors


@pytest.mark.django_db
def test_delete_simple_category_is_soft(user):
    cat = CategoryFactory()
    pk = cat.pk
    resp = views.category_delete(_post(f"/catalog/categories/{pk}/delete/", {}, user), pk=pk)
    assert resp.status_code == 302
    assert not Category.objects.filter(pk=pk).exists()
    assert Category.all_objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_delete_reparent(user):
    grandparent = CategoryFactory(slug="gp")
    parent = CategoryFactory(slug="p", parent=grandparent)
    child = CategoryFactory(slug="c", parent=parent)
    prod = ProductFactory(category=parent)

    resp = views.category_delete(
        _post(f"/catalog/categories/{parent.pk}/delete/", {"strategy": "reparent"}, user),
        pk=parent.pk,
    )
    assert resp.status_code == 302
    assert not Category.objects.filter(pk=parent.pk).exists()  # parent soft-deleted
    child.refresh_from_db()
    assert child.parent_id == grandparent.pk  # ребёнок поднят к деду
    prod.refresh_from_db()
    assert prod.category_id is None  # товар отвязан


@pytest.mark.django_db
def test_delete_cascade(user):
    parent = CategoryFactory(slug="p")
    child = CategoryFactory(slug="c", parent=parent)
    prod = ProductFactory(category=child)

    resp = views.category_delete(
        _post(f"/catalog/categories/{parent.pk}/delete/", {"strategy": "cascade"}, user),
        pk=parent.pk,
    )
    assert resp.status_code == 302
    assert not Category.objects.filter(pk__in=[parent.pk, child.pk]).exists()
    assert Category.all_objects.filter(pk=child.pk).exists()  # soft, не hard
    prod.refresh_from_db()
    assert prod.category_id is None
