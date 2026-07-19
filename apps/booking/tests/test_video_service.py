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
    _services_view(_req("post", {"action": "create", "name": "Video-Beratung", "is_video": "1"}))
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


# --- инкремент 2: секция детали + фасет + письма ------------------------------------


def _detail_html(service, tenant):
    from apps.booking import public_views

    request = _req()
    request.tenant = tenant
    return public_views.service_detail(request, pk=service.pk).content.decode()


def test_detail_video_section_gates():
    with_num = TenantFactory.build(disabled_modules=[], whatsapp_number="+49 171 1234567")
    video = Service.objects.create(name="Beratung", is_video=True)
    plain = Service.objects.create(name="Schnitt")

    html = _detail_html(video, with_num)
    assert "https://wa.me/491711234567" in html
    assert "Per Video zeigen lassen" in html
    # не-видео услуга и бизнес без номера → секции нет
    assert "wa.me" not in _detail_html(plain, with_num)
    no_num = TenantFactory.build(disabled_modules=[], whatsapp_number="")
    assert "wa.me" not in _detail_html(video, no_num)


def test_detail_video_section_hideable_in_builder():
    tenant = TenantFactory.build(
        disabled_modules=[],
        whatsapp_number="+49 171 1234567",
        site_config={"service_detail": {"hidden": ["video"]}},
    )
    video = Service.objects.create(name="Beratung", is_video=True)
    assert "Per Video zeigen lassen" not in _detail_html(video, tenant)


def test_listing_video_chip_and_filter():
    from apps.booking import public_views

    Service.objects.create(name="Beratung", is_video=True)
    Service.objects.create(name="Schnitt")

    request = _req()
    html = public_views.termin_index(request).content.decode()
    assert "?video=1" in html  # авто-чип при ≥1 видео-услуге

    request = _req()
    request.GET = {"video": "1"}
    html = public_views.termin_index(request).content.decode()
    assert "Beratung" in html and "Schnitt" not in html

    Service.objects.filter(is_video=True).delete()
    request = _req()
    html = public_views.termin_index(request).content.decode()
    assert "?video=1" not in html  # без видео-услуг чипа нет


def test_video_booking_email_contains_wa_link():
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking import services as booking_services
    from apps.booking.state_machine import BookingSM
    from apps.notifications.models import Notification

    video = Service.objects.create(name="Beratung", is_video=True)
    from apps.booking.models import Resource

    start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    booking = booking_services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="Kim",
        email="kim@test.de",
        service=video,
    )
    BookingSM().apply(booking, "confirmed")
    n = Notification.objects.get(dedupe_key=f"booking:{booking.id}:confirmed:customer")
    body = n.payload.get("body", "")
    # В тестах у тенанта фабрики номера нет → wa.me пуст; проверяем через ctx-ветку:
    # событие confirmed видео-услуги без номера — письмо БЕЗ wa.me (fail-safe).
    assert "wa.me" not in body


def test_video_booking_email_wa_link_with_number(monkeypatch):
    """С номером бизнеса подтверждение видео-брони содержит wa.me и дату."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking import notifications as booking_notifications
    from apps.booking import services as booking_services
    from apps.booking.models import Resource
    from apps.booking.state_machine import BookingSM
    from apps.notifications.models import Notification

    tenant = TenantFactory.build(whatsapp_number="+49 171 1234567")
    monkeypatch.setattr(booking_notifications, "_tenant", lambda schema: tenant)

    video = Service.objects.create(name="Beratung", is_video=True)
    start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    booking = booking_services.book(
        Resource.objects.create(name="Stuhl"),
        start=start,
        end=start + timedelta(minutes=30),
        name="Kim",
        email="kim@test.de",
        service=video,
    )
    BookingSM().apply(booking, "confirmed")
    n = Notification.objects.get(dedupe_key=f"booking:{booking.id}:confirmed:customer")
    body = n.payload.get("body", "")
    assert "https://wa.me/491711234567" in body
    assert "Video-Termin" in body and start.strftime("%d.%m.") in body

    # Обычная (не видео) бронь — письмо без wa.me даже с номером.
    plain = booking_services.book(
        Resource.objects.create(name="Bank"),
        start=start + timedelta(hours=2),
        end=start + timedelta(hours=2, minutes=30),
        name="Kim",
        email="kim@test.de",
    )
    BookingSM().apply(plain, "confirmed")
    n2 = Notification.objects.get(dedupe_key=f"booking:{plain.id}:confirmed:customer")
    assert "wa.me" not in n2.payload.get("body", "")
