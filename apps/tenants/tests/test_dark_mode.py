"""P5c: тёмная тема витрины — переключатель, no-FOUC init, карта цветов."""

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _render():
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(name="Bäckerei X")
    return public_views.storefront_home(req).content.decode()


def test_storefront_has_theme_toggle_and_init():
    body = _render()
    # кнопка-переключатель в шапке
    assert 'id="sf-theme-toggle"' in body
    # ранний init без мигания: localStorage + системная тема
    assert 'localStorage.getItem("sf-theme")' in body
    assert "prefers-color-scheme: dark" in body
    # регресс: многострочный {# #} утекает текстом — комментарий не должен
    # попадать в HTML (используем {% comment %}).
    assert "ставим класс до отрисовки" not in body


def test_compiled_css_has_dark_override_map():
    # Карта тёмных цветов входит в собранный бандл (CI-гейт держит свежесть).
    css = Path(settings.BASE_DIR, "static", "css", "app.css").read_text()
    assert ".dark .bg-white{" in css
    assert ".dark .text-gray-900{color:#f3f4f6}" in css
