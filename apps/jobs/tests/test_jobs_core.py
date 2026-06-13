"""G6 / F1: ядро заявок-смет — создание (reuse Customer), расчёт сметы
(НДС 19 % / §19), замена позиций, FSM-переходы."""

from decimal import Decimal

import pytest

from apps.core.fsm import IllegalTransition
from apps.jobs import services
from apps.jobs.models import JobLine
from apps.jobs.state_machine import JobSM
from apps.promotions.models import Customer

pytestmark = pytest.mark.django_db


def _job(**kwargs):
    kwargs.setdefault("title", "Bad streichen")
    kwargs.setdefault("name", "Kunde")
    return services.create_job(**kwargs)


# --- создание / клиент ------------------------------------------------------------


def test_create_job_reuses_customer_and_code():
    existing = Customer.objects.create(name="Stamm", email="kunde@test.de")
    job = _job(
        email="KUNDE@test.de", phone="0151", description="2 Räume", site_address="Hauptstr. 1"
    )
    assert job.status == "new"
    assert job.customer == existing
    assert job.reference_code.startswith("A-")
    assert job.description == "2 Räume" and job.site_address == "Hauptstr. 1"
    # телефон дозаписан существующему клиенту
    existing.refresh_from_db()
    assert existing.phone == "0151"


# --- смета: расчёт сумм -----------------------------------------------------------


def test_set_lines_computes_totals_19():
    job = _job()
    services.set_lines(
        job,
        [
            {"text": "Arbeitsstunden", "qty": 8, "unit_price": "50.00"},
            {"text": "Material", "qty": 1, "unit_price": "120.00"},
        ],
    )
    job.refresh_from_db()
    assert job.lines.count() == 2
    assert job.net == Decimal("520.00")  # 8×50 + 120
    assert job.vat_amount == Decimal("98.80")  # 19 %
    assert job.gross == Decimal("618.80")


def test_set_lines_kleinunternehmer_no_vat():
    job = _job()
    services.set_lines(
        job, [{"text": "Pauschale", "qty": 1, "unit_price": "300.00"}], small_business=True
    )
    job.refresh_from_db()
    assert job.net == Decimal("300.00")
    assert job.vat_amount == Decimal("0.00")
    assert job.gross == Decimal("300.00")


def test_set_lines_replaces_and_skips_empty():
    job = _job()
    services.set_lines(job, [{"text": "A", "qty": 1, "unit_price": "10.00"}])
    services.set_lines(
        job,
        [
            {"text": "", "qty": 1, "unit_price": "99.00"},  # пустой текст — пропуск
            {"text": "B", "qty": 2, "unit_price": "20.00"},
        ],
    )
    job.refresh_from_db()
    assert list(job.lines.values_list("text", flat=True)) == ["B"]
    assert job.net == Decimal("40.00")


def test_lines_snapshot_format():
    job = _job()
    services.set_lines(job, [{"text": "X", "qty": 3, "unit_price": "5.00"}])
    snap = services.lines_snapshot(job)
    assert snap == [{"text": "X", "qty": 3, "unit_price": "5.00"}]


# --- FSM --------------------------------------------------------------------------


def test_job_sm_full_path():
    job = _job()
    sm = JobSM()
    for dst in ("quoted", "accepted", "done", "invoiced"):
        job = sm.apply(job, dst)
    assert job.status == "invoiced"


def test_job_sm_declined_and_illegal():
    job = _job()
    sm = JobSM()
    with pytest.raises(IllegalTransition):
        sm.apply(job, "accepted")  # нельзя из new минуя quoted
    sm.apply(job, "quoted")
    assert sm.apply(job, "declined").status == "declined"


def test_joblines_cascade_with_job():
    job = _job()
    services.set_lines(job, [{"text": "A", "qty": 1, "unit_price": "10.00"}])
    job_id = job.id
    job.delete()
    assert not JobLine.objects.filter(job_id=job_id).exists()
