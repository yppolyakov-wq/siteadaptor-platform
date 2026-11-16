"""FB-31 P5 R0: характеризация детальных страниц ДО разбивки разделов на строки схемы.

Товар, услуга, номер, событие, тур × раскладка (Standard · Tabs · Breit) × скрытые разделы ×
свои блоки страницы × порядок разделов события. План — `docs/fb31-p5-detail-plan-2026-11-16.md`.

Обновить (осознанно): FB31P5_GOLDEN=update uv run pytest <этот файл>
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions.tests import test_fb31p3_promo_golden as _p3
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb31p5"
UPDATE = os.environ.get("FB31P5_GOLDEN") == "update"
DETAILS = {
    "idea": "Musik unter freiem Himmel.",
    "for_whom": ["Familien", "Paare"],
    "includes": [{"title": "Getränk", "text": "ein Glas"}],
    "bring": ["Gute Laune", "Decke"],
    "faq": [{"q": "Parkplatz?", "a": "Ja."}],
}
TEXT = {
    "key": "text",
    "id": "t-det",
    "data": {"title": "Gut zu wissen", "body": "Abholung ab 8 Uhr"},
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _normalize(html: str) -> str:
    """Область страницы от <main> до подвала: свои блоки деталей стоят и ниже <main>."""
    start, end = html.find("<main"), html.find("<footer")
    if start != -1 and end != -1:
        html = html[start:end]
    for rx, sub in (
        (_p3._CSRF, r"\1X"),
        (_p3._NONCE, r"\1X"),
        (_p3._UUID, "UUID"),
        (_p3._HEX32, "HEX"),
        (_p3._ISO, "ISO"),
        (_p3._DAY, "DAY"),
        (_p3._DATE, "DATE"),
        (_p3._TIME, "TIME"),
        (_p3._EPOCH, "EPOCH"),
        (_p3._PK, r"\1N"),
    ):
        html = rx.sub(sub, html)
    return "\n".join(line.rstrip() for line in html.splitlines() if line.strip()) + "\n"


def _check(name, html):
    path = GOLDEN / f"{name}.html"
    got = _normalize(html)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB31P5_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"детальная страница изменилась: {path.name}"


def _req(path, cfg):
    request = RequestFactory().get(path)
    request.META["REMOTE_ADDR"] = "10.1.2.3"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(
        name="Laden X", business_type="cafe", disabled_modules=[], site_config=cfg
    )
    return request


def _product(cfg):
    from apps.catalog.tests.factories import ProductFactory
    from apps.promotions import public_views

    p = ProductFactory(name={"de": "Bauernbrot"}, description={"de": "Sauerteig, 1 kg."})
    return public_views.product_detail(_req(f"/sortiment/{p.pk}/", cfg), pk=p.pk)


def _service(cfg):
    from apps.booking import public_views
    from apps.booking.models import Service

    s = Service.objects.create(
        name="Haarschnitt",
        description="Waschen, schneiden, föhnen.",
        duration_minutes=30,
        price_cents=4900,
        is_active=True,
    )
    return public_views.service_detail(_req("/leistung/", cfg), pk=s.pk)


def _stay(cfg):
    from apps.stays import public_views
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(
        name="FeWo See", price_cents=9000, description="Blick auf den See."
    )
    return public_views.unterkunft_unit(_req(f"/unterkunft/{unit.pk}/", cfg), pk=unit.pk)


def _event(cfg):
    from apps.events import public_views
    from apps.events.models import Event

    ev = Event.objects.create(
        title="Konzert",
        description="Ein Abend mit Live-Musik.",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
        details=DETAILS,
    )
    return public_views.veranstaltung_detail(_req(f"/veranstaltung/{ev.pk}/", cfg), pk=ev.pk)


def _tour(cfg):
    from apps.events import public_views
    from apps.events.models import Event, Tour

    tour = Tour.objects.create(
        title="Manali – Leh",
        slug=f"manali-{uuid.uuid4().hex[:6]}",
        is_published=True,
        details=DETAILS,
    )
    Event.objects.create(
        title="Juni-Tour",
        tour=tour,
        starts_at=timezone.now() + timedelta(days=30),
        status=Event.STATUS_PUBLISHED,
    )
    return public_views.tour_detail(_req(f"/touren/{tour.slug}/", cfg), slug=tour.slug)


RENDER = {
    "product": (_product, "product_detail", "catalog"),
    "service": (_service, "service_detail", "booking"),
    "stay": (_stay, "stay_detail", "stays"),
    "event": (_event, "event_detail", "events"),
    "tour": (_tour, "event_detail", "events"),
}
HIDE = {
    "product": ["description"],
    "service": ["description"],
    "stay": ["description"],
    "event": ["includes"],
    "tour": ["bring"],
}


def _cfg(kind, layout="", hide=False, blocks=False, order=None):
    key = RENDER[kind][1]
    detail = {}
    if layout:
        detail["layout"] = layout
    if hide:
        detail["hidden"] = HIDE[kind]
    if order:
        detail["order"] = order
    cfg = {key: detail} if detail else {}
    if blocks:
        host = "event_detail" if kind == "tour" else key
        cfg["page_blocks"] = {host: [TEXT]}
    return cfg


def _html(kind, **kw):
    render = RENDER[kind][0]
    return render(_cfg(kind, **kw)).content.decode()


@pytest.mark.parametrize("blocks", [False, True], ids=["plain", "blocks"])
@pytest.mark.parametrize("hide", [False, True], ids=["all", "hidden"])
@pytest.mark.parametrize("layout", ["", "tabs", "breit"])
@pytest.mark.parametrize("kind", sorted(RENDER))
def test_detail_page_looks_as_before(kind, layout, hide, blocks):
    name = f"{kind}-{layout or 'standard'}-{'hidden' if hide else 'all'}-{'blocks' if blocks else 'plain'}"
    _check(name, _html(kind, layout=layout, hide=hide, blocks=blocks))


@pytest.mark.parametrize("kind", ["event", "tour"])
def test_event_section_order_looks_as_before(kind):
    order = ["bring", "includes", "for_whom", "idea"]
    _check(f"{kind}-ordered", _html(kind, order=order))


def test_cart_upsell_switch_looks_as_before():
    from apps.orders import public_views

    for flag in (True, False):
        req = _req("/warenkorb/", {"cart_show_upsell": flag})
        html = public_views.cart_view(req).content.decode()
        _check(f"cart-upsell-{'on' if flag else 'off'}", html)
