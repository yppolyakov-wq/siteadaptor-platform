"""Track C1: публичный каталог на витрине (список, карточка, превью, sitemap)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/sortiment/", params=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return request


def test_product_list_shows_active_only():
    ProductFactory(name={"de": "AktivBrot"})
    ProductFactory(name={"de": "VerstecktBrot"}, is_active=False)
    deleted = ProductFactory(name={"de": "WegBrot"})
    deleted.delete()  # soft-delete

    body = public_views.product_list(_req()).content.decode()
    assert "AktivBrot" in body
    assert "VerstecktBrot" not in body
    assert "WegBrot" not in body


def test_product_list_filters_by_category():
    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "Roggenbrot"}, category=cat)
    ProductFactory(name={"de": "Kuchenstück"})

    body = public_views.product_list(_req(params={"kategorie": "brot"})).content.decode()
    assert "Roggenbrot" in body
    assert "Kuchenstück" not in body


def test_unknown_category_redirects_to_full_list():
    resp = public_views.product_list(_req(params={"kategorie": "ghost"}))
    assert resp.status_code == 302
    assert resp.url == "/sortiment/"


def test_product_detail_renders_price_and_contacts():
    product = ProductFactory(
        name={"de": "Roggenbrot"}, description={"de": "Frisch gebacken"}, base_price="4.20"
    )
    body = public_views.product_detail(_req(f"/sortiment/{product.pk}/"), pk=product.pk)
    body = body.content.decode()
    assert "Roggenbrot" in body
    assert "4,20" in body  # DE-локаль: запятая
    assert "Frisch gebacken" in body
    assert "Hauptstr. 1" in body  # офлайн-покупка: контакты бизнеса


def test_product_detail_uses_shared_media_gallery():
    """M20U-4: карточка товара переиспользует общую галерею (большое+миниатюры)."""
    product = ProductFactory(
        name={"de": "Roggenbrot"},
        images=[
            {"id": "a", "url": "https://img/a.jpg", "is_primary": True},
            {"id": "b", "url": "https://img/b.jpg"},
        ],
    )
    body = public_views.product_detail(
        _req(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "js-media-gallery" in body and 'data-src="https://img/b.jpg"' in body


def test_product_detail_404_for_inactive():
    product = ProductFactory(is_active=False)
    with pytest.raises(Http404):
        public_views.product_detail(_req(), pk=product.pk)


def test_home_categories_section_when_enabled():
    """M20U-2: секция категорий на главной — карточки top-level → каталог с фильтром."""
    CategoryFactory(slug="brot", name={"de": "Brot"}, sort_order=1)
    CategoryFactory(slug="kuchen", name={"de": "Kuchen"}, sort_order=2)
    req = _req("/")
    req.tenant.site_config = {"sections": [{"key": "categories", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    assert "Brot" in body and "Kuchen" in body
    assert "kategorie=brot" in body  # ссылка на каталог с фильтром


def test_home_categories_section_hidden_by_default():
    CategoryFactory(slug="brot", name={"de": "Brot"})
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "kategorie=brot" not in body  # секция выкл по умолчанию


def test_home_events_section_when_enabled():
    """M20U-2: секция мероприятий на главной — ближайшие события grid → /veranstaltung/."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import Event

    Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
    )
    req = _req("/")
    req.tenant = TenantFactory.build(disabled_modules=[])  # все модули активны
    req.tenant.site_config = {"sections": [{"key": "events", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    assert "Yoga-Retreat" in body and "/veranstaltung/" in body


def test_home_shows_products_preview():
    ProductFactory(name={"de": "VorschauBrot"})
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "VorschauBrot" in body
    assert "/sortiment/" in body


def test_home_without_products_has_no_section():
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "/sortiment/</a>" not in body  # ссылки «View all» нет без товаров


def test_sitemap_includes_products():
    product = ProductFactory()
    body = public_views.sitemap_xml(_req("/sitemap.xml")).content.decode()
    assert "/sortiment/</loc>" in body
    assert f"/sortiment/{product.pk}/" in body


def test_sitemap_without_products_skips_section():
    body = public_views.sitemap_xml(_req("/sitemap.xml")).content.decode()
    assert "/sortiment/" not in body


def test_contact_section_embeds_map_with_coords():
    """T1: при заданных координатах в секции контактов встроена карта Leaflet."""
    from decimal import Decimal

    req = _req("/")
    req.tenant.latitude = Decimal("51.1700000")
    req.tenant.longitude = Decimal("6.9400000")
    body = public_views.storefront_home(req).content.decode()
    assert "sf-contact-map" in body
    assert "leaflet" in body.lower()


def test_contact_section_without_coords_has_no_map():
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "sf-contact-map" not in body


def test_storefront_includes_telegram_miniapp_sdk():
    """TG2: витрина подключает Telegram Web App SDK (Mini App)."""
    ProductFactory(name={"de": "AktivBrot"})
    body = public_views.product_list(_req()).content.decode()
    assert "telegram.org/js/telegram-web-app.js" in body
    assert "in-telegram" in body  # init-скрипт присутствует
