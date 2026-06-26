"""G10 / G10a: услуги (Service) — слоты по длительности, бронь со снимком цены,
подбор ресурса бизнес-уровня, выручка за выполненную услугу."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views, services, views
from apps.booking.models import AvailabilityRule, Booking, Resource, Service
from apps.booking.state_machine import BookingSM
from apps.finance.models import RevenueEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _resource(**kwargs):
    return Resource.objects.create(name=f"Platz {uuid.uuid4().hex[:6]}", **kwargs)


def _service(**kwargs):
    kwargs.setdefault("name", "Ölwechsel")
    kwargs.setdefault("duration_minutes", 60)
    kwargs.setdefault("price_cents", 4900)
    return Service.objects.create(**kwargs)


def _future_day(days=7):
    return timezone.localdate() + timedelta(days=days)


def _rule(resource, day, start="09:00", end="12:00", slot=30):
    return AvailabilityRule.objects.create(
        resource=resource, weekday=day.weekday(), start_time=start, end_time=end, slot_minutes=slot
    )


def _aware(day, hour, minute=0):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


# --- A3: фото услуги (богатая карточка) -------------------------------------------
def test_service_image_url_property():
    svc = _service(image={"url": "https://img.example/cut.jpg", "alt": {"de": "Schnitt"}})
    assert svc.image_url == "https://img.example/cut.jpg"
    # не-dict/пусто → '' (без падений)
    assert _service(image={}).image_url == ""
    assert Service(name="x", image=None).image_url == ""


def test_service_slots_page_shows_photo(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day)
    svc = _service(image={"url": "https://img.example/color.jpg"}, description="Schöne Farbe.")
    request = RequestFactory().get(f"/t/{svc.pk}/?tag={day:%Y-%m-%d}")
    SessionMiddleware(lambda rq: None).process_request(request)
    MessageMiddleware(lambda rq: None).process_request(request)
    request.tenant = TenantFactory.build(name="Salon")
    body = public_views.service_slots(request, pk=svc.pk).content.decode()
    assert "https://img.example/color.jpg" in body
    assert "Schöne Farbe." in body


# --- слоты по длительности услуги -------------------------------------------------


def test_free_slots_uses_service_duration():
    resource = _resource()
    day = _future_day()
    _rule(resource, day, "09:00", "12:00", slot=30)
    slots = availability.free_slots(resource, day, duration_minutes=60)
    # длина слота = 60 мин; старты каждые 30: 9:00, 9:30, 10:00, 10:30, 11:00
    assert slots[0][1] - slots[0][0] == timedelta(minutes=60)
    assert len(slots) == 5


def test_service_slots_and_assign_resource():
    r1, r2 = _resource(), _resource()
    day = _future_day()
    _rule(r1, day)
    _rule(r2, day)
    service = _service(duration_minutes=30)
    starts = availability.service_slots(service, day)
    assert starts and starts == sorted(starts)
    # ресурс назначается на свободный старт
    assert availability.assign_resource(service, starts[0]) in (r1, r2)


def test_assign_resource_none_when_full():
    resource = _resource()  # capacity 1
    day = _future_day()
    _rule(resource, day)
    service = _service(duration_minutes=30)
    start = availability.service_slots(service, day)[0]
    end = start + timedelta(minutes=30)
    services.book(resource, start=start, end=end, name="Gast")  # занял единственный ресурс
    assert availability.assign_resource(service, start) is None


def test_choose_specific_resource_scopes_slots_and_booking():
    """#4: выбор конкретного мастера — слоты и бронь только по нему."""
    r1, r2 = _resource(), _resource()
    day = _future_day()
    _rule(r1, day)
    _rule(r2, day)
    service = _service(duration_minutes=30)
    start = availability.service_slots(service, day, resource=r1)[0]
    # занят r1 на этот старт → его слот пропадает, но общий (r2) остаётся
    services.book(r1, start=start, end=start + timedelta(minutes=30), name="X")
    assert start not in availability.service_slots(service, day, resource=r1)
    assert start in availability.service_slots(service, day)  # r2 ещё свободен
    # назначение ограничено выбранным ресурсом
    assert availability.assign_resource(service, start, resource=r1) is None
    assert availability.assign_resource(service, start, resource=r2) == r2


# --- бронь со снимком цены + выручка ----------------------------------------------


def test_book_snapshots_service_and_price():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    assert booking.service == service and booking.price_cents == 4900


def test_fulfilled_service_records_revenue():
    resource = _resource()
    day = _future_day()
    service = _service(price_cents=4900)
    start = _aware(day, 9)
    booking = services.book(
        resource,
        start=start,
        end=start + timedelta(minutes=60),
        name="Gast",
        service=service,
        price_cents=service.price_cents,
    )
    sm = BookingSM()
    booking = sm.apply(booking, "confirmed")
    sm.apply(booking, "fulfilled")
    entry = RevenueEntry.objects.get(source="booking", source_ref=str(booking.id))
    assert entry.amount == Decimal("49.00") and entry.vat_rate == Decimal("19.00")


def test_fulfilled_without_price_no_revenue():
    resource = _resource()
    start = _aware(_future_day(), 9)
    booking = services.book(resource, start=start, end=start + timedelta(hours=1), name="Tisch")
    sm = BookingSM()
    sm.apply(sm.apply(booking, "confirmed"), "fulfilled")
    assert not RevenueEntry.objects.filter(source="booking").exists()


# --- G10b: кабинет + витрина ------------------------------------------------------


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cab_req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/booking/leistungen/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _pub_req(method="get", path="/termin/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])  # booking активен
    return request


def test_cabinet_creates_and_updates_service():
    resp = views.services_view(
        _cab_req(
            "post",
            {"action": "create", "name": "Haarschnitt", "duration": "45", "price_eur": "25,00"},
        )
    )
    assert resp.status_code == 302
    svc = Service.objects.get(name="Haarschnitt")
    assert svc.duration_minutes == 45 and svc.price_cents == 2500
    views.services_view(
        _cab_req(
            "post",
            {"action": "update", "service": str(svc.pk), "duration": "60", "price_eur": "30"},
        )
    )
    svc.refresh_from_db()
    assert svc.duration_minutes == 60 and svc.price_cents == 3000


def _png(name="cut.png"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_cabinet_service_photo_upload_and_remove():
    """A3: владелец загружает фото услуги в кабинете и может его удалить."""
    create = views.services_view(
        _cab_req(
            "post", {"action": "create", "name": "Färben", "duration": "90", "price_eur": "69"}
        )
    )
    assert create.status_code == 302
    svc = Service.objects.get(name="Färben")
    # загрузка фото на update
    req = _cab_req(
        "post", {"action": "update", "service": str(svc.pk), "duration": "90", "price_eur": "69"}
    )
    req.FILES["image"] = _png()
    views.services_view(req)
    svc.refresh_from_db()
    assert svc.image_url  # фото сохранено
    # удаление фото
    views.services_view(
        _cab_req(
            "post",
            {
                "action": "update",
                "service": str(svc.pk),
                "duration": "90",
                "price_eur": "69",
                "remove_image": "1",
            },
        )
    )
    svc.refresh_from_db()
    assert not svc.image_url


def test_termin_index_shows_services():
    Service.objects.create(name="Ölwechsel", duration_minutes=30, price_cents=4900)
    body = public_views.termin_index(_pub_req()).content.decode()
    assert "Ölwechsel" in body


def test_service_book_assigns_resource_and_snapshots_price():
    resource = _resource()
    day = _future_day()
    _rule(resource, day)
    service = _service(duration_minutes=30, price_cents=2500)
    start = availability.service_slots(service, day)[0]
    resp = public_views.service_book(
        _pub_req(
            "post",
            f"/termin/leistung/{service.pk}/buchen/",
            {"start": start.isoformat(), "name": "Gast"},
        ),
        pk=service.pk,
    )
    booking = Booking.objects.get(service=service)
    assert booking.resource == resource and booking.price_cents == 2500
    assert resp.url == f"/t/{booking.reference_code}/"


def test_service_book_rejects_unavailable_time():
    resource = _resource()
    day = _future_day()
    _rule(resource, day, "09:00", "12:00")
    service = _service(duration_minutes=30)
    bad = _aware(day, 3)  # вне окна правил
    public_views.service_book(
        _pub_req(
            "post",
            f"/termin/leistung/{service.pk}/buchen/",
            {"start": bad.isoformat(), "name": "Gast"},
        ),
        pk=service.pk,
    )
    assert not Booking.objects.filter(service=service).exists()
