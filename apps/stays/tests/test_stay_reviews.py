"""UA4-4b: отзывы о номере — верификация брони, приём формы, рендер на детали."""

import uuid
from datetime import date

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions.models import Customer
from apps.reviews.models import Review
from apps.stays import public_views
from apps.stays.models import StayBooking, StayUnit
from apps.stays.reviews import has_stayed
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/"):
    request = getattr(RequestFactory(), method)(path)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])  # stays активен
    return request


def _post_req(path, data):
    request = RequestFactory().post(path, data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"FeWo {uuid.uuid4().hex[:6]}", **kwargs)


def _stay(unit, email, *, status=StayBooking.STATUS_CONFIRMED):
    customer = Customer.objects.create(name="Gast", email=email)
    return StayBooking.objects.create(
        unit=unit,
        customer=customer,
        reference_code=f"S-{uuid.uuid4().hex[:6].upper()}",
        arrival=date(2026, 7, 1),
        departure=date(2026, 7, 4),
        status=status,
    )


# --- верификация брони (fail-closed) ---------------------------------------
def test_has_stayed_true_for_guest():
    u = _unit()
    _stay(u, "gast@test.de")
    assert has_stayed(u, "Gast@Test.de") is True


def test_has_stayed_false_without_booking():
    assert has_stayed(_unit(), "nobody@test.de") is False


def test_has_stayed_false_for_cancelled():
    u = _unit()
    _stay(u, "gast@test.de", status=StayBooking.STATUS_CANCELLED)
    assert has_stayed(u, "gast@test.de") is False


def test_has_stayed_false_for_other_unit():
    u1, u2 = _unit(), _unit()
    _stay(u1, "gast@test.de")
    assert has_stayed(u2, "gast@test.de") is False


# --- рендер отзывов на детали номера ---------------------------------------
def test_stay_detail_renders_reviews_and_form():
    u = _unit()
    Review.objects.create(
        entity_kind="stay",
        entity_id=u.pk,
        rating=5,
        author_name="Heinz",
        email="h@t.de",
        comment="Schön",
    )
    body = public_views.unterkunft_unit(_req(path=f"/unterkunft/{u.pk}/"), pk=u.pk).content.decode()
    assert "Heinz" in body and "Schön" in body
    assert 'id="bewertungen"' in body
    assert f"/unterkunft/{u.pk}/bewerten/" in body


def test_stay_detail_hides_section_from_builder_config():
    """UA4-1 slice C: скрытие секции «reviews» в билдере убирает её с детали номера."""
    u = _unit()
    Review.objects.create(
        entity_kind="stay", entity_id=u.pk, rating=5, author_name="Heinz", email="h@t.de"
    )
    req = _req(path=f"/unterkunft/{u.pk}/")
    req.tenant.site_config = {"stay_detail": {"hidden": ["reviews"]}}
    body = public_views.unterkunft_unit(req, pk=u.pk).content.decode()
    assert "Heinz" not in body and 'id="bewertungen"' not in body


# --- приём формы (POST) -----------------------------------------------------
def test_submit_creates_review_for_verified_guest():
    u = _unit()
    _stay(u, "gast@test.de")
    data = {"author_name": "Gast", "email": "gast@test.de", "rating": "5", "comment": "Top"}
    resp = public_views.stay_review_submit(
        _post_req(f"/unterkunft/{u.pk}/bewerten/", data), pk=u.pk
    )
    assert resp.status_code == 302
    r = Review.objects.get(entity_kind="stay", entity_id=u.pk, email="gast@test.de")
    assert r.rating == 5 and r.verified


def test_submit_rejected_for_non_guest():
    u = _unit()
    data = {"author_name": "Fake", "email": "fake@test.de", "rating": "5"}
    public_views.stay_review_submit(_post_req(f"/unterkunft/{u.pk}/bewerten/", data), pk=u.pk)
    assert not Review.objects.filter(entity_kind="stay", entity_id=u.pk).exists()


def test_submit_404_when_stays_module_off():
    """Гейт модуля (как у деталь-вьюхи): при выключенном stays submit → Http404."""
    from django.http import Http404

    u = _unit()
    request = RequestFactory().post(f"/unterkunft/{u.pk}/bewerten/", {"rating": "5"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=["stays"])  # модуль выключен
    with pytest.raises(Http404):
        public_views.stay_review_submit(request, pk=u.pk)
