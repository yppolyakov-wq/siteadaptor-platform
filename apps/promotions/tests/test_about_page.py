"""S8: отдельная страница «О компании» /ueber-uns/ + цель меню page=about."""

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
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


def test_about_page_inline_edit_markers_in_preview():
    """Part C: в превью редактора заголовок и текст «О нас» несут data-edit →
    правка прямо на канве (пустой текст тоже редактируем — рендерим placeholder-абзац)."""
    # Не public-схема: контекст-процессор is_preview активен только на тенанте-витрине.
    tenant = TenantFactory.build(slug="abp", name="ABP", site_config={})
    req = RequestFactory().get("/ueber-uns/?preview=1")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    body = public_views.about_page(req).content.decode()
    assert 'data-edit="about_title"' in body
    assert 'data-edit="about_text"' in body  # рендерится даже при пустом тексте (is_preview)


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
