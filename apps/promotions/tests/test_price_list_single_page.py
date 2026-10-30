"""Фидбэк 2026-10-30 (restaurant-demo /sortiment/, «Mehr anzeigen»): прайс-лист листает себя
сам, а серверная страница по 24 давала второй пейджер поверх и обрезала меню. В прайс-виде
каталог отдаёт всё меню одной страницей — для всех вариантов прайс-листа."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Product
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _render(preset):
    tenant = TenantFactory(
        schema_name="public",
        slug=f"pl-{preset}",
        disabled_modules=[],
        site_config={"catalog_layout": {"preset": preset}},
    )
    for i in range(30):
        Product.objects.create(name={"de": f"Gericht {i}"}, base_price="5.00")
    request = RequestFactory().get("/sortiment/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return public_views.product_list(request).content.decode()


@pytest.mark.parametrize("preset", ["preisliste", "preisliste_buch", "preisliste_foto"])
def test_price_list_shows_whole_menu_without_show_more(preset):
    html = _render(preset)
    assert "cursor=" not in html
    assert "Gericht 0" in html and "Gericht 29" in html


def test_grid_still_paginates():
    html = _render("cols3")
    assert "cursor=" in html
