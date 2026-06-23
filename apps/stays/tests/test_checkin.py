"""G6: Online-Checkin / цифровой Meldeschein — флоу, подпись, retention."""

from datetime import date, timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions.models import Customer
from apps.stays import public_views
from apps.stays.models import GuestRegistration, StayBooking, StayUnit
from apps.stays.tasks import purge_due_registrations

pytestmark = pytest.mark.django_db


def _booking(**kw):
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=9000, max_guests=2)
    customer = Customer.objects.create(name="Anna Becker", email="a@test.de")
    defaults = {
        "unit": unit,
        "customer": customer,
        "reference_code": "S-ABC123",
        "arrival": date(2030, 6, 3),
        "departure": date(2030, 6, 5),
        "status": StayBooking.STATUS_CONFIRMED,
    }
    defaults.update(kw)
    return StayBooking.objects.create(**defaults)


def _post(booking, data):
    token = public_views.checkin_token(booking)
    req = RequestFactory().post(f"/checkin/{token}/", data)
    req.tenant = type("T", (), {"is_module_active": lambda self, k: True})()
    # messages framework требует storage на запросе
    from django.contrib.messages.storage.fallback import FallbackStorage

    req.session = {}
    req._messages = FallbackStorage(req)
    return public_views.unterkunft_checkin(req, token)


def test_checkin_saves_registration_with_signature():
    b = _booking()
    _post(
        b,
        {
            "first_name": "Anna",
            "last_name": "Becker",
            "city": "Köln",
            "postal_code": "50667",
            "signed_name": "Anna Becker",
            "confirm": "on",
        },
    )
    reg = GuestRegistration.objects.get(booking=b)
    assert reg.first_name == "Anna" and reg.city == "Köln"
    assert reg.signed_name == "Anna Becker"
    assert reg.signed_at is not None


def test_checkin_requires_confirm_and_name():
    b = _booking()
    _post(b, {"first_name": "Anna", "last_name": "Becker", "signed_name": ""})
    assert not GuestRegistration.objects.filter(booking=b).exists()


def test_bad_token_404():
    from django.http import Http404

    req = RequestFactory().get("/checkin/bad/")
    req.tenant = type("T", (), {"is_module_active": lambda self, k: True})()
    with pytest.raises(Http404):
        public_views.unterkunft_checkin(req, "bad-token")


def test_purge_removes_old_registrations_only():
    old = _booking(reference_code="S-OLD111", departure=date(2020, 1, 10))
    recent = _booking(reference_code="S-NEW222", departure=timezone.localdate() + timedelta(days=2))
    GuestRegistration.objects.create(booking=old, first_name="O", last_name="L", signed_name="OL")
    GuestRegistration.objects.create(
        booking=recent, first_name="N", last_name="E", signed_name="NE"
    )
    deleted = purge_due_registrations()
    assert deleted == 1
    assert GuestRegistration.objects.filter(booking=recent).exists()
    assert not GuestRegistration.objects.filter(booking=old).exists()
