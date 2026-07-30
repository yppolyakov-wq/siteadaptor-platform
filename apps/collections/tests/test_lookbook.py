"""M4-B Lookbook (план m4-boutique-plan-2026-07-30 §B): подборки товаров —
фасет каталога, страница образа, кабинет."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog.models import Product
from apps.collections.models import Collection
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

IMG = [{"id": "a1", "url": "/media/demo/look.webp", "is_primary": True, "sort_order": 0}]


def _req(path="/", method="get", data=None, tenant=None, login=True):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if login:
        request.user = get_user_model().objects.create_user(
            username=f"o-{uuid.uuid4().hex[:8]}", password="pw12345678"
        )
    request.tenant = tenant or TenantFactory.build(business_type="mode", disabled_modules=[])
    return request


def _product(name="Wollmantel"):
    # Product.name — JSONField {"de": …}; плоская строка ломает name_localized.
    return Product.objects.create(name={"de": name}, base_price="129.00", is_active=True)


def test_lookbook_page_shows_gallery_and_products(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.collections.public_views import lookbook

    col = Collection.objects.create(name="Herbst-Looks", slug="herbst-looks", images=IMG)
    col.products.add(_product())
    body = lookbook(_req(), slug="herbst-looks").content.decode()
    assert "Herbst-Looks" in body
    assert "/media/demo/look.webp" in body
    assert "Wollmantel" in body


def test_lookbook_without_photo_is_404(settings):
    """Подборка без фото остаётся обычным фасет-чипом — страницы «лука» нет."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.http import Http404

    from apps.collections.public_views import lookbook

    Collection.objects.create(name="Nur Filter", slug="nur-filter")
    with pytest.raises(Http404):
        lookbook(_req(), slug="nur-filter")


def test_inactive_collection_is_404(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.http import Http404

    from apps.collections.public_views import lookbook

    Collection.objects.create(name="Aus", slug="aus", images=IMG, is_active=False)
    with pytest.raises(Http404):
        lookbook(_req(), slug="aus")


def test_catalog_facet_filters_by_collection():
    from apps.catalog.facets import CatalogFacets

    col = Collection.objects.create(name="Herbst", slug="herbst")
    inside, outside = _product("Mantel"), _product("Shorts")
    col.products.add(inside)
    items = CatalogFacets().apply(Product.objects.all(), {"kollektion": "herbst"})
    assert list(items) == [inside]
    assert outside not in items


def test_inactive_collection_not_filtered_out_silently():
    """Выключенная подборка не отдаёт товары (иначе мёртвая ссылка показывала бы
    выдачу так, будто фильтр работает)."""
    from apps.catalog.facets import CatalogFacets

    col = Collection.objects.create(name="Aus", slug="aus", is_active=False)
    col.products.add(_product())
    assert list(CatalogFacets().apply(Product.objects.all(), {"kollektion": "aus"})) == []


def test_facet_chips_only_for_collections_with_products():
    from apps.catalog.facets import CatalogFacets

    with_products = Collection.objects.create(name="Herbst", slug="herbst")
    Collection.objects.create(name="Leer", slug="leer")
    with_products.products.add(_product())
    chips = CatalogFacets().present(Product.objects.filter(is_active=True), {})["collection_chips"]
    assert [c["slug"] for c in chips] == ["herbst"]


def test_cabinet_assigns_products_and_uploads_photo(settings):
    """Кабинет: чекбоксы товаров (presence-guard) + вход в лукбук после фото."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.collections.views import collections_view

    col = Collection.objects.create(name="Herbst", slug="herbst")
    product = _product()
    resp = collections_view(
        _req(
            "/dashboard/collections/",
            "post",
            {
                "action": "update",
                "collection": str(col.pk),
                "name": "Herbst",
                "products_present": "1",
                "products": [str(product.pk)],
            },
        )
    )
    assert resp.status_code == 302
    assert list(col.products.all()) == [product]

    # Частичная форма БЕЗ products_present не должна очищать состав.
    collections_view(
        _req(
            "/dashboard/collections/",
            "post",
            {"action": "update", "collection": str(col.pk), "name": "Herbst"},
        )
    )
    assert list(col.products.all()) == [product]


def test_cabinet_page_open_for_catalog_only_tenant(settings):
    """Раньше страница подборок была 404 без booking/stays — бутик её не видел."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.collections.views import collections_view

    tenant = TenantFactory.build(business_type="mode", disabled_modules=["booking", "stays"])
    Collection.objects.create(name="Herbst", slug="herbst")
    _product()
    body = collections_view(_req("/dashboard/collections/", tenant=tenant)).content.decode()
    assert "Products in this collection" in body
    assert "Wollmantel" in body


def test_lookbook_url_is_registered(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    assert reverse("storefront-lookbook", args=["herbst"]) == "/lookbook/herbst/"
