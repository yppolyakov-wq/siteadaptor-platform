"""VF-13: резерв склада из сметы при «Beauftragt» (2026-08-25).

Резерв = commit_stock при входе в accepted (кламп, идемпотентно); возврат —
release_stock по ЛЕДЖЕРУ при cancelled/declined; правка сметы при активном
резерве приводит резерв к новому составу; после done правка склад не трогает.
Зеркала для кастом-статусов (роль active+blocks_capacity / cancelled)."""

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.inventory.models import StockMovement
from apps.jobs import services
from apps.jobs.state_machine import JobSM

pytestmark = pytest.mark.django_db


def _job(**kwargs):
    kwargs.setdefault("title", "Reparatur")
    kwargs.setdefault("name", "Kunde")
    return services.create_job(**kwargs)


def _lines(job, product, qty):
    services.set_lines(
        job, [{"text": "Teil", "qty": qty, "unit_price": "5.00", "product": product}]
    )


def _apply(job, *dsts):
    sm = JobSM()
    for dst in dsts:
        job = sm.apply(job, dst)
    return job


def test_accept_reserves_stock_and_writes_ledger():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    job = _apply(job, "quoted", "accepted")
    product.refresh_from_db()
    assert product.stock_quantity == 7
    assert job.stock_committed is True
    mv = StockMovement.objects.get(source="job", kind="commit", note=job.reference_code)
    assert mv.delta == -3


def test_done_after_accept_no_double_deduct():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    _apply(job, "quoted", "accepted", "done")
    product.refresh_from_db()
    assert product.stock_quantity == 7  # commit при done — идемпотентный no-op


def test_cancel_returns_reserved_stock():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    job = _apply(job, "quoted", "accepted", "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 10
    assert job.stock_committed is False
    ret = StockMovement.objects.get(source="job", kind="return", note=job.reference_code)
    assert ret.delta == 3
    # Повторный release — дедуп по (source, ref, kind), счётчик не двигается.
    services.release_stock(job)
    product.refresh_from_db()
    assert product.stock_quantity == 10


def test_cancel_after_clamp_returns_only_deducted():
    """Было 2, в смете 5 → резерв клампит в 0; отмена возвращает ровно 2."""
    job = _job()
    product = ProductFactory(stock_quantity=2)
    _lines(job, product, 5)
    job = _apply(job, "quoted", "accepted")
    product.refresh_from_db()
    assert product.stock_quantity == 0
    _apply(job, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 2


def test_declined_without_reserve_no_movements():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    _apply(job, "quoted", "declined")
    product.refresh_from_db()
    assert product.stock_quantity == 10
    assert not StockMovement.objects.filter(source="job").exists()


def test_edit_lines_while_reserved_resyncs():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    job = _apply(job, "quoted", "accepted")
    _lines(job, product, 5)  # правка qty при активном резерве
    product.refresh_from_db()
    assert product.stock_quantity == 5
    assert job.stock_committed is True
    # Отвязка строки (свободный текст) возвращает всё.
    services.set_lines(job, [{"text": "Nur Arbeit", "qty": 1, "unit_price": "50.00"}])
    product.refresh_from_db()
    assert product.stock_quantity == 10


def test_edit_lines_after_done_does_not_touch_stock():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    job = _apply(job, "quoted", "accepted", "done")
    product.refresh_from_db()
    assert product.stock_quantity == 7
    _lines(job, product, 5)  # правка после done — история, склад цел
    product.refresh_from_db()
    assert product.stock_quantity == 7


def test_edit_lines_before_accept_no_reserve():
    job = _job()
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    _apply(job, "quoted")
    _lines(job, product, 5)
    product.refresh_from_db()
    assert product.stock_quantity == 10  # до Beauftragt резерва нет


def test_lots_follow_reserve_and_release():
    """FEFO smoke: партии гасятся при резерве и доливаются при отмене."""
    from apps.inventory.services import lot_balance, receive_lot

    job = _job()
    product = ProductFactory(stock_quantity=0)
    receive_lot(product=product, qty=10, lot_code="L1")
    product.refresh_from_db()
    _lines(job, product, 4)
    job = _apply(job, "quoted", "accepted")
    product.refresh_from_db()
    assert product.stock_quantity == 6
    assert lot_balance(product) == 6
    _apply(job, "cancelled")
    product.refresh_from_db()
    assert product.stock_quantity == 10
    assert lot_balance(product) == 10


def test_custom_active_status_reserves_and_custom_cancel_returns(monkeypatch):
    """Зеркало SM-3: кастом-статус роли active с blocks_capacity (дефолт редактора)
    резервирует как builtin accepted; кастом-отмена возвращает один раз."""
    from apps.core import status_registry
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "job": [
                    {
                        "code": "beauftragt_extern",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    },
                    {"code": "storno_kulanz", "role": "cancelled", "stage": "terminal"},
                ]
            },
            "status_edges": {
                "job": [
                    {"src": "quoted", "dst": "beauftragt_extern"},
                    {"src": "beauftragt_extern", "dst": "storno_kulanz"},
                ]
            },
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    job = _job(email="k@test.de")
    product = ProductFactory(stock_quantity=10)
    _lines(job, product, 3)
    job = _apply(job, "quoted", "beauftragt_extern")
    product.refresh_from_db()
    assert product.stock_quantity == 7  # кастом-active зарезервировал
    job.refresh_from_db()
    assert job.stock_committed is True
    _apply(job, "storno_kulanz")
    product.refresh_from_db()
    assert product.stock_quantity == 10  # кастом-отмена вернула
