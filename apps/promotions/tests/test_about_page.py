"""S8: отдельная страница «О компании» /ueber-uns/ + цель меню page=about."""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants import menu
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_about_page_renders_text():
    tenant = TenantFactory(
        schema_name="public",
        slug="ab",
        name="AB",
        site_config={"about_title": "Wer wir sind", "about_text": "Vegan seit 2020"},
    )
    req = RequestFactory().get("/ueber-uns/")
    req.tenant = tenant
    body = public_views.about_page(req).content.decode()
    assert "Wer wir sind" in body and "Vegan seit 2020" in body


def test_menu_page_about_resolves_to_ueber_uns():
    tenant = TenantFactory.build(
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "Über uns", "type": "page", "target": "about"},
                    ]
                }
            }
        }
    )
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"] == "/ueber-uns/"
