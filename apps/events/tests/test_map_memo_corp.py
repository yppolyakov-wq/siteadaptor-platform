"""R6: карта (OSM) на странице события, памятка-PDF, корп/групповой запрос."""

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.events import memo, public_views, services
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _store(path="/", tenant=None):
    request = RequestFactory().get(path)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.7"
    request.tenant = tenant or TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Wochenend-Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "ends_at": timezone.now() + timedelta(days=12),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
        "program": ["Fr — Ankommen", "Sa — Yoga"],
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- map -------------------------------------------------------------------
def test_map_embed_with_event_coords():
    ev = _event(latitude="47.965", longitude="7.80")
    body = public_views.veranstaltung_detail(_store(), pk=ev.pk).content.decode()
    assert "openstreetmap.org/export/embed" in body
    assert "marker=47.965" in body


def test_map_fallback_to_tenant_coords():
    ev = _event()  # без координат
    tenant = TenantFactory.build(latitude="48.0", longitude="7.85")
    body = public_views.veranstaltung_detail(_store(tenant=tenant), pk=ev.pk).content.decode()
    assert "openstreetmap.org/export/embed" in body


def test_no_map_without_coords():
    ev = _event()
    body = public_views.veranstaltung_detail(_store(), pk=ev.pk).content.decode()
    assert "openstreetmap.org/export/embed" not in body


# --- corporate inquiry -----------------------------------------------------
def test_corporate_block_when_jobs_active():
    ev = _event()
    body = public_views.veranstaltung_detail(_store(), pk=ev.pk).content.decode()
    assert "/anfrage/?betreff=" in body  # jobs активен у дефолтного тенанта


def test_no_corporate_block_when_jobs_disabled():
    ev = _event()
    tenant = TenantFactory.build(disabled_modules=["jobs"])
    body = public_views.veranstaltung_detail(_store(tenant=tenant), pk=ev.pk).content.decode()
    assert "/anfrage/?betreff=" not in body


def test_anfrage_prefills_betreff():
    from apps.jobs import public_views as jobs_public

    body = jobs_public.anfrage(_store("/anfrage/?betreff=Gruppe: Retreat")).content.decode()
    assert "Gruppe: Retreat" in body


# --- memo PDF --------------------------------------------------------------
def test_build_memo_pdf_returns_pdf_bytes():
    ev = _event(location="Am Waldrand 3, Freiburg")
    ticket = services.book_ticket(ev, name="Mara", email="m@test.de")
    pdf = memo.build_memo_pdf(ticket, TenantFactory.build())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 800


def test_memo_endpoint_returns_pdf():
    ev = _event()
    ticket = services.book_ticket(ev, name="A", email="a@test.de")
    resp = public_views.veranstaltung_memo(
        _store(f"/e/{ticket.reference_code}/memo.pdf"), code=ticket.reference_code
    )
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
