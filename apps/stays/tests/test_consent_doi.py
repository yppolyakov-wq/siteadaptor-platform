"""PMS-B1: галка согласия в воронке брони → Double-Opt-In письмо (UWG §7).

Замки: чекбокс НЕ ставит opt-in напрямую (только DOI-письмо); подписанным/
без галки — тишина; форма содержит чекбокс без checked."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.stays import public_views
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit():
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)


def _book_post(unit, extra=None):
    data = {
        "von": (D0 + timedelta(days=1)).isoformat(),
        "bis": (D0 + timedelta(days=3)).isoformat(),
        "erw": "2",
        "name": "Gast",
        "email": f"g-{uuid.uuid4().hex[:6]}@test.de",
        **(extra or {}),
    }
    request = RequestFactory().post(f"/unterkunft/{unit.pk}/buchen/", data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.5"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return public_views.unterkunft_book(request, pk=unit.pk)


def test_checkbox_sends_doi_not_direct_optin():
    unit = _unit()
    resp = _book_post(unit, {"marketing": "on"})
    assert resp.status_code == 302
    assert Notification.objects.filter(type="newsletter_doi").exists()  # DOI ушёл
    customer = Customer.objects.latest("created_at")
    assert customer.marketing_opt_in is False  # прямой opt-in НЕ поставлен (UWG)


def test_no_checkbox_no_doi():
    unit = _unit()
    _book_post(unit)
    assert not Notification.objects.filter(type="newsletter_doi").exists()


def test_already_opted_in_customer_silent():
    unit = _unit()
    email = "stamm@test.de"
    Customer.objects.create(name="Stamm", email=email, marketing_opt_in=True)
    _book_post(unit, {"marketing": "on", "email": email})
    assert not Notification.objects.filter(type="newsletter_doi").exists()


def test_form_has_unchecked_consent_checkbox():
    unit = _unit()
    request = RequestFactory().get(
        f"/unterkunft/{unit.pk}/",
        {"von": (D0 + timedelta(days=1)).isoformat(), "bis": (D0 + timedelta(days=3)).isoformat()},
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = public_views.unterkunft_unit(request, pk=unit.pk).content.decode()
    assert 'name="marketing"' in body
    import re

    tag = re.search(r'<input[^>]*name="marketing"[^>]*>', body).group(0)
    assert "checked" not in tag  # UWG §7: не предотмечено
