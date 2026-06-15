"""Платформенная админка: KPI-дашборд + чистка реестра (S1/S2).

В тестах django-tenants все приложения SHARED → данные лежат в public-схеме, где
и работает админка. ROOT_URLCONF переключаем на config.urls_public, чтобы
resolved'ились admin-урлы (reverse в карточках/сайдбаре).
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.admin_dashboard import dashboard_callback
from apps.support.models import SupportThread
from apps.tenants.tests.factories import TenantFactory


def _attach_session_user(request, user):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


@pytest.mark.django_db
def test_broken_tenant_admins_unregistered():
    """TENANT-модели (нет таблиц в public) сняты с регистрации; SHARED — на месте."""
    labels = {model._meta.app_label for model in admin.site._registry}
    assert "catalog" not in labels
    assert "promotions" not in labels
    assert "djstripe" not in labels
    assert {"tenants", "aggregator", "support"} <= labels


@pytest.mark.django_db
def test_dashboard_callback_counts(rf, settings):
    settings.ROOT_URLCONF = "config.urls_public"
    TenantFactory(schema_name="t_a", name="A", subscription_status="active")
    TenantFactory(schema_name="t_b", name="B", subscription_status="active")
    TenantFactory(schema_name="t_c", name="C", subscription_status="trial")
    owner = TenantFactory(schema_name="t_d", name="D", subscription_status="suspended")
    SupportThread.objects.create(tenant=owner, subject="Hilfe", status=SupportThread.STATUS_OPEN)

    ctx = dashboard_callback(rf.get("/admin/"), {})
    cards = {c["title"]: c["value"] for c in ctx["kpi_cards"]}
    assert cards["Betriebe"] == 4
    assert cards["Aktive Abos"] == 2
    assert cards["Im Test"] == 1
    assert cards["Offene Tickets"] == 1
    # suspended → карточка-предупреждение появляется.
    assert ctx["kpi_alert"] is not None
    assert ctx["kpi_alert"]["value"] == 1
    assert len(ctx["recent_tenants"]) == 4
    assert len(ctx["open_tickets"]) == 1
    # public-строка не считается бизнесом.
    TenantFactory(schema_name="public", name="Plattform")
    assert dashboard_callback(rf.get("/admin/"), {})["kpi_cards"][0]["value"] == 4


@pytest.mark.django_db
def test_admin_index_renders(rf, settings):
    settings.ROOT_URLCONF = "config.urls_public"
    # Тестовые настройки используют manifest-storage (нужен collectstatic) —
    # для рендера админки берём простой storage, иначе {% static %} падает на
    # отсутствующем манифесте.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    root = get_user_model().objects.create_superuser("root", "root@test.de", "pw12345678")
    TenantFactory(schema_name="t1", name="Bäckerei A", subscription_status="active")

    req = _attach_session_user(rf.get("/admin/"), root)
    resp = admin.site.index(req)
    resp.render()
    html = resp.content.decode()

    assert resp.status_code == 200
    assert "Betriebe" in html  # KPI-карточка
    assert "Bäckerei A" in html  # список «Neueste Betriebe»
