"""KA-12 B2-2 (MC-J1): заявка с неоплаченной Anzahlung — строка Offene Posten.

Раньше заявка попадала в «кто мне должен» только после счёта: принятая смета с
назначенным депозитом не была видна ни в списке, ни для сверки выписки. Строка — на
сумму депозита; сопоставление выписки зачитывает ровно депозит (как вебхук), а не
«оплачено полностью».
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.finance import bank
from apps.finance.models import BankTransaction
from apps.jobs import services as job_services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _job(status="accepted", deposit_cents=5000, **kw):
    job = job_services.create_job(title="Bad", name="Kunde")
    job.status = status
    job.deposit_cents = deposit_cents
    for key, value in kw.items():
        setattr(job, key, value)
    job.save()
    return job


def _rows(tenant, job):
    return [i for i in bank.open_items(tenant) if i["kind"] == "job" and i["obj"].pk == job.pk]


def test_accepted_job_with_unpaid_deposit_is_one_open_row():
    tenant = TenantFactory(schema_name="public")
    job = _job()
    rows = _rows(tenant, job)
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("50.00")


@pytest.mark.parametrize(
    "status,kw",
    [
        ("quoted", {}),  # смета не принята — ещё не долг
        ("new", {}),
        ("accepted", {"payment_state": "paid"}),  # депозит пришёл
        ("cancelled", {}),
        ("accepted", {"deposit_cents": 0}),  # без Anzahlung
        ("invoiced", {}),  # после счёта открытая позиция — сам счёт
    ],
)
def test_job_without_open_deposit_has_no_row(status, kw):
    tenant = TenantFactory(schema_name="public")
    job = _job(status=status, **kw)
    assert _rows(tenant, job) == []


def test_bank_match_credits_only_the_deposit():
    """Выписка на сумму депозита: «оплачено» с сохранённым депозитом (как вебхук) —
    счёт потом вычтет 50 €, а не всю сумму работ."""
    tenant = TenantFactory(schema_name="public")
    job = _job()
    tx = BankTransaction.objects.create(
        date=date(2026, 10, 24),
        amount=Decimal("50.00"),
        purpose=f"Anzahlung {job.reference_code}",
        import_hash="j" * 32,
    )
    sugs = bank.suggestions(tx, bank.open_items(tenant))
    assert sugs and sugs[0]["strong"] and sugs[0]["item"]["obj"].pk == job.pk

    assert bank.apply_match(tx, "job", job) is True
    job.refresh_from_db()
    assert job.payment_state == "paid"
    assert job.deposit_cents == 5000  # не обнулён: это Anzahlung, а не вся оплата
    assert _rows(tenant, job) == []
