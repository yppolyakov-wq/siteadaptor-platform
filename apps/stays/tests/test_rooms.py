"""H3: богатая карточка номера — площадь/кровать/удобства + похожие номера."""

import uuid

import pytest
from django.test import RequestFactory

from apps.stays import public_views
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/unterkunft/x/"):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def test_amenity_badges_in_catalog_order_and_filter_unknown():
    unit = _unit(amenities=["bogus", "tv", "wifi"])
    badges = unit.amenity_badges
    labels = [label for label, _icon in badges]
    # порядок как в каталоге AMENITIES (wifi раньше tv); неизвестный ключ отброшен
    assert labels == ["WLAN", "TV"]


def test_detail_shows_area_bed_and_amenities():
    unit = _unit(area_sqm=24, bed_type="Queensize-Bett", amenities=["wifi", "balcony"])
    body = public_views.unterkunft_unit(
        _req(f"/unterkunft/{unit.pk}/"), pk=unit.pk
    ).content.decode()
    assert "24 m²" in body
    assert "Queensize-Bett" in body
    assert "WLAN" in body
    assert "Balkon/Terrasse" in body


def test_detail_lists_similar_rooms_same_type_first():
    main = _unit(type="room", price_cents=9000)
    same_type = _unit(type="room", price_cents=7000)
    other_type = _unit(type="apartment", price_cents=5000)
    body = public_views.unterkunft_unit(
        _req(f"/unterkunft/{main.pk}/"), pk=main.pk
    ).content.decode()
    # оба похожих показаны, текущий — нет
    assert str(same_type.pk) in body
    assert str(other_type.pk) in body
    # тот же тип (room) идёт раньше apartment в выдаче
    assert body.index(str(same_type.pk)) < body.index(str(other_type.pk))


def test_detail_no_similar_when_alone():
    unit = _unit()
    body = public_views.unterkunft_unit(
        _req(f"/unterkunft/{unit.pk}/"), pk=unit.pk
    ).content.decode()
    assert "Similar rooms" not in body
