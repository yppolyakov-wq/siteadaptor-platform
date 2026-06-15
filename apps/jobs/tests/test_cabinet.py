"""G6 / F2: кабинет Aufträge — ручная заявка, конструктор сметы, переходы
статусов, Angebot-PDF, создание Rechnung из сметы."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.finance.models import Invoice
from apps.jobs import services, views
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/auftraege/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _job(**kwargs):
    kwargs.setdefault("title", "Bad streichen")
    kwargs.setdefault("name", "Kunde")
    return services.create_job(**kwargs)


# --- список / ручная заявка -------------------------------------------------------


def test_manual_request_creates_job():
    resp = views.job_list(
        _req("post", data={"title": "Zaun bauen", "name": "Herr Meyer", "email": "m@t.de"})
    )
    assert resp.status_code == 302
    job = Job.objects.get(title="Zaun bauen")
    assert job.status == "new" and job.source_channel == "manual"
    assert str(job.pk) in resp.url


def test_list_renders_and_filters():
    job = _job()
    body = views.job_list(_req(data={"status": "new"})).content.decode()
    assert job.reference_code in body


def test_detail_renders_with_lines():
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "40.00"}])
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert job.title in body and "Arbeit" in body


# --- конструктор сметы ------------------------------------------------------------


def test_save_lines_computes_totals():
    job = _job()
    resp = views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_text_1": "Arbeit",
                "line_qty_1": "8",
                "line_price_1": "50,00",
                "line_text_2": "Material",
                "line_qty_2": "1",
                "line_price_2": "120,00",
                "vat_rate": "19.00",
                "valid_until": "2026-12-31",
            },
        ),
        pk=job.pk,
    )
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.net == Decimal("520.00") and job.gross == Decimal("618.80")
    assert job.lines.count() == 2
    assert str(job.valid_until) == "2026-12-31"


# --- G11b: пикер расходников из каталога -------------------------------------------


def test_detail_shows_part_picker():
    ProductFactory(base_price="49.00", stock_quantity=5)
    job = _job()
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "line_part_1" in body  # колонка пикера расходников отрисована


def test_save_lines_links_part_and_snapshots():
    product = ProductFactory(base_price="49.00", stock_quantity=10)
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"p:{product.pk}",
                "line_text_1": "",  # пусто → снимок названия
                "line_price_1": "",  # пусто → снимок цены
                "line_qty_1": "2",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert line.product_id == product.id
    assert line.text == product.name_text and line.unit_price == Decimal("49.00")
    assert line.qty == 2


def test_save_lines_links_variant():
    product = ProductFactory(base_price="10.00")
    variant = ProductVariant.objects.create(
        product=product, label="M", price="14.00", stock_quantity=3
    )
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"v:{variant.pk}",
                "line_qty_1": "1",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert line.variant_id == variant.id and line.unit_price == Decimal("14.00")


# --- статусы + Rechnung -----------------------------------------------------------


def test_status_transitions_set_timestamps():
    job = _job()
    views.job_detail(_req("post", data={"action": "quoted"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "quoted" and job.quoted_at is not None
    views.job_detail(_req("post", data={"action": "accepted"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "accepted" and job.accepted_at is not None


def test_create_invoice_from_done_job():
    job = _job()
    services.set_lines(job, [{"text": "Pauschale", "qty": 1, "unit_price": "500.00"}])
    sm = JobSM()
    for dst in ("quoted", "accepted", "done"):
        sm.apply(job, dst)

    resp = views.job_detail(_req("post", data={"action": "invoice"}), pk=job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.status == "invoiced" and job.invoice_id is not None
    invoice = Invoice.objects.get(pk=job.invoice_id)
    assert invoice.gross == Decimal("595.00")  # 500 + 19 %
    assert f"/dashboard/finance/rechnungen/{invoice.pk}/" in resp.url


def test_invoice_blocked_before_done():
    job = _job()
    services.set_lines(job, [{"text": "X", "qty": 1, "unit_price": "10.00"}])
    JobSM().apply(job, "quoted")  # ещё не done
    views.job_detail(_req("post", data={"action": "invoice"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "quoted" and job.invoice_id is None
    assert not Invoice.objects.exists()


# --- PDF + удаление ---------------------------------------------------------------


def test_angebot_pdf_renders():
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "40.00"}])
    resp = views.job_pdf(_req(), pk=job.pk)
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_delete_new_job():
    job = _job()
    resp = views.job_delete(_req("post"), pk=job.pk)
    assert resp.status_code == 302
    assert not Job.objects.filter(pk=job.pk).exists()


def test_vehicle_field_on_create_and_save():
    """A9 Werkstatt: Fahrzeug/Kennzeichen на заявке (создание + правка в кабинете)."""
    job = services.create_job(title="Inspektion", name="Kunde", vehicle="VW Golf · M-AB 1234")
    assert job.vehicle == "VW Golf · M-AB 1234"
    # правка через форму сметы (_save_lines)
    views.job_detail(
        _req("post", data={"action": "save_lines", "vat_rate": "19.00", "vehicle": "BMW · K-XY 9"}),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert job.vehicle == "BMW · K-XY 9"


def test_link_and_unlink_booking():
    """A7d: привязка/отвязка выездного Termin к заявке."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking.models import Booking, Resource

    job = services.create_job(title="Reparatur", name="Kunde", email="k@t.de")
    resource = Resource.objects.create(name="Team")
    start = timezone.now() + timedelta(days=1)
    booking = Booking.objects.create(
        resource=resource,
        customer=job.customer,
        reference_code="T-AAA111",
        start=start,
        end=start + timedelta(hours=1),
        status="confirmed",
    )
    views.job_detail(
        _req("post", data={"action": "link_booking", "booking": str(booking.pk)}), pk=job.pk
    )
    job.refresh_from_db()
    assert job.booking_id == booking.pk

    views.job_detail(_req("post", data={"action": "unlink_booking"}), pk=job.pk)
    job.refresh_from_db()
    assert job.booking_id is None
