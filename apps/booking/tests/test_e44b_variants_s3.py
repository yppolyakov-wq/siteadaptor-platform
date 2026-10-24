"""KA-12 E4.4b (S3): вариант в контракте карточки и в ручной записи.

Карточка услуги с вариантами — честная «ab <минимум>» цена (варианты одним запросом на
листинг); ручная запись в Tagesplan берёт длину/цену выбранного варианта, мусорный
вариант — запись без варианта с предупреждением (стойку не блокируем)."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.booking import views
from apps.booking.facets import ServiceFacets
from apps.booking.models import Booking, Service, ServiceVariant
from apps.booking.tests.test_cabinet import _msgs, _req, _slot
from apps.booking.tests.test_services import _resource, _service
from apps.core import sellable

pytestmark = pytest.mark.django_db


def _variant(service, name, price=0, minutes=0, order=0):
    return ServiceVariant.objects.create(
        service=service,
        name=name,
        price_delta_cents=price,
        duration_delta_minutes=minutes,
        sort_order=order,
    )


def test_card_price_is_ab_minimum():
    svc = _service(price_cents=3900)
    _variant(svc, "Kurz", price=-900)
    _variant(svc, "Lang", price=1500, order=1)
    data = sellable._service(svc, "de")
    assert data["price_display"] == "ab 30,00 €"
    assert str(data["price_value"]) == "30"


def test_card_without_variants_unchanged():
    svc = _service(price_cents=3900)
    assert sellable._service(svc, "de")["price_display"] == "39,00 €"


def test_card_price_hidden_when_minimum_is_zero():
    svc = _service(price_cents=0)
    _variant(svc, "Lang", price=1500)
    assert sellable._service(svc, "de")["price_display"] == ""


def test_listing_prefetch_has_no_n_plus_one():
    for i in range(4):
        svc = _service(name=f"S{i}", price_cents=1000)
        _variant(svc, "Lang", price=500)
    qs = ServiceFacets().apply(Service.objects.filter(is_active=True), {})
    with CaptureQueriesContext(connection) as ctx:
        cards = [sellable._service(s, "de") for s in qs]
    assert len(cards) == 4 and all(c["price_display"] == "ab 10,00 €" for c in cards)
    assert len(ctx.captured_queries) <= 2, len(ctx.captured_queries)


def _manual(resource, service_value, **extra):
    start = timezone.localtime(_slot(hour=12)[0]).replace(tzinfo=None)
    data = {"resource": str(resource.pk), "start": start.isoformat(), "service": service_value}
    data.update(extra)
    req = _req("post", "/dashboard/booking/neu/", data)
    views.booking_create(req)
    return req


def test_manual_booking_takes_variant_length_and_price(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    r = _resource()
    svc = _service(duration_minutes=45, price_cents=3900)
    lang = _variant(svc, "Langhaar", price=1500, minutes=30)
    _manual(r, f"{svc.pk}:{lang.pk}", override_hours="1")
    b = Booking.objects.get(resource=r)
    assert (b.end - b.start).total_seconds() == 75 * 60
    assert b.price_cents == 5400
    assert b.variant_id == lang.pk and b.variant_label == "Langhaar"


def test_manual_booking_junk_variant_warns_and_books_base(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    r = _resource()
    svc = _service(duration_minutes=45, price_cents=3900)
    foreign = _variant(_service(), "X")
    req = _manual(r, f"{svc.pk}:{foreign.pk}", override_hours="1")
    b = Booking.objects.get(resource=r)
    assert b.variant_id is None and b.price_cents == 3900
    assert any("Variante" in m for m in _msgs(req))


def test_tagesplan_offers_variant_options(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    svc = _service(name="Haarschnitt")
    lang = _variant(svc, "Langhaar")
    _resource()
    from django.template.loader import render_to_string

    req = _req("get", "/dashboard/booking/")
    body = render_to_string(
        "booking/_tagesplan_body.html", views.calendar_context(req), request=req
    )
    assert f'value="{svc.pk}:{lang.pk}"' in body
    assert "Haarschnitt · Langhaar" in body
