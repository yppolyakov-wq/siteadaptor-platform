"""LS-1 «Video-Beratung» инкремент 1: флаг is_video + wa_link + кабинет.

v1 = WhatsApp (без записи, §201): услуга помечается видео-флагом (миграция
booking/0017), номер бизнеса — Tenant.whatsapp_number (tenants/0027).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.booking.models import Service
from apps.core.whatsapp import wa_link
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


# --- wa_link ------------------------------------------------------------------------


def test_wa_link_normalizes_number_and_encodes_text():
    url = wa_link("+49 171 123-45", "Video-Termin 20.07. 10:00 — Beratung")
    assert url.startswith("https://wa.me/491711234")
    assert "?text=Video-Termin%2020.07." in url
    assert wa_link("+49 171 12345") == "https://wa.me/4917112345"  # без текста
    assert wa_link("") == "" and wa_link(None) == ""  # нет номера → нет ссылки
    assert wa_link("abc") == ""  # мусор без цифр


# --- кабинет: форма услуги ----------------------------------------------------------


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/booking/leistungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _services_view(request):
    from apps.booking import views

    return views.services_view(request)


def test_service_defaults_not_video():
    assert Service.objects.create(name="Schnitt").is_video is False


def test_create_service_with_video_flag():
    _services_view(
        _req("post", {"action": "create", "name": "Video-Beratung", "is_video": "1"})
    )
    assert Service.objects.get(name="Video-Beratung").is_video is True


def test_update_toggles_video_only_with_sentinel():
    service = Service.objects.create(name="Schnitt", is_video=True)
    base = {"action": "update", "service": str(service.pk), "duration": "30", "price_eur": "10"}
    # Клиент формы БЕЗ чекбокса (нет сентинела) → флаг не тронут.
    _services_view(_req("post", base))
    service.refresh_from_db()
    assert service.is_video is True
    # Наша форма (сентинел есть), чекбокс снят → False.
    _services_view(_req("post", {**base, "is_video_present": "1"}))
    service.refresh_from_db()
    assert service.is_video is False
    # Чекбокс поставлен → True.
    _services_view(_req("post", {**base, "is_video_present": "1", "is_video": "1"}))
    service.refresh_from_db()
    assert service.is_video is True


def test_settings_form_saves_whatsapp_number():
    from apps.tenants.forms import BusinessSettingsForm

    tenant = TenantFactory()
    form = BusinessSettingsForm(
        {"name": tenant.name, "whatsapp_number": "+49 171 1234567"}, instance=tenant
    )
    assert form.is_valid(), form.errors
    form.save()
    tenant.refresh_from_db()
    assert tenant.whatsapp_number == "+49 171 1234567"
