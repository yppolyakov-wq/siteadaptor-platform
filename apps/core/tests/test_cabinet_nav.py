"""Сайдбар кабинета владельца: иконки модулей + групп-заголовки (S3).

Навигация собирается из реестра модулей (context-processor modules_nav по
request.tenant). Рендерим дашборд напрямую через RequestFactory (urls_tenant как
ROOT_URLCONF, чтобы reverse пунктов меню разрешался).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.views import dashboard
from apps.tenants.tests.factories import TenantFactory


def _request(rf, user, tenant):
    request = rf.get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


@pytest.mark.django_db
def test_dashboard_nav_shows_icons_and_group_headers(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    # disabled_modules=[] → активны все модули (в т.ч. многопунктовые).
    tenant = TenantFactory(schema_name="t_nav", name="Nav Co", disabled_modules=[])
    user = get_user_model().objects.create_user("o", "o@test.de", "pw12345678")

    # render() shortcut уже вернул отрендеренный ответ (исключение бы упало здесь).
    resp = dashboard(_request(rf, user, tenant))
    html = resp.content.decode()

    # Иконка модуля рядом с пунктом (Katalog & Import).
    assert "📦" in html
    # Групп-заголовки модулей с несколькими пунктами (& → &amp; в HTML).
    assert "Katalog &amp; Import" in html
    assert "Aktionen &amp; Reservierung" in html
