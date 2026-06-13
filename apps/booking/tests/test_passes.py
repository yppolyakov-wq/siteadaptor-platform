"""G9 / G9b: Mehrfachkarte (10er-Karte) — выпуск, атомарное погашение (guard на
исчерпание/просрочку), кабинет, публичное погашение по коду при онлайн-записи
(карта вместо оплаты; невалидный код не уводит на оплату и не теряет бронь)."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views, services, views
from apps.booking.models import AvailabilityRule, Booking, Pass, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _cab_req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/booking/karten/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _pub_req(method="post", path="/termin/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])  # booking активен
    return request


def _resource_with_rule(capacity=10):
    day = timezone.localdate() + timedelta(days=3)
    resource = Resource.objects.create(name="Yoga", capacity=capacity)
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=day.weekday(),
        start_time="09:00",
        end_time="12:00",
        slot_minutes=60,
    )
    return resource, day


# --- сервисы: выпуск + атомарное погашение ----------------------------------------


def test_issue_pass_creates_with_code_and_credits():
    card = services.issue_pass(name="Yogi", email="y@t.de", credits=10, label="10er Yoga")
    assert card.code.startswith("K-") and card.credits_total == 10 and card.credits_left == 10
    assert card.is_valid


def test_redeem_pass_decrements():
    card = services.issue_pass(name="Yogi", credits=3)
    services.redeem_pass(card)
    card.refresh_from_db()
    assert card.credits_used == 1 and card.credits_left == 2


def test_redeem_pass_exhausted_raises():
    card = services.issue_pass(name="Yogi", credits=1)
    services.redeem_pass(card)
    with pytest.raises(services.PassInvalid):
        services.redeem_pass(card)


def test_redeem_pass_expired_raises():
    card = services.issue_pass(
        name="Yogi", credits=5, valid_until=timezone.localdate() - timedelta(days=1)
    )
    with pytest.raises(services.PassInvalid):
        services.redeem_pass(card)


# --- кабинет -----------------------------------------------------------------------


def test_cabinet_issues_pass():
    resp = views.passes_view(
        _cab_req("post", {"action": "issue", "name": "Kunde", "credits": "5", "label": "5er"})
    )
    assert resp.status_code == 302
    card = Pass.objects.get()
    assert card.credits_total == 5 and card.customer.name == "Kunde"


def test_cabinet_manual_redeem():
    card = services.issue_pass(name="Kunde", credits=4)
    views.passes_view(_cab_req("post", {"action": "redeem", "pass": str(card.pk)}))
    card.refresh_from_db()
    assert card.credits_used == 1


# --- публичная запись по карте -----------------------------------------------------


def test_slots_page_shows_pass_field_when_passes_exist():
    services.issue_pass(name="Yogi", credits=10)
    resource, day = _resource_with_rule()
    start = availability.free_slots(resource, day)[0][0].isoformat()  # выбран слот → форма
    body = public_views.termin_slots(
        _pub_req("get", f"/termin/{resource.pk}/", {"tag": day.isoformat(), "slot": start}),
        pk=resource.pk,
    ).content.decode()
    assert "pass_code" in body


def test_book_with_pass_code_redeems_and_skips_deposit():
    resource, day = _resource_with_rule()
    resource.deposit_cents = 500  # был бы депозит — карта его минует
    resource.save()
    card = services.issue_pass(name="Yogi", email="y@t.de", credits=10)
    start, end = availability.free_slots(resource, day)[0]
    resp = public_views.termin_book(
        _pub_req(
            "post",
            f"/termin/{resource.pk}/buchen/",
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "name": "Yogi",
                "pass_code": card.code,
            },
        ),
        pk=resource.pk,
    )
    booking = Booking.objects.get(resource=resource)
    card.refresh_from_db()
    assert booking.card_id == card.id and card.credits_used == 1
    assert booking.payment_state == Booking.PAYMENT_NONE  # депозит пропущен
    assert resp.url == f"/t/{booking.reference_code}/"


def test_pass_booking_auto_confirms():
    resource, day = _resource_with_rule()
    card = services.issue_pass(name="Yogi", credits=10)
    start, end = availability.free_slots(resource, day)[0]
    public_views.termin_book(
        _pub_req(
            "post",
            f"/termin/{resource.pk}/buchen/",
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "name": "Yogi",
                "pass_code": card.code,
            },
        ),
        pk=resource.pk,
    )
    booking = Booking.objects.get(resource=resource)
    assert booking.status == Booking.STATUS_CONFIRMED  # карта = оплачено → confirmed


def test_pass_booking_manual_confirm_stays_pending():
    resource, day = _resource_with_rule()
    resource.require_manual_confirm = True
    resource.save()
    card = services.issue_pass(name="Yogi", credits=10)
    start, end = availability.free_slots(resource, day)[0]
    public_views.termin_book(
        _pub_req(
            "post",
            f"/termin/{resource.pk}/buchen/",
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "name": "Yogi",
                "pass_code": card.code,
            },
        ),
        pk=resource.pk,
    )
    booking = Booking.objects.get(resource=resource)
    assert booking.status == Booking.STATUS_PENDING and booking.card is not None


def test_invalid_pass_code_keeps_booking_no_charge():
    resource, day = _resource_with_rule()
    start, end = availability.free_slots(resource, day)[0]
    resp = public_views.termin_book(
        _pub_req(
            "post",
            f"/termin/{resource.pk}/buchen/",
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "name": "Yogi",
                "pass_code": "K-NOPE99",
            },
        ),
        pk=resource.pk,
    )
    booking = Booking.objects.get(resource=resource)
    assert booking.card_id is None  # карта не привязана
    assert booking.payment_state == Booking.PAYMENT_NONE
    assert resp.url == f"/t/{booking.reference_code}/"  # бронь есть, на оплату не уводили
