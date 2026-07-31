"""M4-C «Merkzettel» (план m4-boutique-plan-2026-07-30 §C): список отложенного
в СЕССИИ — 0 миграций, без аккаунта, ничего о посетителе в БД."""

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.orders import public_views, wishlist
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(method="get", path="/merkzettel/", data=None, business_type="clothing"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type=business_type, disabled_modules=[])
    return request


def _product(name="Wollmantel"):
    return Product.objects.create(name={"de": name}, base_price="129.00", is_active=True)


def test_toggle_adds_and_removes():
    request = _req()
    product = _product()
    assert wishlist.toggle(request, product.pk) is True
    assert wishlist.has(request, product.pk) and wishlist.count(request) == 1
    assert wishlist.toggle(request, product.pk) is False
    assert wishlist.count(request) == 0


def test_newest_first_and_capped():
    request = _req()
    for i in range(wishlist.WISH_MAX + 5):
        wishlist.toggle(request, f"pk-{i}")
    assert wishlist.count(request) == wishlist.WISH_MAX
    assert wishlist.ids(request)[0] == f"pk-{wishlist.WISH_MAX + 4}"  # новое первым


def test_products_skips_deleted_and_inactive():
    """Товар мог быть скрыт после добавления — список не падает и не показывает его."""
    request = _req()
    live, hidden = _product("Mantel"), _product("Weg")
    hidden.is_active = False
    hidden.save(update_fields=["is_active"])
    for pk in (live.pk, hidden.pk, "00000000-0000-0000-0000-000000000000"):
        wishlist.toggle(request, pk)
    assert list(wishlist.products(request)) == [live]


def test_enabled_by_archetype_and_override():
    assert wishlist.enabled(TenantFactory.build(business_type="clothing")) is True
    assert wishlist.enabled(TenantFactory.build(business_type="restaurant")) is False
    # явный тумблер сильнее архетипа в обе стороны
    assert wishlist.enabled(
        TenantFactory.build(business_type="restaurant", site_config={"wishlist": True})
    )
    assert not wishlist.enabled(
        TenantFactory.build(business_type="clothing", site_config={"wishlist": False})
    )


def test_view_404_when_disabled(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    with pytest.raises(Http404):
        public_views.wishlist_view(_req(business_type="restaurant"))


def test_ajax_toggle_returns_state_and_count(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    product = _product()
    request = _req("post", f"/merkzettel/{product.pk}/")
    request.headers = {"X-Requested-With": "fetch"}
    response = public_views.wishlist_toggle(request, product.pk)
    assert response.status_code == 200
    import json

    body = json.loads(response.content)
    assert body["on"] is True and body["count"] == 1


def test_page_renders_saved_products(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    request = _req()
    product = _product()
    wishlist.toggle(request, product.pk)
    body = public_views.wishlist_view(request).content.decode()
    assert "Wollmantel" in body


def test_heart_hidden_for_non_retail(settings):
    """Гастро/услуги сердечко не показывают — задача посетителя там другая."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    product = _product()
    on = render_to_string(
        "storefront/_wish_heart.html",
        {"p": product, "storefront_wishlist_enabled": True, "storefront_wishlist_ids": []},
    )
    off = render_to_string(
        "storefront/_wish_heart.html", {"p": product, "storefront_wishlist_enabled": False}
    )
    assert "data-wish-form" in on and "♡" in on
    assert off.strip() == ""
