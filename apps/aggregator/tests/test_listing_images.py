"""PIMG: картинки карточек каталога города.

Прод показал две дыры: (1) плейсхолдер демо-бизнеса `/medien/demo.svg` хранится в
снимке листинга относительным и запрашивался у хоста ПОРТАЛА, где маршрута не было —
404; (2) номер/событие/тур брали только логотип бизнеса — своё фото в каталог не
попадало, а без логотипа карточка оставалась пустой.
"""

from datetime import timedelta

import pytest
from django.urls import resolve
from django.utils import timezone

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.events.models import Event, Tour
from apps.stays.models import StayUnit
from apps.tenants.demo_images import demo_image_view
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/x/photo.webp", "is_primary": True}]


@pytest.mark.parametrize("urlconf", ["config.urls_portal", "config.urls_public"])
def test_demo_placeholder_is_served_on_portal_and_public_hosts(urlconf):
    assert resolve("/medien/demo.svg", urlconf=urlconf).func is demo_image_view


def _tenant(**kw):
    kw.setdefault("slug", "x")
    return TenantFactory(schema_name="public", name="X", city="Hilden", **kw)


def _event(**kw):
    return Event.objects.create(
        title="Kurs",
        starts_at=timezone.now() + timedelta(days=10),
        price_cents=1000,
        status=Event.STATUS_PUBLISHED,
        **kw,
    )


def test_stay_uses_own_photo_before_logo():
    _tenant(logo_url="https://cdn.example.de/logo.png")
    unit = StayUnit.objects.create(name="Zimmer", price_cents=5000, is_active=True, images=PHOTO)
    tasks.sync_stay_listing("public", str(unit.id))
    assert AggregatorListing.objects.get(source_ref=str(unit.id)).image == {
        "url": "/media/x/photo.webp"
    }


def test_event_uses_own_photo():
    _tenant(logo_url="https://cdn.example.de/logo.png")
    ev = _event(images=PHOTO)
    tasks.sync_event_listing("public", str(ev.id))
    assert (
        AggregatorListing.objects.get(source_ref=str(ev.id)).image["url"] == "/media/x/photo.webp"
    )


def test_tour_group_uses_tour_photo():
    _tenant()
    tour = Tour.objects.create(title="T", slug="t", is_published=True, images=PHOTO)
    ev = _event(tour=tour)
    tasks.sync_event_listing("public", str(ev.id))
    row = AggregatorListing.objects.get(source_ref=f"tour:{tour.pk}")
    assert row.image["url"] == "/media/x/photo.webp"


def test_without_photo_and_logo_falls_back_to_banner():
    _tenant(site_config={"hero_image": "/medien/demo.svg?kw=hero"})
    ev = _event()
    tasks.sync_event_listing("public", str(ev.id))
    assert AggregatorListing.objects.get(source_ref=str(ev.id)).image == {
        "url": "/medien/demo.svg?kw=hero"
    }
