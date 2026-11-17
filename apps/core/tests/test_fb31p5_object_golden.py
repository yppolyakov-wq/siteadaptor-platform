"""FB-31 P5 R8a: характеризация страниц ОДНОГО объекта до своей схемы объекта (R8).

Товар, услуга, номер, событие, тур × свои блоки объекта (с общими и без), «свои блоки
впереди» (`blocks_first`), свои отличия видимости (`page_override`), раскладка. План —
`docs/fb31-p5-detail-plan-2026-11-16.md` §12: всё, кроме `blocks_first`, после R8 обязано
остаться байт-в-байт; `blocks_first` меняется осознанно (свои блоки — перед первым разделом).

Обновить (осознанно): FB31P5_GOLDEN=update uv run pytest <этот файл>
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.tests import test_fb31p5_detail_golden as g

pytestmark = pytest.mark.django_db

OWN = {"key": "text", "id": "t-own", "data": {"title": "Nur hier", "body": "Eigener Block"}}


@pytest.fixture(autouse=True)
def _urlconf(settings, monkeypatch):
    monkeypatch.setattr(timezone, "now", g.ticking_clock(g.FROZEN_NOW))  # «сегодня» эталонов
    settings.ROOT_URLCONF = "config.urls_tenant"


def _product():
    from apps.catalog.tests.factories import ProductFactory

    return ProductFactory(name={"de": "Bauernbrot"}, description={"de": "Sauerteig, 1 kg."})


def _service():
    from apps.booking.models import Service

    return Service.objects.create(
        name="Haarschnitt",
        description="Waschen, schneiden, föhnen.",
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
    )


def _stay():
    from apps.stays.models import StayUnit

    return StayUnit.objects.create(
        name="FeWo See", price_cents=9000, description="Blick auf den See."
    )


def _event():
    from apps.events.models import Event

    return Event.objects.create(
        title="Konzert",
        description="Ein Abend mit Live-Musik.",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
        details=g.DETAILS,
    )


def _tour():
    from apps.events.models import Event, Tour

    tour = Tour.objects.create(
        title="Manali – Leh",
        slug=f"manali-{uuid.uuid4().hex[:6]}",
        is_published=True,
        details=g.DETAILS,
    )
    Event.objects.create(
        title="Juni-Tour",
        tour=tour,
        starts_at=timezone.now() + timedelta(days=30),
        status=Event.STATUS_PUBLISHED,
    )
    return tour


def _view(kind, obj, cfg):
    if kind == "product":
        from apps.promotions import public_views

        return public_views.product_detail(g._req(f"/sortiment/{obj.pk}/", cfg), pk=obj.pk)
    if kind == "service":
        from apps.booking import public_views

        return public_views.service_detail(g._req("/leistung/", cfg), pk=obj.pk)
    if kind == "stay":
        from apps.stays import public_views

        return public_views.unterkunft_unit(g._req(f"/unterkunft/{obj.pk}/", cfg), pk=obj.pk)
    from apps.events import public_views

    if kind == "event":
        return public_views.veranstaltung_detail(
            g._req(f"/veranstaltung/{obj.pk}/", cfg), pk=obj.pk
        )
    return public_views.tour_detail(g._req(f"/touren/{obj.slug}/", cfg), slug=obj.slug)


MAKE = {"product": _product, "service": _service, "stay": _stay, "event": _event, "tour": _tour}
SHARED_HOST = {
    "product": "product_detail",
    "service": "service_detail",
    "stay": "stay_detail",
    "event": "event_detail",
    "tour": "event_detail",
}
LAYOUT_KEY = {"product": "product_detail", "service": "service_detail", "stay": "stay_detail"}
#: раздел, скрытый только у этого объекта (у всех виден)
OWN_HIDDEN = {
    "product": "description",
    "service": "description",
    "stay": "description",
    "event": "includes",
    "tour": "bring",
}
VARIANTS = ("own", "own-shared", "own-tabs", "own-breit", "first", "override")


def _html(kind, variant):
    obj = MAKE[kind]()
    host = f"{kind}:{obj.pk.hex}"
    cfg: dict = {"page_blocks": {host: [OWN]}}
    if variant == "own-shared":
        cfg["page_blocks"][SHARED_HOST[kind]] = [g.TEXT]
    if variant in ("own-tabs", "own-breit"):
        layout_key = LAYOUT_KEY.get(kind, "event_detail")
        cfg[layout_key] = {"layout": variant.split("-")[1]}
    if variant == "first":
        cfg["page_blocks"][SHARED_HOST[kind]] = [g.TEXT]
        obj.page_override = {"blocks_first": "1"}
        obj.save(update_fields=["page_override"])
    if variant == "override":
        obj.page_override = {"hidden": [OWN_HIDDEN[kind]]}
        obj.save(update_fields=["page_override"])
    return _view(kind, obj, cfg).content.decode()


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("kind", sorted(MAKE))
def test_object_page_looks_as_before(kind, variant):
    html = _html(kind, variant)
    assert "Eigener Block" in html or variant == "override"
    g._check(f"obj-{kind}-{variant}", html)
