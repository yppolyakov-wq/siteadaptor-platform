"""Тесты CRUD-вьюх каталога через RequestFactory (вызов view напрямую).

Урлы каталога живут в urls_tenant, но в тестах django-tenants работает в
public-схеме и TenantMainMiddleware форсит PUBLIC_SCHEMA_URLCONF → реальная
HTTP-маршрутизация на каталог даёт 404. Поэтому тестируем view-функции
напрямую, минуя роутинг и middleware.
"""

import json

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


# --- SE-2c-3: инлайн-правка имени категории на канве ---------------------------


def _json_post(url, payload, user):
    req = RequestFactory().post(url, data=json.dumps(payload), content_type="application/json")
    return _attach_session_user(req, user)


@pytest.mark.django_db
def test_category_inline_edit_updates_name(user):
    cat = CategoryFactory(slug="brot", name={"de": "Brot", "en": "Bread"})
    req = _json_post(
        "/catalog/categories/inline-edit/",
        {"category_pk": str(cat.pk), "value": "Backwaren"},
        user,
    )
    assert views.category_inline_edit(req).status_code == 204
    cat.refresh_from_db()
    assert cat.name["de"] == "Backwaren" and cat.name["en"] == "Bread"  # en не затронут


@pytest.mark.django_db
def test_category_inline_edit_rejects_empty(user):
    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    req = _json_post(
        "/catalog/categories/inline-edit/", {"category_pk": str(cat.pk), "value": "  "}, user
    )
    assert views.category_inline_edit(req).status_code == 400
    cat.refresh_from_db()
    assert cat.name["de"] == "Brot"  # не изменилось


@pytest.mark.django_db
def test_category_inline_edit_rejects_bad_pk(user):
    req = _json_post(
        "/catalog/categories/inline-edit/", {"category_pk": "not-a-uuid", "value": "X"}, user
    )
    assert views.category_inline_edit(req).status_code == 400


# --- Фаза 1 (inline-content): правка текста товара на канве витрины ---


@pytest.mark.django_db
def test_product_inline_edit_updates_name(user):
    p = ProductFactory(name={"de": "Brot", "en": "Bread"})
    req = _json_post(
        "/catalog/products/inline-edit/",
        {"pk": str(p.pk), "field": "name", "value": "Vollkornbrot"},
        user,
    )
    assert views.product_inline_edit(req).status_code == 204
    p.refresh_from_db()
    assert p.name["de"] == "Vollkornbrot" and p.name["en"] == "Bread"  # en не затронут


@pytest.mark.django_db
def test_product_inline_edit_updates_description(user):
    p = ProductFactory(name={"de": "Brot"}, description={"de": "alt"})
    req = _json_post(
        "/catalog/products/inline-edit/",
        {"pk": str(p.pk), "field": "description", "value": "Frisch gebacken"},
        user,
    )
    assert views.product_inline_edit(req).status_code == 204
    p.refresh_from_db()
    assert p.description["de"] == "Frisch gebacken"


@pytest.mark.django_db
def test_product_inline_edit_rejects_empty_name(user):
    p = ProductFactory(name={"de": "Brot"})
    req = _json_post(
        "/catalog/products/inline-edit/", {"pk": str(p.pk), "field": "name", "value": "  "}, user
    )
    assert views.product_inline_edit(req).status_code == 400
    p.refresh_from_db()
    assert p.name["de"] == "Brot"  # не изменилось


@pytest.mark.django_db
def test_product_inline_edit_rejects_non_whitelisted_field(user):
    """Безопасность: вне вайтлиста (name/description/base_price) инлайн НЕ пишет."""
    p = ProductFactory(name={"de": "Brot"}, sku="OLD")
    req = _json_post(
        "/catalog/products/inline-edit/",
        {"pk": str(p.pk), "field": "sku", "value": "HACK"},
        user,
    )
    assert views.product_inline_edit(req).status_code == 400
    p.refresh_from_db()
    assert p.sku == "OLD"  # не тронуто


@pytest.mark.django_db
def test_product_inline_edit_updates_price(user):
    """#7-B: инлайн-цена товара без вариантов → base_price (Decimal), 204."""
    p = ProductFactory(name={"de": "Brot"}, base_price="5.00")
    req = _json_post(
        "/catalog/products/inline-edit/",
        {"pk": str(p.pk), "field": "base_price", "value": "3,50"},  # запятая → точка
        user,
    )
    assert views.product_inline_edit(req).status_code == 204
    p.refresh_from_db()
    assert str(p.base_price) == "3.50"


@pytest.mark.django_db
def test_product_inline_edit_price_rejects_variant_product(user):
    """#7-B: у товара с вариантами цена пер-вариант → инлайн отклоняет (правка в форме)."""
    from apps.catalog.models import ProductVariant

    p = ProductFactory(name={"de": "Tee"}, base_price="5.00")
    ProductVariant.objects.create(product=p, label="250 g", is_active=True)
    req = _json_post(
        "/catalog/products/inline-edit/",
        {"pk": str(p.pk), "field": "base_price", "value": "9.90"},
        user,
    )
    assert views.product_inline_edit(req).status_code == 400
    p.refresh_from_db()
    assert str(p.base_price) == "5.00"  # не тронуто


@pytest.mark.django_db
def test_product_inline_edit_price_rejects_invalid(user):
    """#7-B: нечисловая/отрицательная цена → 400, цена не меняется."""
    p = ProductFactory(name={"de": "Brot"}, base_price="5.00")
    for bad in ("abc", "-1", ""):
        req = _json_post(
            "/catalog/products/inline-edit/",
            {"pk": str(p.pk), "field": "base_price", "value": bad},
            user,
        )
        assert views.product_inline_edit(req).status_code == 400
    p.refresh_from_db()
    assert str(p.base_price) == "5.00"


@pytest.mark.django_db
def test_product_inline_edit_rejects_bad_pk(user):
    req = _json_post(
        "/catalog/products/inline-edit/", {"pk": "not-a-uuid", "field": "name", "value": "X"}, user
    )
    assert views.product_inline_edit(req).status_code == 400


@pytest.mark.django_db
def test_product_photo_edit_replaces_primary_in_place(tmp_path, settings, user):
    """📷 без image_id (карточка/одиночное фото) → замена ГЛАВНОГО фото В МЕСТЕ:
    кол-во не растёт, новое фото — primary (Product.images)."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import RequestFactory
    from PIL import Image

    settings.MEDIA_ROOT = str(tmp_path)
    p = ProductFactory(
        name={"de": "Brot"}, images=[{"id": "x", "url": "/old.png", "is_primary": True}]
    )
    buf = BytesIO()
    Image.new("RGB", (50, 50), "#abc").save(buf, format="PNG")
    req = RequestFactory().post("/catalog/products/photo-edit/", data={"pk": str(p.pk)})
    req.FILES["image"] = SimpleUploadedFile("ph.png", buf.getvalue(), content_type="image/png")
    _attach_session_user(req, user)
    assert views.product_photo_edit(req).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 1  # замена В МЕСТЕ, без дубля
    assert p.images[0]["is_primary"] and p.images[0]["url"] and p.images[0]["url"] != "/old.png"


@pytest.mark.django_db
def test_product_photo_edit_rejects_no_file(user):
    """M4: без файла (op=replace) → 400, фото не меняется."""
    p = ProductFactory(name={"de": "Brot"})
    req = RequestFactory().post("/catalog/products/photo-edit/", data={"pk": str(p.pk)})
    _attach_session_user(req, user)
    assert views.product_photo_edit(req).status_code == 400


def _photo_req(pk, *, op=None, image_id=None, with_file=True, user=None):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.test import RequestFactory
    from PIL import Image

    data = {"pk": str(pk)}
    if op:
        data["op"] = op
    if image_id is not None:
        data["image_id"] = image_id
    req = RequestFactory().post("/catalog/products/photo-edit/", data=data)
    if with_file:
        buf = BytesIO()
        Image.new("RGB", (40, 40), "#abc").save(buf, format="PNG")
        req.FILES["image"] = SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")
    _attach_session_user(req, user)
    return req


@pytest.mark.django_db
def test_product_photo_edit_op_replace_by_id(tmp_path, settings, user):
    """op=replace + image_id → заменён КОНКРЕТНЫЙ слайд, кол-во не меняется."""
    settings.MEDIA_ROOT = str(tmp_path)
    p = ProductFactory(
        name={"de": "Brot"},
        images=[
            {"id": "a", "url": "/a.png", "is_primary": True, "sort_order": 0},
            {"id": "b", "url": "/b.png", "is_primary": False, "sort_order": 1},
        ],
    )
    assert (
        views.product_photo_edit(
            _photo_req(p.pk, op="replace", image_id="b", user=user)
        ).status_code
        == 204
    )
    p.refresh_from_db()
    assert len(p.images) == 2
    assert p.images[1]["url"] != "/b.png" and p.images[0]["url"] == "/a.png"  # только слайд b


@pytest.mark.django_db
def test_product_photo_edit_op_add_and_remove(tmp_path, settings, user):
    """op=add добавляет фото; op=remove удаляет по id."""
    settings.MEDIA_ROOT = str(tmp_path)
    p = ProductFactory(
        name={"de": "Brot"},
        images=[{"id": "a", "url": "/a.png", "is_primary": True, "sort_order": 0}],
    )
    assert views.product_photo_edit(_photo_req(p.pk, op="add", user=user)).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 2  # добавлено
    new_id = next(i["id"] for i in p.images if i["id"] != "a")
    # удаляем добавленное (op=remove, без файла)
    rm = _photo_req(p.pk, op="remove", image_id=new_id, with_file=False, user=user)
    assert views.product_photo_edit(rm).status_code == 204
    p.refresh_from_db()
    assert len(p.images) == 1 and p.images[0]["id"] == "a" and p.images[0]["is_primary"]
