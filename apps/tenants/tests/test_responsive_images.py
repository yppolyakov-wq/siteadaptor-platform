"""P5: responsive images — preload hero-фото (LCP) + lazy/decoding атрибуты."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _render(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def test_hero_image_is_preloaded_when_hero_enabled():
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": True}],
            "hero_image": "https://img.test/banner.jpg",
        }
    )
    body = _render(tenant)
    assert 'rel="preload"' in body
    assert 'as="image"' in body
    assert "https://img.test/banner.jpg" in body
    assert 'fetchpriority="high"' in body


def test_no_preload_without_hero_image():
    tenant = TenantFactory.build(site_config={"sections": [{"key": "hero", "enabled": True}]})
    assert 'rel="preload"' not in _render(tenant)


def test_no_preload_when_hero_section_disabled():
    # Фото задано, но секция выключена → preload зря тянул бы картинку.
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "hero", "enabled": False}],
            "hero_image": "https://img.test/banner.jpg",
        }
    )
    assert 'rel="preload"' not in _render(tenant)


def test_product_card_uses_lazy_and_async_decoding():
    # Карточка товара — offscreen, грузим лениво и декодируем асинхронно (P5).
    from apps.catalog.images import save_product_image
    from apps.catalog.tests.factories import ProductFactory
    from apps.catalog.tests.test_images import _png

    product = ProductFactory(name={"de": "Brötchen"})
    product.images = [save_product_image(_png(), is_primary=True)]
    product.save(update_fields=["images"])

    body = _render(TenantFactory.build(name="Bäckerei X"))
    assert "Brötchen" in body
    assert 'loading="lazy"' in body
    assert 'decoding="async"' in body
