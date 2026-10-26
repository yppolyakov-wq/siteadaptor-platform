"""KA-12 A-6a (Werkstatt): машина клиента как сущность — привязка заявки, перенос
старых заявок, пробег, поиск, карточка клиента, DSGVO."""

import importlib
import uuid

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.jobs import services, vehicles, views
from apps.jobs.models import Job, Vehicle
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw1234567")
    request.tenant = TenantFactory.build(disabled_modules=[], business_type="werkstatt")
    return request


def _job(plate="M-AB 12", email="", name="Herr Lang", **kw):
    job = services.create_job(title="Inspektion", name=name, email=email, vehicle_plate=plate, **kw)
    job.refresh_from_db()
    return job


def test_plate_creates_and_links_one_vehicle_per_customer():
    email = f"{uuid.uuid4().hex[:6]}@example.com"
    first = _job("m-ab  12", email=email, vehicle_hsn="0603", vehicle="VW Golf")
    second = _job("M-AB 12", email=email)
    assert first.vehicle_ref_id and first.vehicle_ref_id == second.vehicle_ref_id
    vehicle = first.vehicle_ref
    assert vehicle.plate == "M-AB 12" and vehicle.hsn == "0603" and vehicle.make_model == "VW Golf"
    assert Vehicle.objects.filter(customer=first.customer).count() == 1


def test_clearing_plate_in_card_unlinks():
    job = _job()
    views.job_detail(
        _req("post", {"action": "request", "title": job.title, "vehicle_plate": ""}), pk=job.pk
    )
    job.refresh_from_db()
    assert job.vehicle_ref_id is None
    assert Vehicle.objects.filter(plate="M-AB 12").exists()  # машина клиента не удаляется


def test_existing_vehicle_fields_are_not_overwritten():
    job = _job(vehicle_hsn="0603")
    Vehicle.objects.filter(pk=job.vehicle_ref_id).update(hsn="1111")
    job.vehicle_hsn = "2222"
    vehicles.ensure_vehicle(job)
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).hsn == "1111"


def test_mileage_never_goes_down():
    job = _job()
    assert vehicles.record_mileage(job, 120000)
    assert not vehicles.record_mileage(job, 90000)
    vehicle = Vehicle.objects.get(pk=job.vehicle_ref_id)
    assert vehicle.mileage_km == 120000
    job.refresh_from_db()
    assert job.mileage_km == 90000  # пробег ЭТОГО визита записан как есть


def test_intake_protocol_mileage_reaches_vehicle():
    job = _job()
    data = {"action": "protocol", "kind": "intake", "date": "2026-10-20", "mileage_km": "45000"}
    views.job_detail(_req("post", data), pk=job.pk)
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).mileage_km == 45000


def test_vin_validation():
    assert vehicles.normalize_vin(" wvwzzz1jzxw000001 ") == "WVWZZZ1JZXW000001"
    assert vehicles.normalize_vin("WVWZZZ1JZXW00000O") is None  # O запрещена ISO 3779
    assert vehicles.normalize_vin("") == ""


def test_vehicle_card_edit_saves_vin_and_hu():
    job = _job()
    data = {
        "action": "vehicle",
        "vin": "WVWZZZ1JZXW000001",
        "first_registration": "2018-03-01",
        "hu_due": "2027-03-31",
        "notes": "Winterreifen im Lager",
    }
    views.job_detail(_req("post", data), pk=job.pk)
    vehicle = Vehicle.objects.get(pk=job.vehicle_ref_id)
    assert vehicle.vin == "WVWZZZ1JZXW000001" and str(vehicle.hu_due) == "2027-03-31"
    bad = views.job_detail(_req("post", {**data, "vin": "KAPUTT"}), pk=job.pk)
    assert bad.status_code == 302
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).vin == "WVWZZZ1JZXW000001"


def test_search_finds_job_by_plate_and_vin():
    from apps.core import transactions

    job = _job("K-XY 777")
    Vehicle.objects.filter(pk=job.vehicle_ref_id).update(vin="WVWZZZ1JZXW000777")
    found = set(transactions._managed_queryset("job", q="XY 777").values_list("pk", flat=True))
    assert job.pk in found
    found = set(transactions._managed_queryset("job", q="ZXW000777").values_list("pk", flat=True))
    assert job.pk in found


def test_customer_card_lists_vehicles():
    from apps.crm import customer360

    job = _job("B-CD 5")
    tenant = TenantFactory.build(disabled_modules=[], business_type="werkstatt")
    sections = {s["key"]: s for s in customer360.sections(tenant, job.customer)}
    assert "vehicles" in sections
    assert "B-CD 5" in sections["vehicles"]["items"][0]["title"]


def test_dsgvo_deletes_vehicle_keeps_job():
    from apps.crm import dsgvo

    job = _job("HH-ZZ 9")
    Job.objects.filter(pk=job.pk).update(status="cancelled")
    dsgvo.erase_customer(job.customer)
    job.refresh_from_db()
    assert not Vehicle.objects.filter(plate="HH-ZZ 9").exists()
    assert job.vehicle_ref_id is None and job.vehicle_plate == ""


def test_data_step_links_old_jobs_idempotently():
    migration = importlib.import_module("apps.jobs.migrations.0024_a6_vehicles_link")
    customer = _job("").customer
    old = Job.objects.create(
        customer=customer,
        reference_code=f"A-{uuid.uuid4().hex[:6].upper()}",
        title="Alt",
        vehicle_plate="s-ab 1",
    )
    Job.objects.create(
        customer=customer,
        reference_code=f"A-{uuid.uuid4().hex[:6].upper()}",
        title="Alt 2",
        vehicle_plate="S-AB  1",
    )
    migration.link_vehicles(django_apps, None)
    migration.link_vehicles(django_apps, None)
    old.refresh_from_db()
    assert old.vehicle_ref.plate == "S-AB 1"
    assert Vehicle.objects.filter(customer=customer, plate="S-AB 1").count() == 1


@pytest.mark.parametrize(
    "raw",
    ["m-ab  12", " M - AB 12 ", "m–ab 12", "M AB 1234", "-", "", "hh-zz9", "MA-B 12"],
)
def test_migration_plate_rule_matches_runtime(raw):
    migration = importlib.import_module("apps.jobs.migrations.0024_a6_vehicles_link")
    assert migration.normalize_plate(raw) == vehicles.normalize_plate(raw)


def test_dash_variants_are_one_vehicle_but_shifted_dash_is_not():
    assert vehicles.normalize_plate("m–ab 12") == vehicles.normalize_plate("M - AB 12")
    assert vehicles.normalize_plate("M-AB 12") != vehicles.normalize_plate("MA-B 12")
