"""KA-H7 (аудит KA-5c): выручка записи, ручная запись с услугой, клиент по телефону.

- визит по карте не пишет цену услуги второй раз (она проведена при продаже карты);
- ставка выручки — снимок записи, § 19 UStG → 0 %;
- ручная запись берёт цену/длительность из услуги и сохраняет заметку;
- клиент без e-mail находится по телефону (без слияния разных людей).
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services, views
from apps.booking.models import Booking, Resource, Service
from apps.booking.state_machine import BookingSM
from apps.finance.models import RevenueEntry
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def small_business(monkeypatch):
    from apps.booking import revenue

    monkeypatch.setattr(revenue, "_tenant", lambda t=None: SimpleNamespace(small_business=True))


def _slot(days_ahead=7, hour=12):
    tz = timezone.get_current_timezone()
    day = timezone.localdate() + timedelta(days=days_ahead)
    start = datetime.combine(day, time(hour, 0), tzinfo=tz)
    return start, start + timedelta(hours=1)


def _resource(**kw):
    return Resource.objects.create(name=f"Platz {uuid.uuid4().hex[:6]}", **kw)


def _service(**kw):
    kw.setdefault("name", f"Schnitt {uuid.uuid4().hex[:5]}")
    kw.setdefault("price_cents", 4000)
    kw.setdefault("duration_minutes", 45)
    return Service.objects.create(**kw)


def _book(**kw):
    start, end = _slot(hour=kw.pop("hour", 12))
    resource = kw.pop("resource", None) or _resource()
    return services.book(resource, start=start, end=end, name="Gast", **kw)


def _fulfill(booking):
    booking = BookingSM().apply(booking, "confirmed")
    return BookingSM().apply(booking, "fulfilled")


def _revenue(booking):
    return RevenueEntry.objects.filter(source="booking", source_ref=str(booking.id))


# --- A: визит по карте --------------------------------------------------------------


def test_pass_booking_journals_only_extras():
    service = _service()
    booking = _book(
        email="k@test.de",
        service=service,
        price_cents=4000,
        extras=[{"label": "Kur", "price_cents": 500}],
    )
    card = services.issue_pass(name="Gast", email="k@test.de", credits=5)
    services.redeem_pass(card, booking=booking)
    _fulfill(booking)
    entry = _revenue(booking).get()
    assert entry.amount == Decimal("5.00")


def test_pass_booking_without_extras_writes_nothing():
    booking = _book(email="k2@test.de", service=_service(), price_cents=4000)
    card = services.issue_pass(name="Gast", email="k2@test.de", credits=5)
    services.redeem_pass(card, booking=booking)
    _fulfill(booking)
    assert not _revenue(booking).exists()


def test_normal_booking_journals_full_total():
    booking = _book(email="k3@test.de", service=_service(), price_cents=4000)
    _fulfill(booking)
    assert _revenue(booking).get().amount == Decimal("40.00")


def test_fulfill_hook_idempotent():
    booking = _book(email="k4@test.de", service=_service(), price_cents=4000)
    booking = _fulfill(booking)
    from apps.core import status_effects

    status_effects.record_revenue_for("booking", booking)
    assert _revenue(booking).count() == 1


def test_reversal_matches_recorded_amount():
    from apps.core import status_effects

    service = _service()
    booking = _book(
        email="k5@test.de",
        service=service,
        price_cents=4000,
        extras=[{"label": "Kur", "price_cents": 500}],
    )
    card = services.issue_pass(name="Gast", email="k5@test.de", credits=5)
    services.redeem_pass(card, booking=booking)
    booking = _fulfill(booking)
    status_effects.record_reversal_for("booking", booking)
    total = sum(e.amount for e in RevenueEntry.objects.filter(source="booking"))
    assert total == Decimal("0")


# --- B: ставка ----------------------------------------------------------------------


def test_revenue_uses_snapshot_vat():
    service = _service(vat_rate=Decimal("7.00"))
    booking = _book(email="v@test.de", service=service, price_cents=4000)
    _fulfill(booking)
    assert _revenue(booking).get().vat_rate == Decimal("7.00")


def test_small_business_revenue_zero_rate(small_business):
    booking = _book(email="s@test.de", service=_service(), price_cents=4000)
    _fulfill(booking)
    assert _revenue(booking).get().vat_rate == Decimal("0")


# --- C: ручная запись ---------------------------------------------------------------


def _req(data):
    request = RequestFactory().post("/dashboard/booking/neu/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _manual(resource, **extra):
    start = timezone.localtime(_slot()[0]).replace(tzinfo=None)
    data = {"resource": str(resource.pk), "start": start.isoformat()}
    data.update(extra)
    views.booking_create(_req(data))
    return Booking.objects.filter(resource=resource).first()


def test_manual_booking_with_service_takes_price_and_duration():
    service = _service(price_cents=3500, duration_minutes=45)
    booking = _manual(_resource(), service=str(service.pk), minutes="")
    assert booking.service_id == service.pk
    assert booking.price_cents == 3500
    assert booking.end - booking.start == timedelta(minutes=45)


def test_manual_booking_per_person_multiplies():
    service = _service(price_cents=2000, pricing_mode="per_person")
    resource = _resource(capacity=10, counts_party_size=True)
    booking = _manual(resource, service=str(service.pk), party_size="3")
    assert booking.price_cents == 6000


def test_manual_booking_explicit_minutes_wins():
    service = _service(duration_minutes=45)
    booking = _manual(_resource(), service=str(service.pk), minutes="90")
    assert booking.end - booking.start == timedelta(minutes=90)


def test_manual_booking_without_service_unchanged():
    booking = _manual(_resource(), minutes="")
    assert booking.service_id is None
    assert booking.price_cents == 0
    assert booking.end - booking.start == timedelta(minutes=60)


def test_manual_booking_garbage_or_inactive_service_ignored():
    inactive = _service(is_active=False)
    assert _manual(_resource(), service=str(inactive.pk)).service_id is None
    assert _manual(_resource(), service="kaputt").service_id is None


def test_manual_booking_note_saved():
    booking = _manual(_resource(), note="Kommt mit Hund")
    assert booking.note == "Kommt mit Hund"


# --- E: клиент по телефону (только кабинет) ------------------------------------------


def _cab(phone, name="Anna", hour=10):
    start, end = _slot(hour=hour)
    return services.book(
        _resource(), start=start, end=end, name=name, phone=phone, match_by_phone=True
    )


def test_customer_reused_by_phone_without_email():
    assert _cab("0171 123", hour=10).customer_id == _cab("0171 123", hour=14).customer_id


def test_phone_match_normalizes_spaces():
    assert _cab("0171123", hour=10).customer_id == _cab("0171 123", hour=14).customer_id


def test_phone_match_does_not_merge_different_names():
    first = _cab("0171 9", name="Anna", hour=10)
    second = _cab("0171 9", name="Bernd", hour=14)
    assert first.customer_id != second.customer_id
    assert Customer.objects.filter(phone="0171 9").count() == 2


def test_storefront_path_never_matches_by_phone():
    """Витрина: телефон и имя легко подставить чужие — склейки нет."""
    first = _cab("0171 77", name="Anna", hour=10)
    start, end = _slot(hour=14)
    public = services.book(_resource(), start=start, end=end, name="Anna", phone="0171 77")
    assert public.customer_id != first.customer_id


def test_cabinet_manual_booking_reuses_customer_by_phone():
    first = _manual(_resource(), name="Anna", phone="0171 55")
    second = _manual(_resource(), name="Anna", phone="0171 55")
    assert first.customer_id == second.customer_id


# --- правки по ревью -----------------------------------------------------------------


def test_reversal_skipped_when_nothing_was_journaled():
    """Визит по карте без Extras выручку не писал → сторно не создаёт минус."""
    from apps.core import status_effects

    booking = _book(email="r@test.de", service=_service(), price_cents=4000)
    card = services.issue_pass(name="Gast", email="r@test.de", credits=5)
    services.redeem_pass(card, booking=booking)
    booking = _fulfill(booking)
    status_effects.record_reversal_for("booking", booking)
    assert not RevenueEntry.objects.filter(source="booking").exists()


def test_zero_percent_rate_is_kept():
    service = _service(vat_rate=Decimal("0"))
    booking = _book(email="z@test.de", service=service, price_cents=4000)
    assert booking.vat_rate == Decimal("0")
    _fulfill(booking)
    assert _revenue(booking).get().vat_rate == Decimal("0")


def test_small_business_resolved_from_schema_in_background(monkeypatch):
    """В фоновой задаче у соединения FakeTenant — § 19 дочитывается по схеме."""
    from django.db import connection

    from apps.booking import revenue
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(small_business=True, auto_create_schema=False)
    monkeypatch.setattr(
        connection, "tenant", SimpleNamespace(schema_name=tenant.schema_name), raising=False
    )
    assert revenue._tenant(None).pk == tenant.pk
